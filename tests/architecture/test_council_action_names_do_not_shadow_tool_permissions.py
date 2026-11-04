"""Een copilot-actienaam mag geen toolrecht overschaduwen (ADR-036 OP-142).

`RBACService.user_has_scope_for()` raadpleegt eerst `_COUNCIL_ALLOWED_ACTION_TYPES` en geeft
`True` zodra de naam daarop staat. Pas daarna kijkt hij naar `tool_required_permission`. Voor
een naam die in BEIDE staat wint dus de copilot-lijst, en dan geldt het rechtenniveau van de
tool niet -- ook niet wanneer een AGENT hem aanroept.

Gemeten 2026-08-15: drie namen botsen (`create_task`, `update_task`, `delete_task`). Ze zijn
tegelijk copilot-chatactie en uitvoerbare tool in `BusinessToolRegistry`. Een gebruiker met
alleen leesrecht kan ze daarom via een agent laten draaien, terwijl `delete_task` in
`tool_required_permission` op `admin` staat.

**Waarom dit vandaag niet is opgelost.** De volgorde omdraaien verandert het COPILOT-pad: een
gebruiker met de rol `user` (alleen leesrecht) kan vandaag via de chat een taak aanmaken, en
zou dat dan niet meer kunnen. Dat is een gedragswijziging voor bestaande gebruikers, buiten de
scope van SP-COUNCIL-GATE-001, en hij hoort met een eigen meting en een eigen beslissing te
komen. `delete_task` heeft wel een tweede laag: risiconiveau `high` opent de HITL-poort, dus
een mens ziet hem vooraf.

**Groene guard met gedateerde uitzondering plus staleness-test**, conform de vier eisen in
`.claude/rules/quality-gates.md`:
1. De bevinding staat als OP-142 in ADR-036, met fase en prioriteit.
2. De uitzonderingslijst is gedateerd en heeft een reden per regel.
3. `test_the_known_shadowing_is_not_stale` wordt rood zodra een botsing is opgelost.
4. Mutatie-getest in beide richtingen (2026-08-15):
   - `"read_data"` aan `tool_required_permission` toegevoegd (staat al in de copilot-lijst)
     -> ROOD op de eerste test, met die naam in de melding.
   - `create_task` uit `tool_required_permission` gehaald -> ROOD op de staleness-test.
   - Ongewijzigd -> beide GROEN, en `test_the_guard_reads_both_sides` bewijst dat geen van
     beide verzamelingen leeg is (een lege verzameling maakt de eerste test trivially groen).
"""

from __future__ import annotations

from pathlib import Path

from src.core.auth.rbac import _COUNCIL_ALLOWED_ACTION_TYPES
from src.core.tool_broker.risk_classifier import ToolRiskClassifier

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROFIELEN = _REPO_ROOT / "config" / "tool_permissions.yml"

# Gedateerd 2026-08-16, reden per regel. Namen in het COPILOT-toolprofiel die NIET op de
# copilot-actielijst staan maar wel een toolrecht hebben gekregen: voor die namen is het
# gedrag op het copilot-pad VERANDERD door SP-COUNCIL-GATE-001.
KNOWN_COPILOT_BEHAVIOUR_CHANGES: dict[str, str] = {
    "list_tasks": (
        "stond in het copilot-toolprofiel maar niet in `_COUNCIL_ALLOWED_ACTION_TYPES`, dus "
        "de SecurityOfficer gaf er ALTIJD MISSING_SCOPE op -- de actie werkte simpelweg niet. "
        "Sinds 2026-08-16 vraagt hij `read` en werkt hij voor iedere rol met leesrecht. Een "
        "verruiming van kapot naar werkend, bewust behouden -- OP-142"
    ),
}


def _copilot_profielnamen() -> set[str]:
    """De toolnamen uit het copilot-profiel, uit de ECHTE configuratie gelezen."""
    import yaml

    data = yaml.safe_load(_PROFIELEN.read_text(encoding="utf-8-sig")) or {}
    for profiel in data.get("agent_profiles") or []:
        if profiel.get("agent_id") == "copilot":
            return {n for n in (profiel.get("allowed_tools") or []) if isinstance(n, str)}
    return set()


# Gedateerd 2026-08-15, reden per regel. Alleen namen die vandaag aantoonbaar botsen.
KNOWN_SHADOWED: dict[str, str] = {
    "create_task": (
        "copilot-chatactie EN BusinessToolRegistry-tool; omdraaien ontneemt een `user`-rol het "
        "aanmaken van taken via de chat -- eigen beslissing, OP-142"
    ),
    "update_task": ("idem create_task; zelfde gedragswijziging voor het copilot-pad -- OP-142"),
    "delete_task": (
        "idem, maar met een tweede laag: risiconiveau `high` opent de HITL-poort, dus een mens "
        "ziet hem vooraf -- OP-142"
    ),
}


