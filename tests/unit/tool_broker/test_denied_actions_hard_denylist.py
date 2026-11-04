"""D5 -- harde denylist `denied_actions`, gehandhaafd VOOR de Council (BE-AGT-038).

ADR-036 D5: elk agent-profiel krijgt naast de allow-list een `denied_actions`-veld: een
harde, per-agent denylist die door `ToolPermissionManager` wordt gecontroleerd **voordat de
Council-poort ooit bereikt wordt**. Geen mens kan dit overrulen -- dit is de
"nooit aanraken"-laag uit de vijf bevoegdheidsniveaus (AI Act art. 14).

Waarom "voor de Council" een echte eis is en niet een detail: als de Council er eerst iets
van mag vinden, is de denylist per definitie overrulebaar en dus geen "nooit aanraken".
De volgorde in `ToolBrokerService.execute_tool` is daarom onderdeel van het contract:

    0.  permissiecheck  (is_tool_allowed)      <-- hier hoort denied_actions
    0a. categorievalidatie
    1.  risk-classificatie -> HITL/Council-poort

Reconciliatie met het bestaande `denied_tools` (D5, verplicht): `denied_tools` is de
legacy-alias/deelverzameling, `denied_actions` is leidend voor nieuwe profielen. Beide
worden gehandhaafd -- de UNIE is verboden -- zodat een bestaand profiel niet stilzwijgend
losser wordt wanneer iemand alleen `denied_actions` invult.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from src.core.tool_broker.permission_manager import AgentToolProfile, ToolPermissionManager

PILOT = "skillsgaptraining"


@pytest.fixture
def config_with_denied_actions(tmp_path: Path) -> str:
    """Profiel waarin een tool ZOWEL in allowed_tools als in denied_actions staat."""
    config = tmp_path / "tool_permissions.yml"
    config.write_text(
        textwrap.dedent("""
            agent_profiles:
              - agent_id: pilot_agent
                allowed_tools:
                  - query_hr_database
                  - send_notification
                  - schedule_training
                denied_actions:
                  - send_notification
                denied_tools: []
                max_tools: 10
              - agent_id: legacy_agent
                allowed_tools:
                  - query_hr_database
                  - send_notification
                denied_tools:
                  - send_notification
                max_tools: 10
            """).strip(),
        encoding="utf-8",
    )
    return str(config)


@pytest.mark.unit
@pytest.mark.security
class TestDeniedActionsIsAHardDenylist:
    def test_profile_carries_denied_actions(self) -> None:
        """Het veld moet bestaan op het profiel, anders kan het nooit gehandhaafd worden."""
        profile = AgentToolProfile(agent_id="x", denied_actions=["dangerous_action"])
        assert profile.denied_actions == ["dangerous_action"]

    def test_denied_action_wins_from_allowed_tools(self, config_with_denied_actions: str) -> None:
        """Staat een tool in beide lijsten, dan wint de denylist. Altijd."""
        manager = ToolPermissionManager(config_path=config_with_denied_actions)

        assert manager.is_tool_allowed("pilot_agent", "query_hr_database") is True
        assert manager.is_tool_allowed("pilot_agent", "send_notification") is False, (
            "send_notification staat in denied_actions en moet geweigerd worden, ook al "
            "staat hij in allowed_tools -- anders is 'nooit aanraken' geen harde laag"
        )

    def test_denied_tools_stays_enforced(self, config_with_denied_actions: str) -> None:
        """Reconciliatie: het legacy-veld blijft werken naast het nieuwe."""
        manager = ToolPermissionManager(config_path=config_with_denied_actions)

        assert manager.is_tool_allowed("legacy_agent", "query_hr_database") is True
        assert manager.is_tool_allowed("legacy_agent", "send_notification") is False, (
            "denied_tools mag niet stilzwijgend zijn kracht verliezen doordat "
            "denied_actions is geintroduceerd -- dat zou bestaande profielen losser maken"
        )

    def test_unknown_agent_still_default_denied(self, config_with_denied_actions: str) -> None:
        """Bestaand fail-closed gedrag mag niet wegvallen (ADR-015)."""
        manager = ToolPermissionManager(config_path=config_with_denied_actions)
        assert manager.is_tool_allowed("", "query_hr_database") is False
        assert manager.is_tool_allowed("unknown_agent", "query_hr_database") is False

    def test_missing_denied_actions_defaults_to_empty(self, tmp_path: Path) -> None:
        """Een profiel zonder het veld blijft werken -- geen KeyError, geen crash."""
        config = tmp_path / "p.yml"
        config.write_text(
            "agent_profiles:\n  - agent_id: a\n    allowed_tools: [t1]\n    max_tools: 5\n",
            encoding="utf-8",
        )
        manager = ToolPermissionManager(config_path=str(config))
        assert manager.is_tool_allowed("a", "t1") is True


@pytest.mark.unit
@pytest.mark.security
class TestEnforcementHappensBeforeTheCouncil:
    """De volgorde is onderdeel van het contract, niet een implementatiedetail."""

    def test_permission_check_precedes_risk_and_council_gating(self) -> None:
        """In execute_tool staat de permissiecheck voor de risk-classificatie.

        Bewust op broncodeniveau getoetst: een gedragstest zou de hele broker moeten
        opzetten (resilience, circuit breaker, HITL-store) om iets aan te tonen dat
        puur over VOLGORDE gaat. Deze test faalt zodra iemand de permissiecheck naar
        beneden verplaatst -- en dan is de harde denylist stilzwijgend overrulebaar
        geworden.
        """
        source = Path("src/core/tool_broker/service.py").read_text(encoding="utf-8")
        body = source.split("async def execute_tool")[1]

        permission_at = body.index("is_tool_allowed")
        risk_at = body.index("risk_classifier.classify")

        assert permission_at < risk_at, (
            "De permissiecheck (is_tool_allowed) moet VOOR de risk-classificatie en de "
            "daaropvolgende HITL/Council-poort staan. Anders kan een menselijke "
            "goedkeuring een 'nooit aanraken'-actie alsnog doorlaten (ADR-036 D5, "
            "AI Act art. 14)."
        )

    def test_denied_action_blocks_without_reaching_the_broker(
        self, config_with_denied_actions: str
    ) -> None:
        """Een geweigerde actie mag nooit tot een tool-aanroep leiden."""
        manager = ToolPermissionManager(config_path=config_with_denied_actions)
        # is_tool_allowed is de enige poort die execute_tool op stap 0 raadpleegt;
        # False betekent dat execute_tool afbreekt voordat er iets wordt uitgevoerd.
        assert manager.is_tool_allowed("pilot_agent", "send_notification") is False


@pytest.mark.unit
@pytest.mark.security
class TestPilotProfileHasARealDenylist:
    def test_pilot_profile_declares_denied_actions(self) -> None:
        """De piloot-skill moet een concrete 'nooit aanraken'-lijst hebben.

        Een leeg veld zou D5 op papier invullen zonder dat er iets wordt afgedwongen.
        """
        manager = ToolPermissionManager()
        profile = manager._agent_profiles.get(PILOT)

        assert profile is not None, f"{PILOT} heeft geen permissieprofiel (AUDIT-008)"
        assert profile.denied_actions, (
            f"{PILOT} heeft een leeg denied_actions-veld. D5 vraagt een echte harde "
            "denylist, geen placeholder."
        )

    def test_pilot_denied_actions_are_not_in_allowed_tools(self) -> None:
        """Een profiel mag zichzelf niet tegenspreken."""
        manager = ToolPermissionManager()
        profile = manager._agent_profiles.get(PILOT)
        assert profile is not None

        overlap = set(profile.denied_actions) & set(profile.allowed_tools)
        assert not overlap, (
            f"{PILOT} heeft {sorted(overlap)} in zowel allowed_tools als denied_actions. "
            "De denylist wint weliswaar, maar een profiel dat zichzelf tegenspreekt is "
            "een leesfout die wacht om te gebeuren."
        )

    def test_pilot_denied_actions_survive_a_widened_allowlist(self) -> None:
        """De ECHTE piloot-acties blijven geweigerd als de allowlist wordt verruimd.

        Waarom niet simpelweg `is_tool_allowed(PILOT, actie) is False` toetsen: die
        assertie is groen ook zonder denylist, want de acties staan niet in `allowed_tools`
        en de allowlist weigert ze dan toch al. Zo'n test bewijst niets over D5 -- hij is
        vacuum. Aangetoond met een mutatietest: het weghalen van de `denied_actions`-check
        liet die versie gewoon slagen.

        Dit is het scenario waarin de denylist er wel toe doet: iemand verruimt de allowlist
        (of het skill-manifest) en verwacht dat de "nooit aanraken"-laag stand houdt. De
        evaluatieset van dag 1 dekt dat niet: taak D1 en D2 gebruiken weliswaar
        `delete_employee_record` en `update_salary`, maar bewijzen alleen dat de
        MANIFEST-filter ze tegenhoudt -- een andere laag, die niets van de denylist weet.
        """
        real = ToolPermissionManager()._agent_profiles.get(PILOT)
        assert real is not None
        assert real.denied_actions, "voorwaarde voor deze test: het profiel heeft een denylist"

        manager = ToolPermissionManager()
        manager._agent_profiles[PILOT] = AgentToolProfile(
            agent_id=PILOT,
            # De verruiming: elke verboden actie staat nu OOK in de allowlist.
            allowed_tools=[*real.allowed_tools, *real.denied_actions],
            denied_tools=list(real.denied_tools),
            denied_actions=list(real.denied_actions),
            max_tools=real.max_tools,
        )

        for action in real.denied_actions:
            assert manager.is_tool_allowed(PILOT, action) is False, (
                f"{PILOT} mag '{action}' niet uitvoeren, ook niet nu die actie in de "
                "allowlist staat. De 'nooit aanraken'-laag moet een verruiming van de "
                "allowlist overleven (ADR-036 D5, AI Act art. 14)."
            )

        assert (
            manager.is_tool_allowed(PILOT, "query_hr_database") is True
        ), "regressiecontrole: de verruiming mag de normale allowlist niet slopen"
