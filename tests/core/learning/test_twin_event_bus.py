"""
Unit tests voor TwinEventBus en TwinEvents.

Controleert:
- subscribe/unsubscribe
- publish roept handlers aan
- meerdere handlers voor hetzelfde event type
- handler error stopt de bus niet (fail-safe)
- publish_async is fire-and-forget
- subscriber_count
- clear
- TwinEvent dataclasses hebben correcte event_type
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from src.core.learning.events.event_bus import (
    TwinEventBus,
    get_twin_event_bus,
    reset_twin_event_bus,
)
from src.core.learning.events.twin_events import (
    ConsentChanged,
    HardDeleteRequested,
    InterventionSuggested,
    ProfileUpdated,
    TwinEvent,
    UserBehaviorTracked,
)


def _make_behavior_event(**kwargs) -> UserBehaviorTracked:
    defaults = {
        "user_id": "u1",
        "tenant_id": 1,
        "behavior_type": "file_edit",
        "trace_id": "trace_001",
    }
    defaults.update(kwargs)
    return UserBehaviorTracked(**defaults)  # type: ignore[arg-type]


class TestTwinEventDataclasses:
    """Tests voor de event dataclasses."""

    def test_user_behavior_tracked_event_type(self):
        event = UserBehaviorTracked(user_id="u1", tenant_id=1, behavior_type="edit")
        assert event.event_type == "twin.user_behavior.tracked"

    def test_profile_updated_event_type(self):
        event = ProfileUpdated(user_id="u1", tenant_id=1)
        assert event.event_type == "twin.profile.updated"

    def test_intervention_suggested_event_type(self):
        event = InterventionSuggested(user_id="u1", tenant_id=1)
        assert event.event_type == "twin.intervention.suggested"

    def test_consent_changed_event_type(self):
        event = ConsentChanged(user_id="u1", tenant_id=1, new_status="disabled")
        assert event.event_type == "twin.consent.changed"

    def test_hard_delete_requested_event_type(self):
        event = HardDeleteRequested(user_id="u1", tenant_id=1)
        assert event.event_type == "twin.hard_delete.requested"

    def test_event_has_timestamp(self):
        event = UserBehaviorTracked(user_id="u1", tenant_id=1, behavior_type="edit")
        assert event.timestamp is not None

    def test_event_has_trace_id(self):
        event = UserBehaviorTracked(
            user_id="u1", tenant_id=1, behavior_type="edit", trace_id="t123"
        )
        assert event.trace_id == "t123"


@pytest.mark.asyncio
class TestTwinEventBusSubscribePublish:
    """Tests voor subscribe/publish."""

    async def test_subscribe_and_publish(self):
        bus = TwinEventBus()
        received = []

        async def handler(event: TwinEvent) -> None:
            received.append(event)

        bus.subscribe("twin.user_behavior.tracked", handler)
        event = _make_behavior_event()
        await bus.publish(event)

        assert len(received) == 1
        assert received[0] is event

    async def test_multiple_handlers_all_called(self):
        bus = TwinEventBus()
        calls = []

        async def h1(event: TwinEvent) -> None:
            calls.append("h1")

        async def h2(event: TwinEvent) -> None:
            calls.append("h2")

        bus.subscribe("twin.user_behavior.tracked", h1)
        bus.subscribe("twin.user_behavior.tracked", h2)
        await bus.publish(_make_behavior_event())

        assert "h1" in calls
        assert "h2" in calls
        assert len(calls) == 2

    async def test_no_handlers_publish_is_noop(self):
        """Publish zonder subscribers → geen error."""
        bus = TwinEventBus()
        # Should not raise
        await bus.publish(_make_behavior_event())

    async def test_only_matching_handlers_called(self):
        bus = TwinEventBus()
        profile_calls = []
        behavior_calls = []

        async def on_profile(event: TwinEvent) -> None:
            profile_calls.append(event)

        async def on_behavior(event: TwinEvent) -> None:
            behavior_calls.append(event)

        bus.subscribe("twin.profile.updated", on_profile)
        bus.subscribe("twin.user_behavior.tracked", on_behavior)

        await bus.publish(_make_behavior_event())

        assert len(behavior_calls) == 1
        assert len(profile_calls) == 0

    async def test_unsubscribe_removes_handler(self):
        bus = TwinEventBus()
        calls = []

        async def handler(event: TwinEvent) -> None:
            calls.append(event)

        bus.subscribe("twin.user_behavior.tracked", handler)
        bus.unsubscribe("twin.user_behavior.tracked", handler)

        await bus.publish(_make_behavior_event())
        assert len(calls) == 0


@pytest.mark.asyncio
class TestTwinEventBusFailSafe:
    """Tests voor fail-safe gedrag."""

    async def test_handler_error_does_not_stop_bus(self):
        bus = TwinEventBus()
        second_handler_called = []

        async def failing_handler(event: TwinEvent) -> None:
            raise RuntimeError("handler failed!")

        async def second_handler(event: TwinEvent) -> None:
            second_handler_called.append(event)

        bus.subscribe("twin.user_behavior.tracked", failing_handler)
        bus.subscribe("twin.user_behavior.tracked", second_handler)

        # Should NOT raise
        await bus.publish(_make_behavior_event())

        # Second handler must still be called
        assert len(second_handler_called) == 1

    async def test_handler_error_is_logged_not_raised(self):
        bus = TwinEventBus()

        async def failing_handler(event: TwinEvent) -> None:
            raise ValueError("test error")

        bus.subscribe("twin.user_behavior.tracked", failing_handler)

        # Must not raise
        try:
            await bus.publish(_make_behavior_event())
        except Exception:
            pytest.fail("publish() should not raise when handler fails")


@pytest.mark.asyncio
class TestTwinEventBusUtils:
    """Tests voor utility methodes."""

    async def test_subscriber_count(self):
        bus = TwinEventBus()

        async def h1(event: TwinEvent) -> None:
            pass

        async def h2(event: TwinEvent) -> None:
            pass

        bus.subscribe("twin.user_behavior.tracked", h1)
        bus.subscribe("twin.user_behavior.tracked", h2)

        assert bus.subscriber_count("twin.user_behavior.tracked") == 2
        assert bus.subscriber_count("twin.profile.updated") == 0

    async def test_clear_removes_all_subscribers(self):
        bus = TwinEventBus()
        calls = []

        async def handler(event: TwinEvent) -> None:
            calls.append(event)

        bus.subscribe("twin.user_behavior.tracked", handler)
        bus.subscribe("twin.profile.updated", handler)
        bus.clear()

        await bus.publish(_make_behavior_event())
        assert len(calls) == 0
        assert bus.subscriber_count("twin.user_behavior.tracked") == 0

    async def test_publish_async_fire_and_forget(self):
        bus = TwinEventBus()
        received = []

        async def handler(event: TwinEvent) -> None:
            received.append(event)

        bus.subscribe("twin.user_behavior.tracked", handler)
        await bus.publish_async(_make_behavior_event())

        # Give the task time to run
        await asyncio.sleep(0.05)
        assert len(received) == 1


class TestTwinEventBusSingleton:
    """Tests voor de singleton getter/reset."""

    def test_get_twin_event_bus_returns_same_instance(self):
        bus1 = get_twin_event_bus()
        bus2 = get_twin_event_bus()
        assert bus1 is bus2

    def test_reset_twin_event_bus_creates_new_instance(self):
        bus1 = get_twin_event_bus()
        reset_twin_event_bus()
        bus2 = get_twin_event_bus()
        assert bus1 is not bus2

    def test_reset_clears_subscribers(self):
        bus = get_twin_event_bus()
        bus.subscribe("twin.user_behavior.tracked", AsyncMock())
        assert bus.subscriber_count("twin.user_behavior.tracked") == 1
        reset_twin_event_bus()
        bus2 = get_twin_event_bus()
        assert bus2.subscriber_count("twin.user_behavior.tracked") == 0
