"""AUDIT-008 regression tests: tool permission profile for the pilot skill skillsgaptraining.

Bevinding (HIGH/P1): config/tool_permissions.yml had exactly 1 agent profile
("copilot"). 0 of the 135/136 ALS skill IDs had a profile, so every TOOL_CALL
attempt by a skill hits ToolPermissionManager default-deny (ADR-015). The
system-prompt stopgap in every skill manifest ("without attempting a
TOOL_CALL") masked this by keeping skill execution honestly text-only, but no
skill could ever actually call a tool -- blocking D10's pilot.

These tests pin the fix:

- A concrete, least-privilege profile for the pilot skill "skillsgaptraining"
  exists and allows exactly the manifest-declared tools.
- Default-deny stays intact for the 134 skills WITHOUT a profile (ADR-015).
- The stopgap is removed for exactly this skill's manifest; all other
  manifests keep it.
- End-to-end: BaseSpecialistAgent.act() routes a valid TOOL_CALL to
  execute_tool with the skill's own agent_id, and the real permission layer
  (loaded from the real yml) no longer default-denies that call.
"""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
import yaml

from src.core.als.agents.skill_manifest import SkillManifest
from src.core.tool_broker.permission_manager import ToolPermissionManager

pytestmark = pytest.mark.unit

TOOL_PERMISSIONS_YML = Path("config/tool_permissions.yml")
SKILL_MANIFESTS_DIR = Path("src/core/als/agents/skills/manifests")
PILOT_SKILL_ID = "skillsgaptraining"
# Marker sentence of the Gate 2/3 stopgap (commit 33b4dd8c), present in all
# 135 skill manifests: forbids the LLM to ever attempt a TOOL_CALL.
STOPGAP_MARKER = "without attempting a TOOL_CALL"


def _load_manifest(skill_id: str) -> SkillManifest:
    return SkillManifest.load(SKILL_MANIFESTS_DIR / f"{skill_id}.yml")


@pytest.fixture()
def permission_manager() -> ToolPermissionManager:
    """The real permission layer, loaded from the real config/tool_permissions.yml."""
    return ToolPermissionManager(config_path=str(TOOL_PERMISSIONS_YML))


# ---------------------------------------------------------------------------
# Test 1.1-1.4 -- permission profile (least privilege, ADR-015)
# ---------------------------------------------------------------------------


class TestSkillsgaptrainingProfile:
    """Tests 1.1, 1.2, 1.3 and 1.4 from the day-4 brief."""

    def test_profile_exists_and_is_valid(self, permission_manager: ToolPermissionManager) -> None:
        """Test 1.1: the pilot skill has a profile with a concrete, non-empty
        allowed_tools list that matches the manifest declaration exactly."""
        with TOOL_PERMISSIONS_YML.open(encoding="utf-8") as f:
            data = yaml.safe_load(f)
        profiles = {p["agent_id"]: p for p in data.get("agent_profiles", [])}

        assert PILOT_SKILL_ID in profiles, (
            f"Geen permissieprofiel voor '{PILOT_SKILL_ID}' in {TOOL_PERMISSIONS_YML}; "
            "elke TOOL_CALL van de piloot-skill wordt default-deny'd (AUDIT-008)."
        )
        profile_tools = set(profiles[PILOT_SKILL_ID].get("allowed_tools") or [])
        manifest_tools = set(_load_manifest(PILOT_SKILL_ID).allowed_tools)

        assert profile_tools, "allowed_tools mag niet leeg zijn voor de piloot-skill"
        assert profile_tools == manifest_tools, (
            "Profiel en manifest moeten exact dezelfde toolset declareren "
            f"(least privilege). Profiel: {sorted(profile_tools)}, "
            f"manifest: {sorted(manifest_tools)}"
        )

    @pytest.mark.security()
    def test_fail_closed_for_skill_without_profile(
        self, permission_manager: ToolPermissionManager
    ) -> None:
        """Test 1.2 (pin): skills zonder profiel blijven default-deny (ADR-015).

        De 134 overige skills krijgen bewust GEEN profiel in deze sprint --
        hun stopgap blijft staan en de broker blijft fail-closed.
        """
        assert permission_manager.is_tool_allowed("burnoutcoach", "send_notification") is False
        assert permission_manager.is_tool_allowed("codereviewer", "read_data") is False
        assert permission_manager.is_tool_allowed("nonexistent_skill", "anything") is False

    def test_declared_tools_are_allowed(self, permission_manager: ToolPermissionManager) -> None:
        """Test 1.3: every tool declared by the manifest is allowed by the profile."""
        for tool in _load_manifest(PILOT_SKILL_ID).allowed_tools:
            assert permission_manager.is_tool_allowed(PILOT_SKILL_ID, tool) is True, (
                f"Tool '{tool}' staat in het manifest maar wordt door het profiel "
                "geweigerd -- de piloot kan zijn eigen declared tools niet gebruiken."
            )

    @pytest.mark.security()
    def test_undeclared_tools_are_denied(self, permission_manager: ToolPermissionManager) -> None:
        """Test 1.4: tools outside the profile are denied -- including tools that
        DO exist in the broker (delete_task) and classic dangerous names."""
        assert permission_manager.is_tool_allowed(PILOT_SKILL_ID, "delete_task") is False
        assert permission_manager.is_tool_allowed(PILOT_SKILL_ID, "admin_action") is False
        assert permission_manager.is_tool_allowed(PILOT_SKILL_ID, "execute_sql") is False


