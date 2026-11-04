import asyncio
from unittest.mock import AsyncMock, patch

import pytest

# `tool_execution_tenant`: deze tests voeren echt een tool uit en hebben dus een tenant in de
# executiecontext nodig (ADR-036 OP-27: de pseudonimiseringsscope van de payload hangt eraan).
# ADR-036 OP-216: LocalToolRegistry bouwt geen sandbox meer, dus deze tests hebben sinds die
# fix geen `geen_echte_docker_daemon`-fixture meer nodig -- de constructor raakt geen daemon.
from tests.fixtures.tool_execution_tenant import tool_execution_tenant  # noqa: F401

from src.core.tool_broker.local_registry import LocalToolRegistry
from src.core.tool_broker.service import ToolBrokerService


@pytest.fixture(autouse=True)
def _allow_all_tools():
    """Bypass ToolPermissionManager for service unit tests -- permission logic tested separately."""
    with patch(
        "src.core.tool_broker.service.ToolPermissionManager.is_tool_allowed",
        return_value=True,
    ):
        yield


@pytest.mark.asyncio
async def test_execute_tool_publishes_success_event() -> None:
    publisher = AsyncMock()
    service = ToolBrokerService(
        serena_client=None,
        seq_thinking_client=None,
        local_registry=LocalToolRegistry(),
        event_publisher=publisher,
        enable_resilience=False,
    )
    await service.execute_tool("test__echo", {"message": "hi", "tenant_id": 5}, agent_id="agent-1")
    await asyncio.sleep(0)
    publisher.publish.assert_awaited_once()
    event = publisher.publish.await_args.args[0]
    assert event.event_type == "tool.executed"
    assert event.data["tool_name"] == "test__echo"
    assert event.data["agent_id"] == "agent-1"


@pytest.mark.asyncio
async def test_execute_tool_publishes_failure_event() -> None:
    publisher = AsyncMock()
    service = ToolBrokerService(
        serena_client=None,
        seq_thinking_client=None,
        local_registry=LocalToolRegistry(),
        event_publisher=publisher,
        enable_resilience=False,
    )
    with pytest.raises(Exception):
        await service.execute_tool(
            "test__fail", {"message": "boom", "tenant_id": 5}, agent_id="agent-1"
        )
    await asyncio.sleep(0)
    publisher.publish.assert_awaited_once()
    event = publisher.publish.await_args.args[0]
    assert event.event_type == "tool.failed"
    assert event.data["tool_name"] == "test__fail"


@pytest.mark.asyncio
async def test_event_publishing_failure_does_not_break_tool() -> None:
    publisher = AsyncMock()
    publisher.publish = AsyncMock(side_effect=RuntimeError("rabbitmq down"))
    service = ToolBrokerService(
        serena_client=None,
        seq_thinking_client=None,
        local_registry=LocalToolRegistry(),
        event_publisher=publisher,
        enable_resilience=False,
    )
    result = await service.execute_tool("test__echo", {"message": "ok"}, agent_id="agent-1")
    await asyncio.sleep(0)
    assert result["echo"]["message"] == "ok"
