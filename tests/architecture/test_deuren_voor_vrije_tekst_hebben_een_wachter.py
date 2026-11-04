"""De BEKENDE deuren voor vrije tekst, en welke daarvan een inhoudswachter hebben.

**De naam van dit bestand is een correctie.** Hij heette
`test_elke_deur_voor_vrije_tekst_heeft_een_inhoudswachter.py`, en dat woord "elke" was een
overclaim. Een Gate 2-reviewer mat op 2026-09-22 nog ZES andere ingangen waar vrije tekst een
taalmodel of de Council bereikt; die zijn met deze bewaker niet gedekt en waren dat ook nooit.
Een bewaker die "elke deur" belooft en er twee toetst, gaat voor altijd groen terwijl de rest
open staat -- dat is de faalvorm die dit project al twee keer heeft betaald.

**Wat deze bewaker WEL doet:** vastleggen dat de twee deuren die vandaag een wachter hebben, hem
ook blijven aanroepen. Niet meer en niet minder.

**Wat hij NIET doet, en dat is met opzet:** bewijzen dat de wachter EFFECT heeft. Dezelfde
reviewer mat dat deze AST-toets groen blijft bij drie mutaties die de wachter neutraliseren:

    de aanroep blijft, `if not oordeel.toegestaan:` wordt `if False:`   -> GROEN
    de aanroep wordt `logger.info(beoordeel(...))`, weigering weg        -> GROEN
    `beoordeel("")` in plaats van de echte invoer                        -> GROEN

Dat is een grens van een wiring-toets en geen gat dat met meer AST-slimheid te dichten is. Het
GEDRAG is daarom per deur apart belegd, en dat is waar de bewijslast hoort:

    chat   -> tests/unit/copilot/test_service.py::TestInputGuardOpDeChatdeur
    agent  -> tests/unit/als/test_de_agentdeur_beoordeelt_de_inhoud.py

Beide bestaan sinds 2026-09-22; voor de agentdeur was er tot die dag NIETS.

**Waarom AST en geen tekstzoekactie.** Een bewaker die `"beoordeel" in bron` toetst, wordt groen
gehouden door de naam in een comment -- en dit bestand staat vol met die naam. Deze bewaker zoekt
een echte `ast.Call` binnen de genoemde functie.

**Mutatiebewijs (2026-09-22, beide richtingen), met `scripts/mutation_harness.py`:**

1. De aanroep uit `handle_turn` halen -> ROOD, met die deur in de melding.
2. De aanroep uit `_reject_before_council` halen -> ROOD, met die deur in de melding.
   Twee APARTE mutaties: een bewaker die beide deuren in een assertie propt kan groen blijven
   op de ene terwijl de andere weg is.
3. De aanroep vervangen door een comment -> ROOD (de AST ziet geen comment).
4. Ongemuteerd -> GROEN.
"""

from __future__ import annotations

import ast
from pathlib import Path

#: De repo-wortel, zodat dit bestand niet afhangt van de werkmap. Dit project heeft een
#: gedocumenteerde valkuil waarbij de shell-cwd stil terugvalt naar de hoofdmap.
REPO = Path(__file__).resolve().parents[2]

#: Deur -> de functie die de wachter MOET aanroepen.
BEWAAKTE_DEUREN: dict[str, str] = {
    "src/core/copilot/service.py": "handle_turn",
    "src/core/als/agents/specialist_base.py": "_reject_before_council",
}