# ---------------------------------------------------------------------------
# Test 1.5 -- stopgap removal, scoped to exactly the pilot skill
# ---------------------------------------------------------------------------


class TestStopgapRemoval:
    """Test 1.5 from the day-4 brief."""

    def test_stopgap_removed_for_pilot_kept_for_others(self) -> None:
        """The pilot manifest no longer forbids TOOL_CALL; every other manifest
        keeps the stopgap until that skill gets its own profile (later sprint)."""
        pilot_prompt = _load_manifest(PILOT_SKILL_ID).system_prompt
        assert STOPGAP_MARKER not in pilot_prompt, (
            f"De system-prompt-stopgap staat nog in het manifest van '{PILOT_SKILL_ID}'; "
            "verwijderen zodra het permissieprofiel bestaat (AUDIT-008)."
        )

        other_prompt = _load_manifest("burnoutcoach").system_prompt
        assert STOPGAP_MARKER in other_prompt, (
            "De stopgap van een skill ZONDER profiel mag niet verwijderd zijn -- "
            "de 134 overige skills blijven bewust op de veilige stopgap."
        )


# ---------------------------------------------------------------------------
# Test 1.6 (behavioral) -- act() routes TOOL_CALL with the skill's own agent_id
# ---------------------------------------------------------------------------


class TestActEndToEnd:
    """Test 1.6 from the day-4 brief: the real skill class, real manifest,
    real permission layer; only the broker dispatch itself is mocked."""

    async def test_act_routes_tool_call_with_skill_agent_id(
        self, permission_manager: ToolPermissionManager
    ) -> None:
        from src.core.als.agents.skills.skillsgaptraining import SkillsGapTrainingSkill

        agent = SkillsGapTrainingSkill(tenant_id=1)
        # BE-AGT-042: act() voert niets uit zonder verantwoordelijke mens. Het uitvoerpad
        # zet dit normaal; deze test roept act() rechtstreeks aan.
        agent._initiated_by_user_id = 42
        # Sinds ADR-036 D4-002 is de piloot Annex III/HITL -- deze test toetst dat execute_tool
        # met de juiste agent_id wordt aangeroepen, niet de HITL-floor. Expliciet terugzetten.
        agent.config["human_in_the_loop"] = "hotl"
        agent.tools = AsyncMock()
        agent.tools.execute_tool = AsyncMock(return_value={"success": True})

        # `query_hr_database`: een tool die de piloot ECHT mag en die zijn broker ECHT kan
        # uitvoeren. Hier stond `send_notification`, op 2026-09-21 uit het manifest gehaald --
        # de manifest-filter weigert hem sindsdien voordat de broker hem ziet, en dan toetst
        # deze test niets meer over de agent-identiteit waarmee wordt gedispatcht.
        decision = 'TOOL_CALL: query_hr_database {"role": "Engineer"}'
        result = await agent.act(decision)

        # The agent-level filter (manifest allowed_tools) lets the call through...
        agent.tools.execute_tool.assert_awaited_once()
        kwargs = agent.tools.execute_tool.await_args.kwargs
        assert kwargs["tool_name"] == "query_hr_database"
        assert kwargs["agent_id"] == PILOT_SKILL_ID, (
            "execute_tool moet met de skill-ID als agent_id worden aangeroepen, "
            "niet met 'copilot' -- anders geldt het verkeerde permissieprofiel."
        )
        assert result.result_data["tool_calls"] == 1

        # ...and the broker-side permission layer no longer default-denies it.
        assert (
            permission_manager.is_tool_allowed(kwargs["agent_id"], kwargs["tool_name"]) is True
        ), (
            "De broker-permissielaag default-denyt deze aanroep nog: het profiel "
            "ontbreekt of deklareert deze tool niet (AUDIT-008)."
        )

    @pytest.mark.security()
    async def test_act_still_blocks_undeclared_tool_at_agent_level(self) -> None:
        """The manifest-level allowed_tools filter (fail-closed when non-empty)
        blocks a TOOL_CALL for an undeclared tool before the broker is reached."""
        from src.core.als.agents.skills.skillsgaptraining import SkillsGapTrainingSkill

        agent = SkillsGapTrainingSkill(tenant_id=1)
        agent.tools = AsyncMock()
        agent.tools.execute_tool = AsyncMock(return_value={"success": True})

        result = await agent.act('TOOL_CALL: delete_task {"task_id": "42"}')

        agent.tools.execute_tool.assert_not_awaited()
        assert result.result_data["tool_calls"] == 0
