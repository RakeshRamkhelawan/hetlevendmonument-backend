"""Unit tests for ToolPermissionManager.

Uses temporary YAML configs (tmp_path fixture) — no real config files needed.
"""

import yaml
import pytest
from pathlib import Path

from src.core.tool_broker.permission_manager import AgentToolProfile, ToolPermissionManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_config(tmp_path: Path, data: dict) -> str:
    """Serialize data to YAML, write to tmp_path, return path string."""
    config_file = tmp_path / "tool_permissions.yml"
    config_file.write_text(yaml.dump(data), encoding="utf-8")
    return str(config_file)


def _single_profile(
    tmp_path: Path,
    agent_id: str,
    allowed_tools: list,
    denied_tools: list | None = None,
    max_tools: int = 10,
) -> ToolPermissionManager:
    """Build a ToolPermissionManager with exactly one profile."""
    data = {
        "agent_profiles": [
            {
                "agent_id": agent_id,
                "allowed_tools": allowed_tools,
                "denied_tools": denied_tools or [],
                "max_tools": max_tools,
            }
        ]
    }
    return ToolPermissionManager(config_path=_write_config(tmp_path, data))


# ---------------------------------------------------------------------------
# AgentToolProfile dataclass
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
class TestAgentToolProfile:
    def test_defaults(self):
        profile = AgentToolProfile(agent_id="my-agent")
        assert profile.agent_id == "my-agent"
        assert profile.allowed_tools == []
        assert profile.denied_tools == []
        assert profile.max_tools == 10

    def test_custom_values(self):
        profile = AgentToolProfile(
            agent_id="my-agent",
            allowed_tools=["local__read_file"],
            denied_tools=["local__run_shell"],
            max_tools=5,
        )
        assert profile.allowed_tools == ["local__read_file"]
        assert profile.denied_tools == ["local__run_shell"]
        assert profile.max_tools == 5


# ---------------------------------------------------------------------------
# validate_agent_profile — happy paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
class TestValidateAgentProfileHappy:
    def test_valid_tools_return_no_warnings(self, tmp_path):
        manager = _single_profile(
            tmp_path, "agent-1", ["local__read_file", "serena__search"], max_tools=10
        )
        warnings = manager.validate_agent_profile("agent-1", ["local__read_file", "serena__search"])
        assert warnings == []

    def test_empty_allowed_tools_is_valid_when_profile_exists(self, tmp_path):
        manager = _single_profile(tmp_path, "agent-1", [], max_tools=5)
        warnings = manager.validate_agent_profile("agent-1", [])
        assert warnings == []

    def test_tools_below_max_returns_no_warnings(self, tmp_path):
        manager = _single_profile(tmp_path, "agent-1", ["t1", "t2"], max_tools=5)
        warnings = manager.validate_agent_profile("agent-1", ["t1", "t2"])
        assert warnings == []


# ---------------------------------------------------------------------------
# validate_agent_profile — unhappy paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
class TestValidateAgentProfileUnhappy:
    def test_too_many_tools_returns_warning(self, tmp_path):
        manager = _single_profile(tmp_path, "agent-1", ["t1", "t2", "t3"], max_tools=2)
        warnings = manager.validate_agent_profile("agent-1", ["t1", "t2", "t3"])
        assert len(warnings) >= 1
        assert any("least-privilege violation" in w for w in warnings)

    def test_denied_tool_in_allowed_list_returns_warning(self, tmp_path):
        manager = _single_profile(
            tmp_path,
            "agent-1",
            allowed_tools=["local__read_file", "local__run_shell"],
            denied_tools=["local__run_shell"],
        )
        warnings = manager.validate_agent_profile(
            "agent-1", ["local__read_file", "local__run_shell"]
        )
        assert any("denied tool" in w for w in warnings)

    def test_no_profile_returns_single_warning(self, tmp_path):
        manager = ToolPermissionManager(config_path=_write_config(tmp_path, {"agent_profiles": []}))
        warnings = manager.validate_agent_profile("unknown-agent", ["local__read_file"])
        assert len(warnings) == 1
        assert "No profile" in warnings[0]

    def test_multiple_denied_tools_each_produce_a_warning(self, tmp_path):
        manager = _single_profile(
            tmp_path,
            "agent-1",
            allowed_tools=["local__run_shell", "local__send_email"],
            denied_tools=["local__run_shell", "local__send_email"],
        )
        warnings = manager.validate_agent_profile(
            "agent-1", ["local__run_shell", "local__send_email"]
        )
        # One warning per denied-but-present tool
        assert len([w for w in warnings if "denied tool" in w]) == 2


