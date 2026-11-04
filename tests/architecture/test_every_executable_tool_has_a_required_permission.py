"""Elke uitvoerbare tool zegt welk MENSENRECHT hij vereist (SP-COUNCIL-GATE-001).

Zusterguard van `test_every_executable_tool_has_a_risk_level.py`. Die bewaakt hoeveel toezicht
een tool krijgt; deze bewaakt WIE hem mag laten draaien.

**Waarom hij moet bestaan.** `ToolRiskClassifier.required_permission()` geeft `None` voor een
tool zonder regel, en `RBACService.user_has_scope_for()` weigert dan voor iedereen -- ook voor
een beheerder. Dat is de veilige kant, maar het betekent ook dat een vergeten regel een tool
volledig onbruikbaar maakt zonder dat iemand het merkt tot een gebruiker klaagt. Deze guard
maakt dat zichtbaar op het moment van toevoegen.

**Waarom geen terugval op "het strengste bestaande recht".** Dat leek eerst netter en was fout:
met `default_required_permission: admin` mag een beheerder ELKE ongeclassificeerde tool draaien,
en dan opent een nieuwe tool zichzelf zolang niemand eraan denkt hem te classificeren. De test
`test_an_unknown_tool_is_refused_even_for_an_admin` betrapte dat.

**Mutatietest (2026-08-15), een regel per richting:**
1. `query_hr_database: admin` uit `tool_required_permission` gehaald -> ROOD, met die naam in
   de melding.
2. Vervangen door een prefixregel-achtige truc (`query_hr_: admin` toegevoegd, exacte regel weg)
   -> nog steeds ROOD. `required_permission()` kent bewust geen prefix-terugval; de guard laat
   zich daar dus niet mee afkopen.
3. Andere richting: ongewijzigd -> GROEN, en `_uitvoerbare_tools()` is aantoonbaar niet leeg
   (`test_the_guard_is_not_vacuous`). Zonder die helft zou "weiger alles" een oplossing zijn.
4. Een rechtennaam die niet in `TOOL_RECHTEN` bestaat (`tools:admin` -> `tools:beheerder`, of
   een wildcard `*:*`) -> ROOD via `test_every_required_permission_is_a_real_permission`
   (OP-143: waarden zijn `resource:actie`).
"""

from __future__ import annotations

from src.core.auth.rbac import TOOL_RECHTEN
from src.core.tool_broker.risk_classifier import ToolRiskClassifier


def _uitvoerbare_tools() -> set[str]:
    """Alle namen die een agent daadwerkelijk kan laten uitvoeren.

    Dezelfde drie registries als `test_every_executable_tool_has_a_risk_level.py`. Komt er een
    vierde bij, dan hoort hij in beide guards.
    """
    from src.core.tool_broker.business_registry import BusinessToolRegistry
    from src.core.tool_broker.hr_registry import HRToolRegistry
    from src.core.tool_broker.local_registry import LocalToolRegistry

    return (
        set(BusinessToolRegistry.known_tool_names())
        | set(HRToolRegistry.known_tool_names())
        | set(LocalToolRegistry.known_tool_names())
    )


def test_every_executable_tool_has_an_explicit_required_permission() -> None:
    """Geen enkele uitvoerbare tool mag zonder regel blijven."""
    classifier = ToolRiskClassifier()
    zonder_regel = sorted(
        naam for naam in _uitvoerbare_tools() if classifier.required_permission(naam) is None
    )

    assert not zonder_regel, (
        "Deze uitvoerbare tools staan niet in `tool_required_permission` in "
        f"`src/core/config/tool_risk_levels.yml`: {zonder_regel}.\n\n"
        "Gevolg in productie: `user_has_scope_for()` weigert ze voor IEDEREEN, ook voor een "
        "beheerder, en de SecurityOfficer geeft MISSING_SCOPE. De tool is dan onbruikbaar. Zet "
        "er een recht bij, met de reden erbij zoals de andere regels dat doen."
    )


def test_every_required_permission_is_a_real_permission() -> None:
    """Een rechtennaam die niet bestaat is hetzelfde als geen recht -- maar stiller.

    `user_has_scope_for()` weigert een waarde die niet in `TOOL_RECHTEN` staat. Dat is veilig
    maar onvindbaar: de tool werkt gewoon niet en de configuratie ziet er goed uit. Deze test
    maakt de typefout zichtbaar waar hij gemaakt wordt. Een wildcard (`*:*`) hoort er ook niet in.
    """
    classifier = ToolRiskClassifier()
    onbekend = sorted(
        f"{naam}={recht}"
        for naam, recht in classifier._required_permissions.items()
        if recht not in TOOL_RECHTEN
    )

    assert not onbekend, (
        f"Deze regels noemen een recht dat niet in `TOOL_RECHTEN` staat: {onbekend}. "
        f"Geldige waarden (`resource:actie`): {sorted(TOOL_RECHTEN)}."
    )


def test_every_tool_right_is_used_by_at_least_one_tool() -> None:
    """Een recht in `TOOL_RECHTEN` dat geen enkele tool vraagt is dode configuratie."""
    classifier = ToolRiskClassifier()
    gebruikt = frozenset(classifier._required_permissions.values())
    ongebruikt = sorted(TOOL_RECHTEN - gebruikt)

    assert not ongebruikt, (
        f"Deze rechten staan in TOOL_RECHTEN maar geen enkele tool vraagt ze: {ongebruikt}. "
        "Haal ze weg of koppel een tool."
    )


def test_the_guard_is_not_vacuous() -> None:
    """De tweede richting: een lege toolverzameling maakt de guard hierboven zinloos."""
    tools = _uitvoerbare_tools()

    assert len(tools) >= 10, (
        f"Slechts {len(tools)} uitvoerbare tools gevonden: {sorted(tools)}. Op 2026-08-15 waren "
        "het er elf. Is er een registry gesloopt, of leest deze guard de verkeerde bron? Zolang "
        "dit niet klopt, bewaakt de test hierboven niets."
    )
