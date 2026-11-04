from unittest.mock import AsyncMock, MagicMock

import pytest

# Deze tests voeren echt een tool uit en hebben dus een tenant in de executiecontext
# nodig (ADR-036 OP-27: de pseudonimiseringsscope van de payload hangt eraan).
from tests.fixtures.tool_execution_tenant import tool_execution_tenant  # noqa: F401

from src.core.tool_broker.exceptions import ToolExecutionException
from src.core.tool_broker.permission_manager import ToolPermissionManager
from src.core.tool_broker.service import ToolBrokerService


def _make_permission_manager(agent_id: str, allowed_tools: list[str]) -> ToolPermissionManager:
    """Return a ToolPermissionManager with a single agent profile (no YAML needed)."""
    mgr = ToolPermissionManager(config_path="nonexistent_path_no_config")
    from src.core.tool_broker.permission_manager import AgentToolProfile

    mgr._agent_profiles[agent_id] = AgentToolProfile(
        agent_id=agent_id,
        allowed_tools=allowed_tools,
        denied_tools=[],
    )
    return mgr


@pytest.mark.asyncio
async def test_tool_execution_denied_without_permissions():
    """Agent with a profile that excludes the requested tool is denied (ADR-015)."""
    mock_serena = MagicMock()
    mock_seq = MagicMock()

    agent_id = "marketing_agent"
    forbidden_tool = "local__shutdown_server"

    mgr = _make_permission_manager(agent_id, allowed_tools=["local__send_email"])
    broker = ToolBrokerService(
        serena_client=mock_serena,
        seq_thinking_client=mock_seq,
        permission_manager=mgr,
    )

    with pytest.raises(ToolExecutionException, match="Permission denied"):
        await broker.execute_tool(tool_name=forbidden_tool, payload={}, agent_id=agent_id)


@pytest.mark.asyncio
async def test_tool_execution_denied_for_unknown_agent():
    """Agent with no profile in yml is default-denied (ADR-015 fail-secure)."""
    mock_serena = MagicMock()
    mock_seq = MagicMock()

    mgr = ToolPermissionManager(config_path="nonexistent_path_no_config")
    broker = ToolBrokerService(
        serena_client=mock_serena,
        seq_thinking_client=mock_seq,
        permission_manager=mgr,
    )

    with pytest.raises(ToolExecutionException, match="Permission denied"):
        await broker.execute_tool(tool_name="local__any_tool", payload={}, agent_id="unknown_agent")


@pytest.mark.asyncio
async def test_tool_execution_denied_for_none_agent_id():
    """None agent_id is treated as empty string (no profile) -> default-denied (RV-001)."""
    mock_serena = MagicMock()
    mock_seq = MagicMock()

    mgr = ToolPermissionManager(config_path="nonexistent_path_no_config")
    broker = ToolBrokerService(
        serena_client=mock_serena,
        seq_thinking_client=mock_seq,
        permission_manager=mgr,
    )

    with pytest.raises(ToolExecutionException, match="Permission denied"):
        await broker.execute_tool(tool_name="local__any_tool", payload={}, agent_id=None)


@pytest.mark.asyncio
async def test_tool_execution_allowed_with_permissions():
    """Agent with an explicit profile that includes the tool is allowed (ADR-015)."""
    mock_serena = MagicMock()
    mock_serena.call = AsyncMock(return_value={"status": "sent"})
    mock_seq = MagicMock()

    agent_id = "marketing_agent"
    allowed_tool = "serena__send_email"

    mgr = _make_permission_manager(agent_id, allowed_tools=[allowed_tool])
    broker = ToolBrokerService(
        serena_client=mock_serena,
        seq_thinking_client=mock_seq,
        enable_resilience=False,
        permission_manager=mgr,
    )

    result = await broker.execute_tool(tool_name=allowed_tool, payload={}, agent_id=agent_id)
    assert result["status"] == "sent"
