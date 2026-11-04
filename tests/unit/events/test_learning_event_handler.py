from unittest.mock import AsyncMock

import pytest

from src.core.events.handlers.learning_event_handler import LearningEventHandler
from src.core.events.publisher import DomainEvent


def _make_event(event_type: str, success: bool) -> DomainEvent:
    return DomainEvent(
        event_id="evt-1",
        event_type=event_type,
        aggregate_id="agent-1",
        aggregate_type="ToolExecution",
        data={
            "tool_name": "test__echo",
            "agent_id": "agent-1",
            "payload": {"foo": "bar"},
            "result": {"ok": True},
            "duration_seconds": 0.5,
            "success": success,
            "error": None if success else "boom",
        },
        metadata={"agent_type": "specialist"},
    )


@pytest.mark.asyncio
async def test_handle_tool_executed_records_observation() -> None:
    service = AsyncMock()
    service.record = AsyncMock(return_value="obs-1")
    handler = LearningEventHandler(observation_service=service, tenant_id=1)
    observation_id = await handler.handle_tool_executed(_make_event("tool.executed", True))
    assert observation_id == "obs-1"
    service.record.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_tool_failed_records_error_observation() -> None:
    service = AsyncMock()
    service.record = AsyncMock(return_value="obs-2")
    handler = LearningEventHandler(observation_service=service, tenant_id=1)
    observation_id = await handler.handle_tool_failed(_make_event("tool.failed", False))
    assert observation_id == "obs-2"
    service.record.assert_awaited_once()