# ---------------------------------------------------------------------------
# is_tool_allowed — happy paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
class TestIsToolAllowedHappy:
    def test_tool_in_allowed_list_returns_true(self, tmp_path):
        manager = _single_profile(tmp_path, "agent-1", ["local__read_file", "serena__search"])
        assert manager.is_tool_allowed("agent-1", "local__read_file") is True

    def test_no_profile_returns_false_default_deny(self, tmp_path):
        # ADR-015 default-deny: unknown agents must not access any tools (RC-007 fix).
        manager = ToolPermissionManager(config_path=_write_config(tmp_path, {"agent_profiles": []}))
        assert manager.is_tool_allowed("unknown-agent", "local__read_file") is False


# ---------------------------------------------------------------------------
# is_tool_allowed — unhappy paths
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
class TestIsToolAllowedUnhappy:
    def test_tool_not_in_allowed_list_returns_false(self, tmp_path):
        manager = _single_profile(tmp_path, "agent-1", ["local__read_file"])
        assert manager.is_tool_allowed("agent-1", "local__run_shell") is False

    def test_denied_tool_returns_false_even_if_in_allowed(self, tmp_path):
        manager = _single_profile(
            tmp_path,
            "agent-1",
            allowed_tools=["local__read_file", "local__run_shell"],
            denied_tools=["local__run_shell"],
        )
        assert manager.is_tool_allowed("agent-1", "local__run_shell") is False

    def test_denied_takes_priority_over_allowed(self, tmp_path):
        # Explicit deny always wins — defense-in-depth
        manager = _single_profile(
            tmp_path,
            "agent-1",
            allowed_tools=["local__run_shell"],
            denied_tools=["local__run_shell"],
        )
        assert manager.is_tool_allowed("agent-1", "local__run_shell") is False


# ---------------------------------------------------------------------------
# get_excessive_tools_report
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
class TestGetExcessiveToolsReport:
    def test_no_agents_exceed_max_returns_empty_report(self, tmp_path):
        manager = _single_profile(tmp_path, "agent-1", ["local__read_file"], max_tools=10)
        assert manager.get_excessive_tools_report() == {}

    def test_agent_exceeding_max_appears_in_report(self, tmp_path):
        manager = _single_profile(tmp_path, "agent-1", ["t1", "t2", "t3"], max_tools=2)
        report = manager.get_excessive_tools_report()
        assert "agent-1" in report
        assert "3 tools" in report["agent-1"][0]

    def test_multiple_agents_only_excessive_ones_appear(self, tmp_path):
        data = {
            "agent_profiles": [
                {
                    "agent_id": "lean-agent",
                    "allowed_tools": ["t1"],
                    "denied_tools": [],
                    "max_tools": 5,
                },
                {
                    "agent_id": "fat-agent",
                    "allowed_tools": ["t1", "t2", "t3"],
                    "denied_tools": [],
                    "max_tools": 2,
                },
            ]
        }
        manager = ToolPermissionManager(config_path=_write_config(tmp_path, data))
        report = manager.get_excessive_tools_report()
        assert "lean-agent" not in report
        assert "fat-agent" in report


# ---------------------------------------------------------------------------
# Config loading edge cases
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
class TestConfigLoading:
    def test_missing_config_file_produces_empty_profiles(self, tmp_path):
        manager = ToolPermissionManager(config_path=str(tmp_path / "nonexistent.yml"))
        assert manager._agent_profiles == {}
        # ADR-015 default-deny: no profile = denied (RC-007 fix)
        assert manager.is_tool_allowed("any-agent", "any-tool") is False

    def test_empty_yaml_file_produces_empty_profiles(self, tmp_path):
        config_file = tmp_path / "tool_permissions.yml"
        config_file.write_text("", encoding="utf-8")
        manager = ToolPermissionManager(config_path=str(config_file))
        assert manager._agent_profiles == {}

    def test_multi_agent_config_loads_all_profiles(self, tmp_path):
        data = {
            "agent_profiles": [
                {
                    "agent_id": "agent-a",
                    "allowed_tools": ["local__read_file"],
                    "denied_tools": [],
                    "max_tools": 5,
                },
                {
                    "agent_id": "agent-b",
                    "allowed_tools": ["serena__search"],
                    "denied_tools": ["local__run_shell"],
                    "max_tools": 3,
                },
            ]
        }
        manager = ToolPermissionManager(config_path=_write_config(tmp_path, data))
        assert "agent-a" in manager._agent_profiles
        assert "agent-b" in manager._agent_profiles
        assert manager.is_tool_allowed("agent-a", "local__read_file") is True
        assert manager.is_tool_allowed("agent-b", "local__run_shell") is False

    def test_null_lists_in_yaml_are_treated_as_empty(self, tmp_path):
        # YAML `allowed_tools: ~` (null) should not crash
        data = {
            "agent_profiles": [
                {
                    "agent_id": "agent-null",
                    "allowed_tools": None,
                    "denied_tools": None,
                    "max_tools": 5,
                }
            ]
        }
        manager = ToolPermissionManager(config_path=_write_config(tmp_path, data))
        profile = manager._agent_profiles.get("agent-null")
        assert profile is not None
        assert profile.allowed_tools == []
        assert profile.denied_tools == []
