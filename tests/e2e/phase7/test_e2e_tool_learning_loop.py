from __future__ import annotations

import asyncio
import pytest

from src.core.events.pubsub_manager import get_pubsub_manager
from src.core.events.learning_event_wiring import initialize_learning_events, reset_learning_event_registration
from src.core.events.publisher import DomainEvent, EventPublisher
from tests.helpers.db_verify import count_all_learning_records
from tests.helpers.factories import make_tool_event_data
from tests.helpers.wait_for import wait_for_condition


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.no_mocks
async def test_tool_execution_learning_loop_creates_learning_artifacts(
    phase7_learning_stack,
    phase7_session,
    phase7_tenant_id: int,
) -> None:
    # Get singleton pubsub manager and publisher
    pubsub_manager = await get_pubsub_manager()
    publisher = EventPublisher(pubsub_manager)
    
    # Create the handler with the wired test stack to use test database!
    from src.core.events.handlers.learning_event_handler import LearningEventHandler
    handler = LearningEventHandler(
        observation_service=phase7_learning_stack["observation_service"],
        tenant_id=phase7_tenant_id,
    )
    
    # Initialize learning event handler via production wiring
    reset_learning_event_registration()
    await initialize_learning_events(pubsub_manager, tenant_id=phase7_tenant_id, handler=handler)

    # Start the pub/sub listener loop in a background task
    consume_task = asyncio.create_task(pubsub_manager.start_listening())
    
    await asyncio.sleep(0.5)  # give it time to subscribe

    try:
        await publisher.connect()
        for index in range(20):
            event = DomainEvent(
                event_id=f"phase7-tool-event-{index}",
                event_type="tool.executed",
                aggregate_id=f"tool-run-{index}",
                aggregate_type="ToolExecution",
                data=make_tool_event_data(index, phase7_tenant_id),
                metadata={"agent_type": "python_pro"},
            )
            await publisher.publish(event)

        await wait_for_condition(
            lambda: count_all_learning_records(phase7_session, phase7_tenant_id),
            lambda counts: (print(f"\nCOUNTS: {counts}") or True) and counts["observations"] >= 20
            and counts["patterns"] >= 1
            and counts["adaptations"] >= 1
            and counts["insights"] >= 1,
            timeout_seconds=10.0,
            poll_interval=1.0,
            description="tool execution events to create learning artifacts via Redis",
        )
    finally:
        await publisher.disconnect()
        pubsub_manager._stop_listening = True
        consume_task.cancel()
        try:
            await consume_task
        except asyncio.CancelledError:
            pass

    counts = await count_all_learning_records(phase7_session, phase7_tenant_id)

    assert counts["observations"] >= 20
    assert counts["patterns"] >= 1
    assert counts["adaptations"] >= 1
    assert counts["insights"] >= 1
