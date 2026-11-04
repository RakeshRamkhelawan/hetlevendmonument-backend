"""Een HIGH-risk tool in een agentprofiel vraagt een gedateerde, benoemde afweging.

**Waarom deze guard er is, met de meting.** Op 2026-09-21 is `schedule_training` van een naam in
een manifest een echte SCHRIJFtool op personeelsdata geworden. Tot die dag kostte het niets om
die naam te declareren -- de broker weigerde hem toch. Die kostenloosheid is verdwenen, en een
Gate 2-reviewer mat waar dat naartoe wijst: die naam staat in VEERTIEN andere skill-manifesten
(`breakreminder`, `burnoutcoach`, `digitaldetox`, `taskmanager`, ...). Vandaag zijn die inert
omdat die skills geen broker-profiel hebben en `ToolPermissionManager` default-deny is. Maar
`config/tool_permissions.yml` zegt zelf dat de overige skills er "in a later sprint" elk een
krijgen, en de bestaande guard (`test_als_skills_tool_permissions.py`) eist alleen dat een
profiel een DEELVERZAMELING van het manifest is.

Op de dag dat `breakreminder` een profiel krijgt dat zijn manifest volgt, heeft een
pauzeherinnering dus schrijfrecht op `employee_trainings` -- met een HITL-poort ervoor die door
een mens wordt bediend die niet weet waarom een pauzeherinnering een training toewijst. AI Act
artikel 14 gaat over BETEKENISVOL toezicht, niet over de aanwezigheid van een knop.

Deze guard verplaatst dat van "iemand moet eraan denken" naar "de test wordt rood".

**Waarom niet de veertien manifesten leegmaken.** Dat is de andere kant van dezelfde bevinding en
het is gedeeltelijk gedaan: `DEPARTMENT_TOOLS["hr_culture"]` in `scripts/generate_skill_manifests.py`
bevat `schedule_training` niet meer, dus een regeneratie haalt de naam daar weg. De manifesten op
schijf regenereren raakt 134 bestanden en is een eigen wijziging. Tot die tijd is het PROFIEL de
plek waar het echt telt, want zonder profiel kan geen enkele skill de tool aanroepen.

**De eerste versie van deze guard was BLIND, en dat is gemeten (Gate 2 ronde 2, 2026-09-21).**
Hij sloeg elk profiel over dat geen `namespace: broker_tool` had:

```python
if profiel.get("namespace") != "broker_tool":
    continue
```

`ToolPermissionManager` kent `namespace` niet -- dat veld bestaat om LEZERS te helpen
onderscheiden welke namen echte tools zijn (`test_tool_profile_namespaces.py`). Het `copilot`-
profiel staat op `council_action` en werd dus overgeslagen, terwijl `copilot` de DEFAULT
uitvoerende identiteit is waarmee `hitl_router._voer_goedgekeurde_actie_uit` `execute_tool`
aanroept. Dat profiel hield al een HIGH broker-tool (`delete_task`) zonder gedateerde reden, en
een mutatie die `schedule_training` aan `copilot` gaf bleef GROEN.

Dat is precies de aanscherping van 2026-09-18 die ik niet had toegepast: muteer IN de sleutel die
al wordt vrijgesteld. Mijn mutatie zat binnen de verzameling die de filter al doorliet.

De filter is weg. Wat de verzameling nu begrenst is `_high_tools()`: alleen namen die
DAADWERKELIJK in een registry zitten EN als HIGH classificeren. Een council-actienaam die geen
tool is (`write_data`, `admin_action`) valt daar niet onder -- die kan `execute_tool` niet
bereiken, en er een gedateerde reden voor eisen zou de lijst vullen met dingen die geen
bevoegdheid zijn.

**Mutatiebewijs (2026-09-21, beide richtingen), met `scripts/mutation_harness.py`:**

1. `schedule_training` toegevoegd aan een tweede broker_tool-profiel in
   `config/tool_permissions.yml` -> ROOD, met dat agent_id in de melding.
1b. `schedule_training` toegevoegd aan het `copilot`-profiel (namespace `council_action`) ->
   ROOD. Dit is de mutatie waar de eerste versie groen op bleef.
2. `skillsgaptraining` uit `TOEGESTANE_HIGH_TOOLGEBRUIKERS` gehaald -> ROOD; de bestaande,
   afgewogen uitzondering moet ook echt genoemd staan.
3. Ongemuteerd -> GROEN (de tegenrichting: een profiel met alleen leestools blijft toegestaan,
   en de bestaande uitzondering hangt niet).
4. `schedule_training: high` -> `medium` in `tool_risk_levels.yml` -> GROEN hier, en ROOD in
   `tests/unit/tool_broker/test_hr_schedule_training.py`. Bewust: deze guard gaat over WIE een
   HIGH-tool mag hebben, niet over de vraag of de tool HIGH hoort te zijn -- dat is daar belegd.
"""

from __future__ import annotations

from pathlib import Path

import yaml

CONFIG = Path("config/tool_permissions.yml")

