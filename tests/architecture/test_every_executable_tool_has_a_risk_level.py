"""Elke uitvoerbare tool heeft een EIGEN risicoregel -- de prefix-terugval telt niet (OP-130).

**Hoe dit boven water kwam.** Bij het verwijderen van `local__run_shell` (OP-126) verwachtte ik
dat een niet-geclassificeerde tool op de zero-trust `default_risk_level: high` zou vallen. Dat
klopt niet. `ToolRiskClassifier.classify()` lost op in drie stappen -- exacte regel, dan
prefixregel, dan default -- en `tool_prefixes` bevat `local__: medium`. De naam viel dus op
MEDIUM, en MEDIUM opent de HITL-poort niet. Alleen HIGH doet dat.

**Waarom dat erger is dan het lijkt.** Wie een nieuwe `local__`-tool toevoegt wordt vandaag door
twee guards gedwongen iets te doen: `test_tool_policy_matches_the_tools.py` eist een regel in
`redaction.PAYLOAD_POLICY`, en `test_local_tool_names_dispatch_and_every_method_is_named` eist een
dispatchende methode. Geen van beide eist een RISICOREGEL. Een nieuwe `local__delete_everything`
zou dus stil als MEDIUM draaien: gelogd, met een melding achteraf, zonder dat een mens hem vooraf
ziet. De poort staat dan open voor precies de tool waarvoor hij bedoeld is.

**Stand op 2026-08-11: het gat is nul.** Alle elf uitvoerbare tools hebben een exacte regel. Deze
guard houdt dat zo; er is geen uitzonderingslijst en die hoort er ook niet te komen.

**Mutatietest (2026-08-11, beide richtingen):**

1. `local__send_email: high` uit `tool_risk_levels.yml` weghalen -> ROOD, met die naam in de
   melding. Vervangen door een prefixregel `local__send_: high` -> nog steeds ROOD; de guard
   toetst de exacte regel en laat zich niet met een prefix afkopen.

   Die tweede mutatie leverde nog iets op dat het argument versterkt: met `local__send_: high`
   erbij classificeert `local__send_email` als **MEDIUM**, niet HIGH. `classify()` loopt
   `tool_prefixes` af in invoegvolgorde en neemt de EERSTE die past -- niet de langste. Het
   bredere `local__: medium` staat eerder en wint. Een specifiekere prefix later toevoegen doet
   dus niets, terwijl het lijkt alsof je iets hebt aangescherpt. Reden te meer om uitvoerbare
   tools nooit op prefixen te laten leunen (ADR-036 OP-130, meegemeten).
2. De andere kant: ongewijzigd -> GROEN. En `_uitvoerbare_tools()` is aantoonbaar niet leeg
   (`test_the_guard_is_not_vacuous`), want een lege verzameling maakt richting 1 trivially groen.
   Zonder die tweede helft zou "vlag alles" een geldige oplossing zijn.
"""

from __future__ import annotations

from src.core.tool_broker.risk_classifier import ToolRiskClassifier


def _uitvoerbare_tools() -> set[str]:
    """Alle namen die een agent daadwerkelijk kan laten uitvoeren.

    Dezelfde drie registries als `test_tool_policy_matches_the_tools.py`. Komt er een vierde
    registry bij, dan hoort hij hier ook -- dat is dezelfde afweging die die guard maakt.
    """
    from src.core.tool_broker.business_registry import BusinessToolRegistry
    from src.core.tool_broker.hr_registry import HRToolRegistry
    from src.core.tool_broker.local_registry import LocalToolRegistry

    return (
        set(BusinessToolRegistry.known_tool_names())
        | set(HRToolRegistry.known_tool_names())
        | set(LocalToolRegistry.known_tool_names())
    )


def test_every_executable_tool_has_an_explicit_risk_level() -> None:
    """Geen enkele uitvoerbare tool mag op de prefixregel of de default leunen."""
    classifier = ToolRiskClassifier()
    zonder_regel = sorted(
        naam for naam in _uitvoerbare_tools() if naam not in classifier._risk_levels
    )

    assert not zonder_regel, (
        "Deze uitvoerbare tools hebben geen eigen regel in `src/core/config/tool_risk_levels.yml` "
        f"en worden dus door een prefixregel of de default geclassificeerd: {zonder_regel}.\n\n"
        "Dat is geen theoretisch bezwaar: `tool_prefixes` bevat `local__: medium`, en MEDIUM "
        "opent de HITL-poort niet. Een `local__`-tool zonder eigen regel draait zonder dat een "
        "mens hem vooraf ziet. Zet elke tool expliciet in `tool_risk_levels`."
    )


def test_the_guard_is_not_vacuous() -> None:
    """De tweede richting: een lege toolverzameling maakt de guard hierboven zinloos.

    Breekt de import van een registry, of raakt `_TOOL_NAMES` leeg, dan is de assertie hierboven
    stil groen. Deze test faalt dan in plaats daarvan.
    """
    tools = _uitvoerbare_tools()

    assert len(tools) >= 10, (
        f"Slechts {len(tools)} uitvoerbare tools gevonden: {sorted(tools)}. Op 2026-08-11 waren "
        "het er elf. Is er een registry gesloopt, of leest deze guard de verkeerde bron? Zolang "
        "dit klopt niet, bewaakt de test hierboven niets."
    )
