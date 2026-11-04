"""Elke deur waar een agent een actie start controleert de noodstop (noodstop per klant; ADR-036 OP-03).

Drie dingen worden hier bewaakt, uit de BRONCODE gelezen (de autouse-stub in `tests/conftest.py`
verbergt dus niets):

1. **De deuren.** Elke functie in `DEUREN` roept een controle aan (`eis_klant_actief`,
   `klant_staat_stil`, of voor een chat `eis_chat_actief`), en wel op een plek die telt: niet in een
   `except`/`finally`, niet in een dode tak (`if False`, `if TYPE_CHECKING`), niet in een geneste
   functie die de deur nergens gebruikt, en VOOR de eerste actie die bij de deur is benoemd
   (`acties`). Haalt iemand de controle weg of verschuift hij naar na de actie, dan faalt de test.
2. **De inventaris per FUNCTIE.** Elke Dramatiq-actor en elke functie die een taak inplant
   (`.add_job(`) is een eenheid. Een eenheid in een bestand dat in `DEUREN` staat moet in
   `UITVOERDERS` staan met de deur die hij gebruikt (of zelf de deur zijn). Een tweede actor in
   een deurbestand blijft zo niet onzichtbaar. Een bestand met een actor dat nergens is ingedeeld
   moet in `DEUREN` of in `VRIJGESTELD` (met reden).
3. **De chat-ingangen.** Elke functie met een chatnaam (`chat`, `chat_stream`, `process_chat`,
   `handle_turn`, ...) en elke websocketroute met `chat` in het pad staat in `DEUREN` (een
   chat-deur) of in `VRIJGESTELD_CHAT` met een reden.

**Bekende grens.** De volgorde-controle vergelijkt regelnummers en kent geen vertakkingen: een
controle in een `if` die een actie niet altijd dekt, ziet deze test als geldig. Daarom staat de
volgorde alleen vast voor de acties die in `DEUREN` zijn benoemd, en blijft het gedrag zelf
bewaakt door de gedragstests in `tests/unit/noodstop` en `tests/integration`. LLM-gebruikers die
geen chat zijn (generatoren, agents) vallen buiten deze inventaris: besluit A van de gebruiker
dekt de chat.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CONTROLES = {"eis_klant_actief", "klant_staat_stil", "eis_chat_actief"}

#: (bestand, functie, acties). De functie mag de controle ook in een geneste functie hebben.
#: `acties` zijn de namen van aanroepen die de agentactie STARTEN; de controle moet er voor staan.
Deur = tuple[str, str, tuple[str, ...]]
DEUREN: tuple[Deur, ...] = (
    (
        "src/core/tool_broker/service.py",
        "execute_tool",
        ("is_tool_allowed", "redeem_approval", "classify"),
    ),
    (
        "src/core/copilot/council/coordinator.py",
        "deliberate",
        ("load_policy", "_build_context", "_gather_verdicts"),
    ),
    (
        "src/core/workflow/engine.py",
        "execute_workflow",
        ("_parse_spec", "_update_execution_status", "_execute_task_with_retry"),
    ),
    (
        "src/core/workflow/engine.py",
        "execute_task",
        ("_get_task", "_execute_llm_task", "_execute_tool_task", "_execute_agent_task"),
    ),
    ("src/core/tasks/workflow_tasks.py", "execute_workflow_step", ("process_task",)),
    (
        "src/core/tasks/cva_tasks.py",
        "_process_cva_message_async",
        ("initialize", "chat", "send_telegram_message"),
    ),
    ("src/core/tasks/debiteuren_tasks.py", "verstuur_klare_berichten_async", ("_verwerk",)),
    ("src/core/tasks/debiteuren_tasks.py", "volg_debiteuren_op_async", ("_escaleer",)),
    (
        "src/core/copilot/proactive/scheduler.py",
        "_run_for_all_tenants",
        ("detect", "propose_to_council"),
    ),
    ("src/core/api/v1/tool_broker/hitl_router.py", "approve_hitl_request", ("approve",)),
    # De chat (besluit A, ronde 2).
    (
        "src/core/services/cva_service.py",
        "chat",
        ("_get_conversation", "_create_conversation", "build_council", "_llm_voor"),
    ),
    (
        "src/core/services/cva_service.py",
        "chat_stream",
        ("_get_conversation", "_create_conversation", "build_council", "_llm_voor"),
    ),
    ("src/core/copilot/service.py", "handle_turn", ("beoordeel", "_augment_context")),
    (
        "src/core/api/v1/focus_builder/ws_chat_router.py",
        "focus_builder_ws_chat",
        (
            "handle_message",
            "handle_refine",
            "handle_explain",
            "handle_template_action",
            "handle_node_updated",
        ),
    ),
    ("src/domains/agentic/services/chat_service.py", "process_chat", ("_get_or_create_session",)),
    (
        "src/domains/agentic/services/chat_service.py",
        "process_chat_stream",
        ("_get_or_create_session",),
    ),
)

#: Eenheden (actor of geplande taak) in een deurbestand: (bestand, eenheid) -> de deur die hij gebruikt.
UITVOERDERS: dict[tuple[str, str], str] = {
    ("src/core/tasks/workflow_tasks.py", "execute_workflow_step"): "execute_workflow_step",
    ("src/core/tasks/cva_tasks.py", "process_cva_message"): "_process_cva_message_async",
    ("src/core/tasks/debiteuren_tasks.py", "verstuur_klare_berichten"): (
        "verstuur_klare_berichten_async"
    ),
    ("src/core/tasks/debiteuren_tasks.py", "volg_debiteuren_op"): "volg_debiteuren_op_async",
    ("src/core/copilot/proactive/scheduler.py", "start"): "_run_for_all_tenants",
}

#: Bestanden met een actor of geplande taak die GEEN agentactie start. Reden erbij, anders niet erin.
VRIJGESTELD: dict[str, str] = {
    "src/core/actors/gdpr_purge.py": "wist gegevens op grond van de AVG; mag nooit stilvallen",
    "src/core/als/bonlezer/worker.py": "leest een geuploade bon zonder uitgaand netwerk; geen actie",
    "src/core/copilot/api/contest_service.py": "in-app melding aan beheerders over een betwisting",
    "src/core/copilot/audit/integrity_check_actor.py": "controleert de hashketen; mag niet stilvallen",
    "src/core/copilot/audit/report_jobs.py": "bouwt een auditrapport; geen actie naar buiten",
    "src/core/governance/retention_cleanup.py": "bewaartermijnen opruimen (AVG); mag niet stilvallen",
    "src/core/learning/worker.py": "interne leerverwerking en opruiming; geen actie naar buiten",
    "src/core/tasks/dramatiq_broker.py": "definieert de broker en de `workflow_actor`-decorator (OP-13); een actor zelf is het niet",
    "src/core/tasks/audit_tasks.py": "schrijft een auditregel; een stop mag het logboek niet dichtzetten",
    "src/core/tasks/bonnen_opruimen.py": "verwijdert oude bonnen (bewaartermijn); mag niet stilvallen",
    "src/core/tasks/hr_termijn_tasks.py": "alleen een in-app melding aan HR; wijzigt en beslist niets",
    "src/domains/memory/tasks.py": "fysiek wissen van verwijderde geheugenitems (AVG)",
    "src/workers/actors.py": "onderhoud, aggregatie, opruiming en documentverwerking; geen agentactie",
    "src/workers/calendar_sync_worker.py": "synchroniseert een agenda; geen agentactie",
    "src/workers/scheduler.py": "zet alleen taken in de wachtrij; de actor controleert zelf",
    "src/workers/workflow_worker.py": "start via `engine.execute_workflow`, en dat is een deur hierboven",
}

#: Chat-ingangen die zelf niet controleren: ze lopen langs een chat-deur, of zitten onder de deur.
VRIJGESTELD_CHAT: dict[str, str] = {
    "src/core/api/v1/cva/chat_router.py": "roept `CVAService.chat` en `chat_stream` aan (deuren)",
    "src/core/copilot/api/chat_websocket.py": "roept `handle_turn_stream`, dat via `handle_turn` loopt",
    "src/core/copilot/api/turn_endpoint.py": "roept `handle_turn` en `handle_turn_stream` aan",
    "src/api/v1/endpoints/agent.py": "roept `AgentChatService.process_chat(_stream)` aan (deuren)",
    "src/core/llm/deepseek_provider.py": "modelclient ONDER de deur; de aanroeper controleert",
    "src/core/llm/ollama_client.py": "modelclient ONDER de deur; de aanroeper controleert",
}

#: Wat een actor of geplande taak in een bestand verraadt.
# `@workflow_actor` is de decorator uit `src/core/tasks/dramatiq_broker.py` (OP-13): sinds develop
# `d054a114` hangt elke workflowactor daaraan, in plaats van aan `@dramatiq.actor` of een lokale alias.
MARKERS = ("@dramatiq.actor", "_workflow_actor(", "@workflow_actor", ".add_job(")
CHAT_NAMEN = {"chat", "chat_stream", "process_chat", "process_chat_stream"}
CHAT_NAMEN |= {"handle_turn", "handle_turn_stream"}


def _bron(pad: str) -> str:
    return (ROOT / pad).read_text(encoding="utf-8")


def _functies(boom: ast.AST, naam: str) -> list[ast.AST]:
    return [
        n
        for n in ast.walk(boom)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == naam
    ]


def _naam_van_aanroep(n: ast.Call) -> str:
    f = n.func
    return f.id if isinstance(f, ast.Name) else f.attr if isinstance(f, ast.Attribute) else ""


def _is_dood(test: ast.expr) -> bool:
    """Een voorwaarde die de body nooit (of alleen voor een typechecker) laat draaien."""
    if isinstance(test, ast.Constant):
        return not test.value
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    if isinstance(test, ast.Attribute):
        return test.attr == "TYPE_CHECKING"
    return False


def _geldige_controles(functie: ast.AST) -> list[ast.Call]:
    """De controle-aanroepen die echt een deur vormen (zie de moduledocstring)."""
    ouders: dict[ast.AST, ast.AST] = {}
    for p in ast.walk(functie):
        for kind in ast.iter_child_nodes(p):
            ouders[kind] = p
    gebruikte_namen = {n.id for n in ast.walk(functie) if isinstance(n, ast.Name)}

    def telt(aanroep: ast.AST) -> bool:
        kind = aanroep
        while kind is not functie:
            ouder = ouders[kind]
            if isinstance(ouder, ast.ExceptHandler):
                return False
            if isinstance(ouder, ast.Try) and kind in ouder.finalbody:
                return False
            if isinstance(ouder, ast.If) and kind in ouder.body and _is_dood(ouder.test):
                return False
            if (
                isinstance(ouder, (ast.FunctionDef, ast.AsyncFunctionDef))
                and ouder is not functie
                and ouder.name not in gebruikte_namen
            ):
                return False  # een geneste functie die de deur nergens gebruikt
            kind = ouder
        return True

    return [
        n
        for n in ast.walk(functie)
        if isinstance(n, ast.Call) and _naam_van_aanroep(n) in CONTROLES and telt(n)
    ]


def _roept_controle_aan(functie: ast.AST, acties: tuple[str, ...] = ()) -> bool:
    """True als de functie een geldige controle heeft, voor de eerste benoemde actie."""
    controles = _geldige_controles(functie)
    if not controles:
        return False
    if not acties:
        return True
    actieregels = [
        n.lineno
        for n in ast.walk(functie)
        if isinstance(n, ast.Call) and _naam_van_aanroep(n) in acties
    ]
    if not actieregels:
        return True  # de staleness-test hieronder meldt een verdwenen actie apart
    return min(c.lineno for c in controles) < min(actieregels)


def _acties_aanwezig(functie: ast.AST, acties: tuple[str, ...]) -> bool:
    return any(
        isinstance(n, ast.Call) and _naam_van_aanroep(n) in acties for n in ast.walk(functie)
    )


_IDS = [f"{p}::{f}" for p, f, _ in DEUREN]


@pytest.mark.parametrize(("pad", "functie", "acties"), DEUREN, ids=_IDS)
def test_elke_deur_roept_de_noodstopcontrole_aan(
    pad: str, functie: str, acties: tuple[str, ...]
) -> None:
    gevonden = _functies(ast.parse(_bron(pad)), functie)
    assert gevonden, f"deur {pad}::{functie} bestaat niet meer; werk DEUREN bij"
    assert any(_roept_controle_aan(f, acties) for f in gevonden), (
        f"{pad}::{functie} start een agentactie maar controleert de noodstop niet, of niet VOOR "
        f"de eerste actie ({', '.join(acties)}), of op een plek die niet telt (een except, een "
        "finally, een dode tak, een ongebruikte geneste functie). Zie de moduledocstring."
    )


@pytest.mark.parametrize(("pad", "functie", "acties"), DEUREN, ids=_IDS)
def test_de_benoemde_acties_van_een_deur_bestaan_nog(
    pad: str, functie: str, acties: tuple[str, ...]
) -> None:
    gevonden = _functies(ast.parse(_bron(pad)), functie)
    assert any(_acties_aanwezig(f, acties) for f in gevonden), (
        f"geen van de acties {acties} komt nog voor in {pad}::{functie}; de volgorde-controle "
        "meet dan niets meer. Werk `acties` in DEUREN bij."
    )


def test_de_deuren_importeren_de_controle_uit_de_guard() -> None:
    # `hitl_router` haalt de controle via de broker-module (zelfde object): zie de opmerking daar.
    # Binnen agent_runtime lopen de deuren via de ene ingang `services/noodstop_toegang.py` (een rand in de
    # DSM-meter in plaats van tien); die module importeert de guard, en dat staat hieronder vast.
    toegestaan = (
        "src.core.noodstop.guard import",
        "src.core.services.noodstop_toegang import",
        "src.core.tool_broker.service import KlantStilgezet",
    )
    toegang = _bron("src/core/services/noodstop_toegang.py")
    assert "from src.core.noodstop import guard" in toegang, "de ingang importeert de guard niet"
    for naam in ("eis_klant_actief", "eis_chat_actief", "klant_staat_stil", "KlantStilgezet"):
        assert f"{naam} = guard.{naam}" in toegang, f"de ingang biedt {naam} niet als de guard-functie aan"
    # De focus-builder-router haalt de controle uit `focus_builder/dependencies.py` (ADR-033: een router
    # gebruikt alleen wat de dependencies van zijn domein aanbieden); die module importeert hem uit de ingang `services/noodstop_toegang.py`.
    via_dependencies = {
        "src/core/api/v1/focus_builder/ws_chat_router.py": (
            "src/core/api/v1/focus_builder/dependencies.py"
        ),
    }
    for pad in {p for p, _, _ in DEUREN}:
        bron = _bron(pad)
        if pad in via_dependencies:
            assert "eis_chat_actief" in bron, f"{pad} importeert de controle niet"
            assert "src.core.services.noodstop_toegang import" in _bron(via_dependencies[pad]), (
                f"{via_dependencies[pad]} importeert de controle niet uit de ingang"
            )
            continue
        assert any(t in bron for t in toegestaan), f"{pad} importeert de controle niet"


def _bestanden() -> list[str]:
    uit = subprocess.run(
        ["git", "ls-files", "src"], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.split()
    return [p for p in uit if p.endswith(".py")]


def _bestanden_met_actor_of_taak() -> set[str]:
    return {pad for pad in _bestanden() if any(m in _bron(pad) for m in MARKERS)}


def _is_actor(f: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    for d in f.decorator_list:
        kern = d.func if isinstance(d, ast.Call) else d
        if isinstance(kern, ast.Attribute) and kern.attr == "actor":
            return True
        if isinstance(kern, ast.Name) and kern.id in {"actor", "_workflow_actor", "workflow_actor"}:
            return True
    return False


def _eenheden(boom: ast.AST) -> set[str]:
    """Namen van de functies die een actor zijn of een taak inplannen."""
    eenheden: set[str] = set()
    for n in ast.walk(boom):
        if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        plant_in = any(
            isinstance(c, ast.Call)
            and isinstance(c.func, ast.Attribute)
            and c.func.attr == "add_job"
            for c in ast.walk(n)
        )
        if _is_actor(n) or plant_in:
            eenheden.add(n.name)
    return eenheden


def test_elk_bestand_met_een_actor_of_geplande_taak_is_ingedeeld() -> None:
    ingedeeld = {p for p, _, _ in DEUREN} | set(VRIJGESTELD)
    niet_ingedeeld = sorted(_bestanden_met_actor_of_taak() - ingedeeld)
    assert not niet_ingedeeld, (
        "Nieuwe actor of geplande taak zonder indeling: "
        f"{niet_ingedeeld}. Is het een deur (agentactie)? Zet er de noodstopcontrole in en voeg het "
        "toe aan DEUREN. Zo niet, voeg het toe aan VRIJGESTELD met de reden."
    )


def test_elke_actor_in_een_deurbestand_is_ingedeeld_per_functie() -> None:
    deurnamen = {(p, f) for p, f, _ in DEUREN}
    ontbreekt: list[str] = []
    verkeerd: list[str] = []
    for pad in sorted({p for p, _, _ in DEUREN}):
        boom = ast.parse(_bron(pad))
        for eenheid in sorted(_eenheden(boom)):
            deur = UITVOERDERS.get((pad, eenheid))
            if deur is None:
                ontbreekt.append(f"{pad}::{eenheid}")
                continue
            if (pad, deur) not in deurnamen:
                verkeerd.append(f"{pad}::{eenheid} -> {deur} (geen deur in DEUREN)")
                continue
            if eenheid == deur:
                continue
            for functie in _functies(boom, eenheid):
                gebruikt = {n.id for n in ast.walk(functie) if isinstance(n, ast.Name)}
                gebruikt |= {n.attr for n in ast.walk(functie) if isinstance(n, ast.Attribute)}
                if deur not in gebruikt:
                    verkeerd.append(f"{pad}::{eenheid} gebruikt de deur {deur} niet")
    assert not ontbreekt, (
        f"Actor of geplande taak in een deurbestand zonder indeling: {ontbreekt}. Een tweede actor "
        "naast een deur is niet automatisch gedekt: laat hem een deur gebruiken (en voeg hem toe "
        "aan UITVOERDERS) of maak hem zelf een deur."
    )
    assert not verkeerd, f"Verkeerde indeling in UITVOERDERS: {verkeerd}"


def test_uitvoerders_zijn_niet_verouderd() -> None:
    aanwezig = {
        (pad, e) for pad in {p for p, _ in UITVOERDERS} for e in _eenheden(ast.parse(_bron(pad)))
    }
    assert not (set(UITVOERDERS) - aanwezig), f"Verouderd: {sorted(set(UITVOERDERS) - aanwezig)}"


def test_de_vrijstellingen_zijn_niet_verouderd() -> None:
    verouderd = sorted(set(VRIJGESTELD) - _bestanden_met_actor_of_taak())
    assert not verouderd, f"Geen actor of taak meer in {verouderd}; haal ze uit VRIJGESTELD"


def test_een_vrijstelling_is_geen_deur() -> None:
    deurbestanden = {p for p, _, _ in DEUREN}
    assert not (deurbestanden & set(VRIJGESTELD))
    assert not (deurbestanden & set(VRIJGESTELD_CHAT))
    assert all(reden.strip() for reden in VRIJGESTELD.values())
    assert all(reden.strip() for reden in VRIJGESTELD_CHAT.values())


def _is_chatroute(d: ast.expr) -> bool:
    return (
        isinstance(d, ast.Call)
        and isinstance(d.func, ast.Attribute)
        and d.func.attr == "websocket"
        and bool(d.args)
        and isinstance(d.args[0], ast.Constant)
        and "chat" in str(d.args[0].value)
    )


def _chat_ingangen() -> set[str]:
    """Bestanden met een chat-functie of een websocketroute met `chat` in het pad."""
    gevonden: set[str] = set()
    for pad in _bestanden():
        bron = _bron(pad)
        if "chat" not in bron.lower() and "handle_turn" not in bron:
            continue
        for n in ast.walk(ast.parse(bron)):
            if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if n.name in CHAT_NAMEN or any(_is_chatroute(d) for d in n.decorator_list):
                gevonden.add(pad)
    return gevonden


def test_elke_chat_ingang_is_ingedeeld() -> None:
    ingedeeld = {p for p, _, _ in DEUREN} | set(VRIJGESTELD_CHAT)
    niet_ingedeeld = sorted(_chat_ingangen() - ingedeeld)
    assert not niet_ingedeeld, (
        f"Chat-ingang zonder noodstopindeling: {niet_ingedeeld}. Een chat die klantgegevens naar "
        "een taalmodel stuurt controleert eerst `eis_chat_actief` (zet hem in DEUREN). Loopt hij "
        "via een bestaande chat-deur, voeg hem dan toe aan VRIJGESTELD_CHAT met de reden."
    )


def test_de_chat_vrijstellingen_zijn_niet_verouderd() -> None:
    verouderd = sorted(p for p in VRIJGESTELD_CHAT if not (ROOT / p).is_file())
    assert not verouderd, f"Bestand bestaat niet meer: {verouderd}; haal ze uit VRIJGESTELD_CHAT"


# --- De controle zelf is gemeten: wat telt als een deur, en wat niet ------------------------------


def _parse(bron: str) -> ast.AST:
    return ast.parse(bron).body[0]


def test_een_controle_voor_de_actie_telt() -> None:
    f = _parse("async def d(t):\n    await eis_klant_actief(t)\n    await doe(t)\n")
    assert _roept_controle_aan(f, ("doe",))


def test_een_controle_na_de_actie_telt_niet() -> None:
    f = _parse("async def d(t):\n    await doe(t)\n    await eis_klant_actief(t)\n")
    assert not _roept_controle_aan(f, ("doe",))


def test_een_controle_in_een_dode_tak_telt_niet() -> None:
    f = _parse(
        "async def d(t):\n    if False:\n        await eis_klant_actief(t)\n    await doe(t)\n"
    )
    assert not _roept_controle_aan(f, ("doe",))
    g = _parse("async def d(t):\n    if TYPE_CHECKING:\n        await klant_staat_stil(t)\n")
    assert not _roept_controle_aan(g)


def test_een_controle_in_een_except_of_finally_telt_niet() -> None:
    f = _parse(
        "async def d(t):\n    try:\n        await doe(t)\n    except Exception:\n"
        "        await eis_klant_actief(t)\n"
    )
    assert not _roept_controle_aan(f, ("doe",))
    g = _parse(
        "async def d(t):\n    try:\n        await doe(t)\n    finally:\n"
        "        await eis_klant_actief(t)\n"
    )
    assert not _roept_controle_aan(g, ("doe",))


def test_een_controle_in_een_ongebruikte_geneste_functie_telt_niet() -> None:
    ongebruikt = _parse(
        "async def d(t):\n    async def _x():\n        await eis_klant_actief(t)\n    await doe(t)\n"
    )
    assert not _roept_controle_aan(ongebruikt, ("doe",))
    gebruikt = _parse(
        "async def d(t):\n    async def _x():\n        await eis_klant_actief(t)\n"
        "    await _x()\n    await doe(t)\n"
    )
    assert _roept_controle_aan(gebruikt, ("doe",))


def test_een_controle_in_een_try_body_voor_de_actie_telt() -> None:
    f = _parse(
        "async def d(t):\n    try:\n        await eis_klant_actief(t)\n    except K:\n"
        "        return\n    await doe(t)\n"
    )
    assert _roept_controle_aan(f, ("doe",))


def test_een_functie_zonder_controle_telt_niet() -> None:
    assert not _roept_controle_aan(_parse("async def d(t):\n    await doe(t)\n"), ("doe",))