def _overschaduwde_namen() -> set[str]:
    """Namen die in BEIDE bronnen staan; daar wint vandaag de copilot-lijst."""
    classifier = ToolRiskClassifier()
    return set(_COUNCIL_ALLOWED_ACTION_TYPES) & set(classifier._required_permissions)


def test_no_new_shadowed_action_names() -> None:
    """Nieuwe botsingen zijn geblokkeerd."""
    nieuw = sorted(_overschaduwde_namen() - set(KNOWN_SHADOWED))

    assert not nieuw, (
        f"Deze namen staan zowel in `_COUNCIL_ALLOWED_ACTION_TYPES` als in "
        f"`tool_required_permission`: {nieuw}.\n\n"
        "`user_has_scope_for()` raadpleegt de copilot-lijst EERST, dus het rechtenniveau van "
        "de tool geldt niet -- ook niet wanneer een agent hem aanroept. Kies er een van: geef "
        "de tool een andere naam dan de chat-actie, of los OP-142 op en haal de naam van de "
        "copilot-lijst."
    )


def test_the_known_shadowing_is_not_stale() -> None:
    """Een uitzondering die is opgelost MOET uit de lijst -- anders rot hij dicht."""
    opgelost = sorted(naam for naam in KNOWN_SHADOWED if naam not in _overschaduwde_namen())

    assert not opgelost, (
        f"Deze namen botsen niet meer en horen uit KNOWN_SHADOWED: {opgelost}. Laat staan wat "
        "nog botst; haal weg wat is opgelost, en werk de OP-142-regel in ADR-036 bij."
    )


def test_no_new_copilot_behaviour_change() -> None:
    """De OMGEKEERDE richting: een copilot-toolnaam die nu ineens een rechtencontrole krijgt.

    De eerste versie van deze guard keek maar een kant op -- naam op de copilot-ACTIElijst die
    het toolrecht overschaduwt. De spiegelvorm is even belangrijk: een naam in het
    copilot-TOOLPROFIEL die NIET op de actielijst staat, valt sinds SP-COUNCIL-GATE-001 door
    naar de nieuwe rechtencontrole. Dat verandert het gedrag van het copilot-pad, en zulke
    wijzigingen horen bewust te zijn (Gate 2-review ronde 2 betrapte `list_tasks` zo).
    """
    classifier = ToolRiskClassifier()
    veranderd = sorted(
        (_copilot_profielnamen() & set(classifier._required_permissions))
        - set(_COUNCIL_ALLOWED_ACTION_TYPES)
        - set(KNOWN_COPILOT_BEHAVIOUR_CHANGES)
    )

    assert not veranderd, (
        f"Deze copilot-toolnamen krijgen sinds deze wijziging een rechtencontrole die ze "
        f"eerder niet hadden: {veranderd}. Dat is een gedragswijziging voor bestaande "
        "gebruikers. Verantwoord hem in KNOWN_COPILOT_BEHAVIOUR_CHANGES, of zet de naam op "
        "`_COUNCIL_ALLOWED_ACTION_TYPES` als hij ongemoeid moet blijven."
    )


def test_the_known_behaviour_changes_are_not_stale() -> None:
    """Een verantwoorde wijziging die niet meer bestaat MOET uit de lijst."""
    classifier = ToolRiskClassifier()
    veranderd = (_copilot_profielnamen() & set(classifier._required_permissions)) - set(
        _COUNCIL_ALLOWED_ACTION_TYPES
    )
    opgelost = sorted(n for n in KNOWN_COPILOT_BEHAVIOUR_CHANGES if n not in veranderd)

    assert not opgelost, (
        f"Deze namen veranderen niet meer van gedrag: {opgelost}. Haal ze uit "
        "KNOWN_COPILOT_BEHAVIOUR_CHANGES."
    )


def test_the_guard_reads_both_sides() -> None:
    """De tweede richting: een lege bron maakt de eerste test trivially groen."""
    classifier = ToolRiskClassifier()

    assert len(_COUNCIL_ALLOWED_ACTION_TYPES) >= 10, (
        f"Slechts {len(_COUNCIL_ALLOWED_ACTION_TYPES)} copilot-acties gevonden."
    )
    assert len(classifier._required_permissions) >= 10, (
        f"Slechts {len(classifier._required_permissions)} toolrechten gelezen -- laadt de "
        "configuratie wel?"
    )
    assert len(_copilot_profielnamen()) >= 10, (
        f"Slechts {len(_copilot_profielnamen())} namen in het copilot-toolprofiel gevonden. "
        "Op 2026-08-16 waren het er 17; leest de guard het profiel wel?"
    )
