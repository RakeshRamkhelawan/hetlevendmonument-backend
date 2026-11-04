import asyncio
from datetime import datetime, timezone

import pytest

from src.core.memory.event_bus import Event, event_bus


@pytest.mark.asyncio
async def test_event_bus_publish_subscribe():
    # 1. Clear previous state
    event_bus.clear()

    received_events = []

    # Define an async callback
    async def callback(evt: Event):
        received_events.append(evt)

    # 2. Subscribe to "OBSERVE" channel
    event_bus.subscribe("OBSERVE", callback)

    # 3. Publish an event
    payload = Event(
        id="test-1",
        agent_id="agent-007",
        phase="OBSERVE",
        type="TEST_SIGNAL",
        content={"msg": "hello_world"},
        timestamp=datetime.now(timezone.utc),
    )

    # We await the publish (since it's async)
    await event_bus.publish(payload)

    # 4. Verify Subscriber received it
    assert len(received_events) == 1
    assert received_events[0].content["msg"] == "hello_world"
    assert received_events[0].agent_id == "agent-007"


@pytest.mark.asyncio
async def test_event_bus_buffer():
    event_bus.clear()

    # Publish 2 events
    evt1 = Event(agent_id="A1", phase="ACT", type="T1", content={})
    evt2 = Event(agent_id="A2", phase="ACT", type="T2", content={})

    await event_bus.publish(evt1)
    await event_bus.publish(evt2)

    # Check buffer (LIFO order usually, but let's check content)
    recent = event_bus.get_recent_events()
    assert len(recent) == 2
    ids = [e.agent_id for e in recent]
    assert "A1" in ids
    assert "A2" in ids
