"""Unit tests voor TwinEventBridge.

Covers:
- Bridge subscribes to twin events on the singleton bus
- Events are forwarded to Redis Pub/Sub
- Handler errors do not break the bus
- Bridge start/stop lifecycle
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.learning.events.event_bus import TwinEventBus, reset_twin_event_bus
from src.core.learning.events.twin_events import (
    ConsentChanged,
    InterventionSuggested,
    ProfileUpdated,
    UserBehaviorTracked,
)
from src.core.learning.wiring.twin_event_bridge import (
    TwinEventBridge,
    get_twin_event_bridge,
    shutdown_twin_event_bridge,
)


@pytest.fixture(autouse=True)
def _reset_bus():
    """Ensure a clean event bus before each test."""
    reset_twin_event_bus()
    yield
    reset_twin_event_bus()


@pytest.mark.asyncio
class TestTwinEventBridgeLifecycle:
    """Tests voor bridge start/stop."""

    async def test_start_subscribes_handlers(self):
        bus = TwinEventBus()
        bridge = TwinEventBridge(event_bus=bus)
        await bridge.start()

        assert bus.subscriber_count("twin.user_behavior.tracked") == 1
        assert bus.subscriber_count("twin.profile.updated") == 1
        # Forwarding + learning handlers for intervention/critique events.
        assert bus.subscriber_count("twin.intervention.suggested") == 2
        assert bus.subscriber_count("twin.critique.score_low") == 2
        assert bus.subscriber_count("twin.consent.changed") == 1
        assert bus.subscriber_count("twin.hard_delete.requested") == 1

        await bridge.stop()

    async def test_stop_unsubscribes_handlers(self):
        bus = TwinEventBus()
        bridge = TwinEventBridge(event_bus=bus)
        await bridge.start()
        await bridge.stop()

        assert bus.subscriber_count("twin.user_behavior.tracked") == 0
        assert bus.subscriber_count("twin.profile.updated") == 0

    async def test_double_start_is_idempotent(self):
        bus = TwinEventBus()
        bridge = TwinEventBridge(event_bus=bus)
        await bridge.start()
        await bridge.start()  # second call should be no-op

        # Should still have exactly one handler per event type
        assert bus.subscriber_count("twin.user_behavior.tracked") == 1
        await bridge.stop()


@pytest.mark.asyncio
class TestTwinEventBridgeForwarding:
    """Tests voor Redis Pub/Sub forwarding."""

    async def test_behavior_tracked_forwarded(self):
        bus = TwinEventBus()
        mock_pubsub = AsyncMock()
        bridge = TwinEventBridge(event_bus=bus, pubsub=mock_pubsub)
        await bridge.start()

        event = UserBehaviorTracked(
            user_id="u1",
            tenant_id=1,
            behavior_type="file_edit",
            trace_id="trace_001",
            context={"edit_count": 3},
        )
        await bus.publish(event)

        assert mock_pubsub.publish.call_count == 1
        call_args = mock_pubsub.publish.call_args[0][0]
        assert call_args.data["twin_event_type"] == "twin.user_behavior.tracked"
        assert call_args.data["behavior_type"] == "file_edit"

        await bridge.stop()

    async def test_profile_updated_forwarded(self):
        bus = TwinEventBus()
        mock_pubsub = AsyncMock()
        bridge = TwinEventBridge(event_bus=bus, pubsub=mock_pubsub)
        await bridge.start()

        event = ProfileUpdated(
            user_id="u1",
            tenant_id=1,
            profile_id=42,
            confidence_level=0.85,
            observation_count=100,
        )
        await bus.publish(event)

        assert mock_pubsub.publish.call_count == 1
        call_args = mock_pubsub.publish.call_args[0][0]
        assert call_args.data["confidence_level"] == 0.85
        assert call_args.data["observation_count"] == 100

        await bridge.stop()

    async def test_intervention_suggested_forwarded(self):
        bus = TwinEventBus()
        mock_pubsub = AsyncMock()
        bridge = TwinEventBridge(event_bus=bus, pubsub=mock_pubsub)
        await bridge.start()

        event = InterventionSuggested(
            user_id="u1",
            tenant_id=1,
            intervention_type="struggle",
            message="Neem een pauze",
            confidence=0.92,
        )
        await bus.publish(event)

        assert mock_pubsub.publish.call_count == 1
        call_args = mock_pubsub.publish.call_args[0][0]
        assert call_args.data["intervention_type"] == "struggle"
        assert call_args.data["message"] == "Neem een pauze"

        await bridge.stop()

    async def test_pubsub_failure_does_not_break_bus(self):
        bus = TwinEventBus()
        mock_pubsub = AsyncMock()
        mock_pubsub.publish.side_effect = ConnectionError("redis down")
        bridge = TwinEventBridge(event_bus=bus, pubsub=mock_pubsub)
        await bridge.start()

        # Should NOT raise
        event = UserBehaviorTracked(user_id="u1", tenant_id=1, behavior_type="edit")
        await bus.publish(event)

        # Bus is still functional
        assert bus.subscriber_count("twin.user_behavior.tracked") == 1

        await bridge.stop()


@pytest.mark.asyncio
class TestTwinEventBridgeSingleton:
    """Tests voor singleton getters."""

    async def test_get_twin_event_bridge_returns_same_instance(self):
        bridge1 = await get_twin_event_bridge()
        bridge2 = await get_twin_event_bridge()
        assert bridge1 is bridge2
        await shutdown_twin_event_bridge()

    async def test_shutdown_creates_new_instance(self):
        bridge1 = await get_twin_event_bridge()
        await shutdown_twin_event_bridge()
        bridge2 = await get_twin_event_bridge()
        assert bridge1 is not bridge2
        await shutdown_twin_event_bridge()
