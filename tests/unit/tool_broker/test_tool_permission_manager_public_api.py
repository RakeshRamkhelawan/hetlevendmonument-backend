"""Tests for ToolPermissionManager public API and CopilotService encapsulation.

Verifies:
- get_allowed_tools(agent_id) public method exists on ToolPermissionManager (ADR-015)
- Returns allowed tools for configured agents
- Default-deny: returns empty list for unconfigured agents
- Hard denylist: filters out any tools present in denied_actions or denied_tools (ADR-036 D5)
- CopilotService._get_allowed_tools uses public API and does not access private _agent_profiles
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from src.core.tool_broker.permission_manager import ToolPermissionManager, AgentToolProfile


def test_tool_permission_manager_get_allowed_tools_returns_allowed_list() -> None:
    """Configured agent returns its declared allowed tools."""
    mgr = ToolPermissionManager()
    tools = mgr.get_allowed_tools("copilot")
    assert isinstance(tools, list)
    assert len(tools) > 0
    assert "send_notification" in tools
    assert "create_task" in tools


def test_tool_permission_manager_get_allowed_tools_default_deny() -> None:
    """Unknown agent returns empty list (default-deny per ADR-015)."""
    mgr = ToolPermissionManager()
    tools = mgr.get_allowed_tools("non_existent_agent_999")
    assert tools == []


def test_tool_permission_manager_get_allowed_tools_enforces_hard_denylist() -> None:
    """Denied actions and denied tools must be excluded even if listed in allowed_tools (ADR-036 D5)."""
    mgr = ToolPermissionManager()
    # Inject a test profile with conflicting allow and deny
    mgr._agent_profiles["test_agent"] = AgentToolProfile(
        agent_id="test_agent",
        allowed_tools=["safe_tool", "dangerous_tool", "legacy_forbidden_tool"],
        denied_tools=["legacy_forbidden_tool"],
        denied_actions=["dangerous_tool"],
    )

    allowed = mgr.get_allowed_tools("test_agent")
    assert allowed == ["safe_tool"]
    assert "dangerous_tool" not in allowed
    assert "legacy_forbidden_tool" not in allowed


@pytest.mark.asyncio
async def test_copilot_service_get_allowed_tools_calls_public_api_and_returns_dicts() -> None:
    """CopilotService._get_allowed_tools must invoke get_allowed_tools and return dict structure."""
    from src.core.copilot.service import CopilotService

    # Instantiate CopilotService without full dependencies
    service = object.__new__(CopilotService)

    mock_mgr = MagicMock()
    mock_mgr.get_allowed_tools.return_value = ["send_notification", "read_data"]

    with patch(
        "src.core.tool_broker.permission_manager.ToolPermissionManager", return_value=mock_mgr
    ):
        tools = await service._get_allowed_tools(tenant_id=1)

    mock_mgr.get_allowed_tools.assert_called_once_with("copilot")
    assert tools == [
        {"name": "send_notification", "allowed": True},
        {"name": "read_data", "allowed": True},
    ]


@pytest.mark.asyncio
async def test_copilot_service_get_allowed_tools_logs_error_on_exception() -> None:
    """CopilotService._get_allowed_tools must log error when ToolPermissionManager raises."""
    from src.core.copilot.service import CopilotService

    service = object.__new__(CopilotService)

    with (
        patch(
            "src.core.tool_broker.permission_manager.ToolPermissionManager",
            side_effect=RuntimeError("Permission config failure"),
        ),
        patch("src.core.copilot.service.logger.error") as mock_logger_error,
    ):
        tools = await service._get_allowed_tools(tenant_id=1)

    assert tools == []
    mock_logger_error.assert_called_once()
    assert "Failed to load tool permissions" in mock_logger_error.call_args[0][0]
    assert isinstance(mock_logger_error.call_args[0][1], RuntimeError)