#: Ingangen waar vrije tekst een taalmodel of de Council bereikt en waar NOG GEEN wachter staat.
#: Gevonden door een Gate 2-reviewer op 2026-09-22, door mij nagemeten op de scherpste twee.
#:
#: Deze lijst is met de HAND samengesteld en is dus mogelijk niet compleet -- dat hoort erbij te
#: staan, want een lijst die volledigheid suggereert is erger dan een lijst die het toegeeft. Er
#: is geen scanner die "vrije tekst die een model bereikt" betrouwbaar vindt; dat zou zelf een
#: artefact met eigen bewijslast zijn.
#:
#: De staleness-test hieronder houdt de lijst eerlijk: verdwijnt een ingang of krijgt hij een
#: wachter, dan wordt die test rood en moet de regel hier weg.
ONBEWAAKTE_DEUREN: dict[str, str] = {
    "src/core/api/agentic_flow_endpoints.py": (
        "2026-09-22 -- `request.prompt[:100]` gaat in `context_snapshot` en daarmee naar de "
        "Council (regel 89), en de volledige prompt naar `generate_flow_from_prompt`. Dit is "
        "de scherpste van de zes: hij zet rauwe gebruikerstekst in precies het register waar "
        "de InputGuard voor is gebouwd. Zelf nagemeten."
    ),
    "src/core/api/v1/workflow/workflow_generation_router.py": (
        "2026-09-22 -- `user_prompt=request.prompt` naar de workflowgenerator (regel 91). "
        "Zelf nagemeten: `prompt: str = Field(...)`."
    ),
    "src/core/api/assistant_endpoints.py": (
        "2026-09-22 -- `query: str` tot 5000 tekens naar `user_input=` (regel 92). Zelf nagemeten."
    ),
    "src/core/api/v1/focus_builder/ai_router.py": (
        "2026-09-22 -- prompt naar `generate_flow_from_prompt`. Door de reviewer gemeten, door "
        "mij NIET nagemeten op regelniveau."
    ),
    "src/core/api/v1/workflow/workflow_builder_router.py": (
        "2026-09-22 -- prompt wordt in een LLM-prompt geinterpoleerd. Door de reviewer "
        "gemeten, door mij NIET nagemeten."
    ),
    "src/core/api/agent_endpoints.py": (
        "2026-09-22 -- vrije tekst query/message. Door de reviewer gemeten, door mij NIET "
        "nagemeten."
    ),
}

WACHTER = "beoordeel"


