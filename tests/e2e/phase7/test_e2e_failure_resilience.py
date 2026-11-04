from __future__ import annotations

import pytest

from src.core.events.handlers.learning_event_handler import LearningEventHandler
from src.core.events.publisher import DomainEvent, EventPublisher
from tests.helpers.db_verify import count_observations
from tests.helpers.factories import make_tool_event_data


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.no_mocks
async def test_failure_resilience_degrades_gracefully_and_recovers(
    phase7_learning_stack,
    phase7_session,
    phase7_tenant_id: int,
) -> None:
    publisher = EventPublisher("amqp://guest:guest@127.0.0.1:1/")
    handler = LearningEventHandler(
        observation_service=phase7_learning_stack["observation_service"],
        tenant_id=phase7_tenant_id,
    )
    event = DomainEvent(
        event_id="phase7-recovery-event",
        event_type="tool.executed",
        aggregate_id="tool-recovery",
        aggregate_type="ToolExecution",
        data=make_tool_event_data(0, phase7_tenant_id),
        metadata={"agent_type": "python_pro"},
    )

    await publisher.publish(event)

    observation_id = await handler.handle_tool_executed(event)
    observations = await count_observations(phase7_session, phase7_tenant_id)

    assert observation_id is not None
    assert observations >= 1
