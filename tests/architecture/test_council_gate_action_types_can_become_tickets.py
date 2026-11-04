"""Een HITL-verdict moet een ticket kunnen opleveren, anders vraagt niemand een mens (OP-174).

**Wat het register beweert.** OP-174 gaat volgens de registerrij over een MISLEIDENDE weergave:
`require_council_approval()` geeft `executing_identity` niet door, waardoor het ticket met een
generieke `"copilot"`-identiteit in de goedkeuringslijst komt.

**Wat de hermeting van 2026-08-29 statisch vaststelde, en wat deze test empirisch maakt.** Dat
symptoom veronderstelt dat er een ticket ONTSTAAT. `HITLTicketRepository.create_hitl_request()`
begint echter met `is_known_tool(action_type)` en gooit `ValueError` als daar geen uitvoerder
bij hoort (`src/core/tool_broker/hitl_repository.py:488-493`). De `action_type`-waarden op de
poort zijn domeinnamen als `cva.chat` en `agentic.generate_workflow`; de bekende tools zijn
`local__`/`test__`/`serena__`/`sequentialthinking__` plus de namen uit de Business- en
HR-registry.

Komt geen van die waarden door `is_known_tool`, dan gebeurt er dit bij een
`HITL_REQUIRED`-verdict: `create_hitl_request` gooit, `governance_gate.py:173-181` vangt de
`ValueError`, schrijft een `logger.warning` en gaat door met de 403. Er komt dus GEEN ticket en
GEEN mens -- precies het gat dat OP-167 wilde dichten, een laag hoger. Dat is een zwaarder
probleem dan een verkeerd label in een lijst.

**Waarom deze test de huidige, ONGEWENSTE toestand vastlegt.** Zolang niemand de koppeling
tussen poort-actienamen en uitvoerbare tools heeft gelegd, is dit de werkelijkheid, en die hoort
zichtbaar te zijn in plaats van als aanname in een registerrij. Wordt de koppeling gelegd, dan
wordt deze test ROOD -- en dat is dan het moment om OP-174 te herformuleren naar wat de rij
oorspronkelijk beschreef. Het is een staleness-anker, geen goedkeuring van de situatie.

**Mutatietest (2026-08-30, beide richtingen):**
- `"cva.chat"` aan `BusinessToolRegistry.known_tool_names()` toegevoegd -> ROOD op
  `test_no_gate_action_type_can_become_a_ticket_today`, met die naam in de melding.
- Weer weggehaald -> GROEN.
- De AST-scan leeggemaakt -> ROOD op `test_the_scan_finds_the_gate_call_sites` (vacuiteit).
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SRC = REPO_ROOT / "src"

#: De poortfunctie waarvan de aanroepen worden gescand.
_POORT = "require_council_approval"


def _action_types_op_de_poort() -> tuple[dict[str, str], list[str]]:
    """Per aanroep van de poort: de letterlijke `action_type`, met vindplaats.

    Bewust ALLEEN letterlijke tekst. Een doorgegeven variabele (`api/v1/agents/dependencies.py`
    geeft zijn eigen parameter door) is hier niet te bepalen; die valt buiten de meting en dat
    is eerlijker dan raden.

    Retourneert ook de fouten: een bestand dat niet leest of niet parseert werd voorheen stil
    overgeslagen (`errors="replace"` + kale `except SyntaxError: continue`, geen telling) --
    precies het bestand met een nieuwe, echte `require_council_approval`-aanroep kon zo
    ongezien buiten de scan vallen.
    """
    gevonden: dict[str, str] = {}
    fouten: list[str] = []
    for pad in sorted(SRC.rglob("*.py")):
        if "alembic" in pad.parts:
            continue
        try:
            tekst = pad.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError) as exc:
            fouten.append(f"{pad.relative_to(REPO_ROOT).as_posix()}: {exc}")
            continue
        try:
            boom = ast.parse(tekst)
        except SyntaxError as exc:
            fouten.append(f"{pad.relative_to(REPO_ROOT).as_posix()}: {exc}")
            continue
        for knoop in ast.walk(boom):
            if not isinstance(knoop, ast.Call):
                continue
            doel = knoop.func
            naam = doel.attr if isinstance(doel, ast.Attribute) else getattr(doel, "id", "")
            if naam != _POORT:
                continue
            for sleutelwoord in knoop.keywords:
                if sleutelwoord.arg != "action_type":
                    continue
                waarde = sleutelwoord.value
                if isinstance(waarde, ast.Constant) and isinstance(waarde.value, str):
                    plek = f"{pad.relative_to(REPO_ROOT).as_posix()}:{waarde.lineno}"
                    gevonden[waarde.value] = plek
    return gevonden, fouten


def test_no_source_file_is_silently_unreadable_or_unparseable() -> None:
    """Vangnet PER BESTAND: de vloer hieronder wordt door de gezonde bestanden altijd
    gehaald, dus een enkel overgeslagen bestand blijft daaronder onzichtbaar."""
    _, fouten = _action_types_op_de_poort()
    assert not fouten, (
        "Deze bestanden konden niet gelezen/geparsed worden en zijn NIET gecontroleerd op "
        f"een `{_POORT}`-aanroep:\n" + "\n".join(f"  - {f}" for f in fouten)
    )


def test_the_scan_finds_the_gate_call_sites() -> None:
    """Vangnet: loopt de scan leeg, dan bewijst de test hieronder niets."""
    gevonden, _ = _action_types_op_de_poort()

    assert len(gevonden) >= 6, (
        f"Slechts {len(gevonden)} letterlijke action_type-waarden gevonden op aanroepen van "
        f"`{_POORT}`: {sorted(gevonden)}. Is de poort hernoemd of gaat het argument nu via een "
        "variabele? Dan meet deze guard niets meer."
    )


def test_no_gate_action_type_can_become_a_ticket_today() -> None:
    """Meting, geen wens: geen enkele actienaam van de poort is een uitvoerbare tool.

    Wordt deze test rood, dan is er iets GOED gegaan -- lees de moduledocstring en herformuleer
    ADR-036 OP-174.
    """
    from src.core.tool_broker.service import is_known_tool

    gevonden, _ = _action_types_op_de_poort()
    wel_uitvoerbaar = sorted(
        f"{naam} ({plek})" for naam, plek in gevonden.items() if is_known_tool(naam)
    )

    assert not wel_uitvoerbaar, (
        "Deze actienamen op de Council-poort zijn inmiddels WEL uitvoerbare tools:\n  "
        + "\n  ".join(wel_uitvoerbaar)
        + "\n\nDat is goed nieuws: bij een HITL_REQUIRED-verdict kan er nu een ticket ontstaan "
        "in plaats van alleen een logger.warning. Werk ADR-036 OP-174 bij -- de rij beschrijft "
        "nog het symptoom (een misleidende agent_id op het ticket) en niet meer de oorzaak "
        "(er kwam helemaal geen ticket). Haal daarna deze test weg of draai hem om."
    )


def test_the_gate_swallows_the_refusal_instead_of_failing_loudly() -> None:
    """De poort vangt de weigering af en gaat door met een 403; er is geen tweede signaal.

    Dit is de andere helft van de bevinding. Dat de `ValueError` wordt gevangen is op zichzelf
    juist (een onverwachte exception op een geldig verdict is erger), maar in combinatie met de
    test hierboven betekent het dat ELK HITL-verdict op deze paden stil eindigt in een
    waarschuwing in het log. Zolang beide tests groen zijn, staat OP-174 open op zijn ZWAARSTE
    vorm en niet op de vorm die het register beschrijft.
    """
    poort = SRC / "core/copilot/council/governance_gate.py"
    boom = ast.parse(poort.read_text(encoding="utf-8"))

    vangt_valueerror = False
    for knoop in ast.walk(boom):
        if not isinstance(knoop, ast.ExceptHandler) or knoop.type is None:
            continue
        namen: list[str] = []
        typen = knoop.type.elts if isinstance(knoop.type, ast.Tuple) else [knoop.type]
        for element in typen:
            if isinstance(element, ast.Name):
                namen.append(element.id)
        if "ValueError" in namen:
            vangt_valueerror = True

    assert vangt_valueerror, (
        "`governance_gate.py` vangt geen `ValueError` meer rond `create_hitl_request`. Als die "
        "weigering nu doorslaat naar de aanroeper, is het gedrag veranderd en klopt de analyse "
        "in deze module niet meer -- werk hem bij (ADR-036 OP-174/OP-167)."
    )
