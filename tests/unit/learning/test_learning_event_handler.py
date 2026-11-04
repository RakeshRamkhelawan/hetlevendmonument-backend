from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.core.events.handlers.learning_event_handler import LearningEventHandler
from src.core.events.publisher import DomainEvent


def _make_event(success: bool = True) -> DomainEvent:
    return DomainEvent(
        event_id="event-1",
        event_type="tool.executed" if success else "tool.failed",
        aggregate_id="agent-1",
        aggregate_type="ToolExecution",
        data={
            "agent_id": "agent-1",
            "tool_name": "test__echo",
            "payload": {"value": 1},
            "result": {"ok": success},
            "error": None if success else "boom",
            "success": success,
            "duration_seconds": 0.2,
        },
        timestamp=datetime.now(timezone.utc),
        metadata={"agent_type": "python_pro"},
    )


def test_observation_service_property_creates_default_service() -> None:
    handler = LearningEventHandler(observation_service=None, tenant_id=0)

    service = handler.observation_service

    assert service.tenant_id == 1


@pytest.mark.asyncio
async def test_handle_tool_failed_uses_error_correction_learning_type() -> None:
    observation_service = AsyncMock()
    observation_service.record = AsyncMock(return_value="obs-failure")
    handler = LearningEventHandler(observation_service=observation_service, tenant_id=17)

    observation_id = await handler.handle_tool_failed(_make_event(success=False))

    assert observation_id == "obs-failure"
    kwargs = observation_service.record.await_args.kwargs
    assert kwargs["context"]["task_type"] == "tool_execution"
    assert kwargs["observation_data"]["success"] is False


@pytest.mark.asyncio
async def test_handler_swallows_observation_errors() -> None:
    observation_service = AsyncMock()
    observation_service.record = AsyncMock(side_effect=RuntimeError("db offline"))
    handler = LearningEventHandler(observation_service=observation_service, tenant_id=17)

    observation_id = await handler.handle_tool_executed(_make_event(success=True))

    assert observation_id is None