def _functie(boom: ast.Module, naam: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    """Zoek een functie op naam, ook in een klasse. Expliciete recursie."""

    def _zoek(knopen: list[ast.stmt]) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
        for knoop in knopen:
            if isinstance(knoop, (ast.FunctionDef, ast.AsyncFunctionDef)) and knoop.name == naam:
                return knoop
            if isinstance(knoop, ast.ClassDef):
                gevonden = _zoek(knoop.body)
                if gevonden is not None:
                    return gevonden
        return None

    return _zoek(boom.body)


def _roept_wachter_aan(functie: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Staat er een echte aanroep `beoordeel(...)` in deze functie?"""
    for knoop in ast.walk(functie):
        if not isinstance(knoop, ast.Call):
            continue
        doel = knoop.func
        if isinstance(doel, ast.Name) and doel.id == WACHTER:
            return True
        if isinstance(doel, ast.Attribute) and doel.attr == WACHTER:
            return True
    return False


def _noemt_de_wachter(pad: Path) -> bool:
    """Importeert of roept dit bestand de wachter aan? Op de AST, niet op de tekst.

    **Dit was eerst een substring-toets, en die viel meteen om.** `WACHTER in bron` matchte het
    woord "beoordeeld" in een Nederlandse foutmelding in `agentic_flow_endpoints.py`, waardoor
    de staleness-test beweerde dat die ingang al een wachter had. Dat is exact de faalvorm die
    `.claude/rules/quality-gates.md` beschrijft -- tekst doorzoeken waar structuur hoort -- en
    hij zat in een bewaker die ik net had geschreven om precies dat te voorkomen. Gevonden
    doordat de test rood werd, dus hij kan tenminste falen.
    """
    try:
        boom = ast.parse(pad.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return False
    for knoop in ast.walk(boom):
        if isinstance(knoop, ast.ImportFrom) and knoop.module == "src.core.governance.input_guard":
            return True
        if isinstance(knoop, ast.Call):
            doel = knoop.func
            if isinstance(doel, ast.Name) and doel.id == WACHTER:
                return True
            if isinstance(doel, ast.Attribute) and doel.attr == WACHTER:
                return True
    return False


def test_elke_bewaakte_deur_roept_de_inhoudswachter_aan() -> None:
    """Per deur een eigen melding, zodat zichtbaar is WELKE deur open staat."""
    zonder: list[str] = []

    for pad, functienaam in BEWAAKTE_DEUREN.items():
        bron = (REPO / pad).read_text(encoding="utf-8")
        functie = _functie(ast.parse(bron), functienaam)
        assert functie is not None, (
            f"`{functienaam}` bestaat niet meer in {pad}. Is de deur verplaatst, dan hoort deze "
            "bewaker mee te verhuizen -- niet weggehaald te worden."
        )
        if not _roept_wachter_aan(functie):
            zonder.append(f"{pad}::{functienaam}")

    assert not zonder, (
        "Deze bewaakte deuren laten vrije tekst binnen zonder hem te laten beoordelen:\n"
        + "\n".join(f"  - {d}" for d in zonder)
        + f"\n\nRoep `{WACHTER}()` aan uit `src/core/governance/input_guard.py`. De Council kan "
        "dit niet opvangen: die krijgt per ontwerp alleen de argumentNAMEN en niet de waarden "
        "(ADR-036 OP-25), want alles wat hij ziet gaat de onuitwisbare ADR-019-keten in."
    )


def test_de_onbewaakte_deuren_zijn_niet_verouderd() -> None:
    """Een ingang die verdwijnt of een wachter krijgt, hoort uit de lijst.

    Zonder deze test rot de opsomming dicht: de bestanden veranderen, de lijst blijft, en een
    lezer denkt dat er zes gaten zijn terwijl er vier of acht zijn.
    """
    verdwenen = [pad for pad in ONBEWAAKTE_DEUREN if not (REPO / pad).exists()]
    assert not verdwenen, (
        f"Deze ingangen bestaan niet meer; haal ze uit ONBEWAAKTE_DEUREN: {verdwenen}"
    )

    inmiddels_bewaakt = [pad for pad in ONBEWAAKTE_DEUREN if _noemt_de_wachter(REPO / pad)]
    assert not inmiddels_bewaakt, (
        "Deze ingangen noemen de wachter inmiddels; verplaats ze naar BEWAAKTE_DEUREN met de "
        f"functienaam erbij: {inmiddels_bewaakt}"
    )


def test_de_wachter_bestaat_en_heet_nog_zo() -> None:
    """Zonder deze test is de eerste assertie groen te houden met een hernoeming.

    Zou `beoordeel` hernoemd worden, dan vindt `_roept_wachter_aan` niets meer -- en dan faalt
    de eerste test met "deze deuren laten vrije tekst binnen", wat de lezer op het verkeerde
    spoor zet. Deze test wijst de echte oorzaak aan.
    """
    from src.core.governance import input_guard

    assert hasattr(input_guard, WACHTER), (
        f"`input_guard.{WACHTER}` bestaat niet meer. Is hij hernoemd, werk dan WACHTER bij; de "
        "deuren hierboven falen anders met een misleidende melding."
    )


def test_de_deurenlijsten_zijn_niet_leeg() -> None:
    """Een lege verzameling maakt de asserties hierboven trivially groen.

    Gemeten 2026-09-22: twee bewaakte deuren, zes bekende onbewaakte. Dat tweede getal is
    expliciet GEEN doel om te halen maar een stand die zichtbaar hoort te blijven.
    """
    assert len(BEWAAKTE_DEUREN) >= 2, (
        f"Slechts {len(BEWAAKTE_DEUREN)} bewaakte deur(en). Op 2026-09-22 waren het er twee."
    )
    assert len(ONBEWAAKTE_DEUREN) >= 1, (
        "De lijst met onbewaakte ingangen is leeg. Dat zou goed nieuws zijn, maar dan hoort er "
        "een meting bij die aantoont dat er geen ingang meer zonder wachter is -- en die "
        "meting bestaat niet."
    )