#: Per agent_id de HIGH-risk tools die hij MAG hebben, met datum en reden per regel.
#:
#: Een regel hier is een afweging die iemand heeft opgeschreven, niet een lijst om aan te vullen
#: als een test rood wordt. Voor elke nieuwe regel geldt de vraag uit
#: `docs/AUDIT-TO-FIX-WORKFLOW.md`: wat doet deze agent dat deze bevoegdheid AANTOONBAAR nodig
#: heeft, en wie ziet het als hij het verkeerd doet?
TOEGESTANE_HIGH_TOOLGEBRUIKERS: dict[str, dict[str, str]] = {
    "copilot": {
        "delete_task": (
            "Bestond al voor deze guard (ADR-015 classificeert `delete_task` als HIGH omdat hij "
            "destructief is, en de copilot voert hem uit namens de mens die er in de chat om "
            "vraagt). Deze regel is een VASTLEGGING van de bestaande stand, niet een nieuwe "
            "toekenning -- 2026-09-21, toen de guard voor het eerst ook naar dit profiel keek. "
            "Let op de bekende botsing OP-142: `delete_task` staat ook in "
            "`_COUNCIL_ALLOWED_ACTION_TYPES`, en die lijst wordt eerst geraadpleegd."
        )
    },
    "skillsgaptraining": {
        "schedule_training": (
            "2026-09-21 -- de piloot-skill uit ADR-036 D10. Zijn hele opdracht is een "
            "vaardighedenkloof meten en de bijbehorende training toewijzen; zonder deze tool "
            "eindigt de keten in een rapport. HIGH en dus achter de HITL-poort, en het "
            "ticket noemt de tool per aanroep."
        )
    },
}


def _profielen() -> list[dict[str, object]]:
    data = yaml.safe_load(CONFIG.read_text(encoding="utf-8")) or {}
    return [p for p in (data.get("agent_profiles") or []) if isinstance(p, dict)]


def _high_tools() -> set[str]:
    """De tools die als HIGH classificeren -- uit de classifier, niet uit een eigen lijst."""
    from src.core.tool_broker.business_registry import BusinessToolRegistry
    from src.core.tool_broker.hr_registry import HRToolRegistry
    from src.core.tool_broker.local_registry import LocalToolRegistry
    from src.core.tool_broker.risk_classifier import ToolRiskClassifier, ToolRiskLevel

    classifier = ToolRiskClassifier()
    uitvoerbaar = (
        BusinessToolRegistry.known_tool_names()
        | HRToolRegistry.known_tool_names()
        | LocalToolRegistry.known_tool_names()
    )
    return {naam for naam in uitvoerbaar if classifier.classify(naam) is ToolRiskLevel.HIGH}


def test_no_profile_gains_a_high_risk_tool_without_a_dated_reason() -> None:
    """Een HIGH-tool in een broker_tool-profiel staat in de lijst hierboven, of de test faalt."""
    high = _high_tools()
    ongedekt: list[str] = []

    for profiel in _profielen():
        # GEEN filter op `namespace`. Zie de moduledocstring: die filter maakte de guard blind
        # op precies het profiel dat de default uitvoerende identiteit is.
        agent_id = str(profiel.get("agent_id"))
        toegestaan = TOEGESTANE_HIGH_TOOLGEBRUIKERS.get(agent_id, {})
        for tool in profiel.get("allowed_tools") or []:  # type: ignore[union-attr]
            naam = str(tool)
            if naam in high and naam not in toegestaan:
                ongedekt.append(f"{agent_id}: {naam}")

    assert not ongedekt, (
        "Deze profielen geven een HIGH-risk tool zonder dat er een afweging bij staat:\n"
        + "\n".join(f"  - {u}" for u in sorted(ongedekt))
        + "\n\nHIGH betekent: onomkeerbaar, naar buiten, of een mutatie op gevoelige data. "
        "Voeg de agent met datum en reden toe aan TOEGESTANE_HIGH_TOOLGEBRUIKERS in deze "
        "test, of haal de tool uit het profiel. Let op dat de bestaande HITL-poort geen "
        "argument is: die vraagt een mens om ja te zeggen op een tool die hij in deze "
        "context niet verwacht."
    )


def test_the_dated_reasons_are_not_stale() -> None:
    """Een uitzondering voor een profiel dat de tool niet meer heeft, is dode ballast."""
    werkelijk: dict[str, set[str]] = {
        str(p.get("agent_id")): {str(t) for t in (p.get("allowed_tools") or [])}  # type: ignore[union-attr]
        for p in _profielen()
    }

    verouderd = [
        f"{agent_id}: {tool}"
        for agent_id, tools in TOEGESTANE_HIGH_TOOLGEBRUIKERS.items()
        for tool in tools
        if tool not in werkelijk.get(agent_id, set())
    ]

    assert not verouderd, (
        "Deze uitzonderingen gelden een tool die het profiel niet meer declareert; haal ze "
        f"weg: {sorted(verouderd)}"
    )


def test_the_guard_reads_a_non_empty_set_of_high_tools() -> None:
    """De tegenrichting: zonder HIGH-tools is de eerste assertie trivially groen.

    Breekt de classifier of de registry-import, dan vindt `_high_tools()` niets en bewaakt de
    test hierboven niets meer -- stil. Gemeten 2026-09-21: er zijn er drie
    (`delete_task`, `local__send_email`, `schedule_training`).
    """
    high = _high_tools()

    assert len(high) >= 3, (
        f"Slechts {len(high)} HIGH-tools gevonden: {sorted(high)}. Op 2026-09-21 waren het er "
        "drie. Leest deze guard nog de echte classifier?"
    )
    assert "schedule_training" in high
