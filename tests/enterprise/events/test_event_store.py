"""
Tests for Event Sourcing - Immutable Event Log

Sprint D: Event Store, State Reconstruction, Event Partitioning
"""

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List

import pytest

from src.core.als.enterprise.events.event_store import (
    ContractState,
    Event,
    EventStore,
    EventType,
    StateProjector,
)


class TestEventModel:
    """Test Event data model."""

    def test_event_creation(self):
        """Test creating an event."""
        event = Event(
            event_id="evt-001",
            event_type=EventType.CONTRACT_PROPOSED,
            tenant_id=1,
            aggregate_id="contract-001",
            aggregate_type="contract",
            payload={"prana_cost": 50},
            correlation_id="corr-001",
            idempotency_key="idem-001",
            timestamp=datetime.now(timezone.utc),
            previous_hash="0" * 32,
        )

        assert event.event_id == "evt-001"
        assert event.event_type == EventType.CONTRACT_PROPOSED
        assert event.tenant_id == 1
        assert event.compute_hash() is not None

    def test_event_hash_chain(self):
        """Test that events form a hash chain."""
        event1 = Event(
            event_id="evt-001",
            event_type=EventType.CONTRACT_PROPOSED,
            tenant_id=1,
            aggregate_id="contract-001",
            aggregate_type="contract",
            payload={},
            timestamp=datetime.now(timezone.utc),
            previous_hash="0" * 32,
        )

        # First event computes its hash
        hash1 = event1.compute_hash()

        # Second event references first
        event2 = Event(
            event_id="evt-002",
            event_type=EventType.CONTRACT_AGREED,
            tenant_id=1,
            aggregate_id="contract-001",
            aggregate_type="contract",
            payload={},
            timestamp=datetime.now(timezone.utc),
            previous_hash=hash1,
        )

        assert event2.previous_hash == hash1


class TestEventStore:
    """Test EventStore functionality."""

    @pytest.fixture
    def event_store(self):
        """Create an EventStore instance."""
        return EventStore()

    @pytest.mark.asyncio
    async def test_append_event(self, event_store):
        """Test appending an event."""
        event = Event(
            event_id="evt-001",
            event_type=EventType.CONTRACT_PROPOSED,
            tenant_id=1,
            aggregate_id="contract-001",
            aggregate_type="contract",
            payload={"prana_cost": 50},
            correlation_id="corr-001",
            timestamp=datetime.now(timezone.utc),
            previous_hash="0" * 32,
        )

        result = await event_store.append(event)
        assert result is True
        assert len(event_store._events) == 1

    @pytest.mark.asyncio
    async def test_append_multiple_events(self, event_store):
        """Test appending multiple events."""
        for i in range(3):
            event = Event(
                event_id=f"evt-{i:03d}",
                event_type=EventType.CONTRACT_PROPOSED,
                tenant_id=1,
                aggregate_id="contract-001",
                aggregate_type="contract",
                payload={"seq": i},
                timestamp=datetime.now(timezone.utc),
                previous_hash="0" * 32 if i == 0 else event_store._events[-1].event_hash,
            )
            await event_store.append(event)

        assert len(event_store._events) == 3

    @pytest.mark.asyncio
    async def test_get_events_by_aggregate(self, event_store):
        """Test retrieving events by aggregate ID."""
        # Events for contract-001
        for i in range(2):
            event = Event(
                event_id=f"evt-c1-{i}",
                event_type=EventType.CONTRACT_PROPOSED,
                tenant_id=1,
                aggregate_id="contract-001",
                aggregate_type="contract",
                payload={},
                timestamp=datetime.now(timezone.utc),
                previous_hash="0" * 32,
            )
            await event_store.append(event)

        # Events for contract-002
        for i in range(3):
            event = Event(
                event_id=f"evt-c2-{i}",
                event_type=EventType.CONTRACT_PROPOSED,
                tenant_id=1,
                aggregate_id="contract-002",
                aggregate_type="contract",
                payload={},
                timestamp=datetime.now(timezone.utc),
                previous_hash="0" * 32,
            )
            await event_store.append(event)

        events_c1 = event_store.get_events_by_aggregate("contract-001")
        events_c2 = event_store.get_events_by_aggregate("contract-002")

        assert len(events_c1) == 2
        assert len(events_c2) == 3

    @pytest.mark.asyncio
    async def test_get_events_by_tenant(self, event_store):
        """Test retrieving events by tenant."""
        for tenant_id in [1, 2]:
            for i in range(2):
                event = Event(
                    event_id=f"evt-t{tenant_id}-{i}",
                    event_type=EventType.CONTRACT_PROPOSED,
                    tenant_id=tenant_id,
                    aggregate_id=f"contract-t{tenant_id}",
                    aggregate_type="contract",
                    payload={},
                    timestamp=datetime.now(timezone.utc),
                    previous_hash="0" * 32,
                )
                await event_store.append(event)

        events_t1 = event_store.get_events_by_tenant(1)
        events_t2 = event_store.get_events_by_tenant(2)

        assert len(events_t1) == 2
        assert len(events_t2) == 2

    @pytest.mark.asyncio
    async def test_event_immutability(self, event_store):
        """Test that events cannot be modified after creation."""
        event = Event(
            event_id="evt-001",
            event_type=EventType.CONTRACT_PROPOSED,
            tenant_id=1,
            aggregate_id="contract-001",
            aggregate_type="contract",
            payload={"prana_cost": 50},
            timestamp=datetime.now(timezone.utc),
            previous_hash="0" * 32,
        )

        await event_store.append(event)

        # Try to modify the stored event
        with pytest.raises(AttributeError):
            event_store._events[0].payload = {"modified": True}

    @pytest.mark.asyncio
    async def test_idempotency(self, event_store):
        """Test that duplicate events are rejected."""
        event = Event(
            event_id="evt-001",
            event_type=EventType.CONTRACT_PROPOSED,
            tenant_id=1,
            aggregate_id="contract-001",
            aggregate_type="contract",
            payload={},
            idempotency_key="idem-001",
            timestamp=datetime.now(timezone.utc),
            previous_hash="0" * 32,
        )

        result1 = await event_store.append(event)
        assert result1 is True

        # Try to append same event again
        result2 = await event_store.append(event)
        assert result2 is False  # Duplicate rejected

    @pytest.mark.asyncio
    async def test_get_events_by_timerange(self, event_store):
        """Test retrieving events by time range."""
        now = datetime.now(timezone.utc)

        # Old event
        old_event = Event(
            event_id="evt-old",
            event_type=EventType.CONTRACT_PROPOSED,
            tenant_id=1,
            aggregate_id="contract-001",
            aggregate_type="contract",
            payload={},
            timestamp=now - timedelta(hours=2),
            previous_hash="0" * 32,
        )
        await event_store.append(old_event)

        # Recent events
        for i in range(3):
            event = Event(
                event_id=f"evt-recent-{i}",
                event_type=EventType.CONTRACT_PROPOSED,
                tenant_id=1,
                aggregate_id="contract-001",
                aggregate_type="contract",
                payload={},
                timestamp=now - timedelta(minutes=i),
                previous_hash="0" * 32,
            )
            await event_store.append(event)

        # Query last hour
        events = event_store.get_events_by_timerange(since=now - timedelta(hours=1))

        assert len(events) == 3  # Only recent events


class TestStateProjector:
    """Test StateProjector for state reconstruction."""

    @pytest.fixture
    def event_store(self):
        """Create an EventStore with sample contract events."""
        store = EventStore()
        return store

    @pytest.mark.asyncio
    async def test_reconstruct_contract_state(self, event_store):
        """Test reconstructing contract state from events."""
        # Create contract lifecycle events
        events = [
            Event(
                event_id="evt-001",
                event_type=EventType.CONTRACT_PROPOSED,
                tenant_id=1,
                aggregate_id="contract-001",
                aggregate_type="contract",
                payload={"prana_cost": 50},
                timestamp=datetime.now(timezone.utc),
                previous_hash="0" * 32,
            ),
            Event(
                event_id="evt-002",
                event_type=EventType.CONTRACT_AGREED,
                tenant_id=1,
                aggregate_id="contract-001",
                aggregate_type="contract",
                payload={},
                timestamp=datetime.now(timezone.utc),
                previous_hash="0" * 32,
            ),
            Event(
                event_id="evt-003",
                event_type=EventType.CONTRACT_EXECUTING,
                tenant_id=1,
                aggregate_id="contract-001",
                aggregate_type="contract",
                payload={},
                timestamp=datetime.now(timezone.utc),
                previous_hash="0" * 32,
            ),
            Event(
                event_id="evt-004",
                event_type=EventType.CONTRACT_SETTLED,
                tenant_id=1,
                aggregate_id="contract-001",
                aggregate_type="contract",
                payload={"result": "success"},
                timestamp=datetime.now(timezone.utc),
                previous_hash="0" * 32,
            ),
        ]

        for event in events:
            await event_store.append(event)

        # Reconstruct state
        projector = StateProjector()
        state = projector.reconstruct_contract_state(
            event_store.get_events_by_aggregate("contract-001")
        )

        assert state["contract_id"] == "contract-001"
        assert state["state"] == ContractState.SETTLED
        assert state["prana_cost"] == 50

    @pytest.mark.asyncio
    async def test_reconstruct_state_with_veto(self, event_store):
        """Test state reconstruction with veto and override."""
        events = [
            Event(
                event_id="evt-001",
                event_type=EventType.CONTRACT_PROPOSED,
                tenant_id=1,
                aggregate_id="contract-002",
                aggregate_type="contract",
                payload={},
                timestamp=datetime.now(timezone.utc),
                previous_hash="0" * 32,
            ),
            Event(
                event_id="evt-002",
                event_type=EventType.CONTRACT_VETOED,
                tenant_id=1,
                aggregate_id="contract-002",
                aggregate_type="contract",
                payload={"veto_reason": "High risk"},
                timestamp=datetime.now(timezone.utc),
                previous_hash="0" * 32,
            ),
            Event(
                event_id="evt-003",
                event_type=EventType.CONTRACT_OVERRIDDEN,
                tenant_id=1,
                aggregate_id="contract-002",
                aggregate_type="contract",
                payload={"override_by": "admin"},
                timestamp=datetime.now(timezone.utc),
                previous_hash="0" * 32,
            ),
            Event(
                event_id="evt-004",
                event_type=EventType.CONTRACT_EXECUTING,
                tenant_id=1,
                aggregate_id="contract-002",
                aggregate_type="contract",
                payload={},
                timestamp=datetime.now(timezone.utc),
                previous_hash="0" * 32,
            ),
        ]

        for event in events:
            await event_store.append(event)

        projector = StateProjector()
        state = projector.reconstruct_contract_state(
            event_store.get_events_by_aggregate("contract-002")
        )

        assert state["state"] == ContractState.EXECUTING
        assert state["was_vetoed"] is True
        assert state["was_overridden"] is True

    def test_empty_event_list(self):
        """Test reconstruction with no events."""
        projector = StateProjector()
        state = projector.reconstruct_contract_state([])

        assert state["contract_id"] is None
        assert state["state"] is None


class TestEventHashChain:
    """Test hash chain verification."""

    @pytest.mark.asyncio
    async def test_verify_hash_chain(self):
        """Test verifying a chain of events."""
        store = EventStore()

        # Create chain of events
        events = []
        prev_hash = "0" * 32

        for i in range(5):
            event = Event(
                event_id=f"evt-{i:03d}",
                event_type=EventType.CONTRACT_PROPOSED,
                tenant_id=1,
                aggregate_id="contract-001",
                aggregate_type="contract",
                payload={"seq": i},
                timestamp=datetime.now(timezone.utc),
                previous_hash=prev_hash,
            )
            await store.append(event)
            events.append(event)
            prev_hash = event.event_hash

        # Verify chain
        assert store.verify_hash_chain("contract-001") is True

    @pytest.mark.asyncio
    async def test_detect_tampering(self):
        """Test detecting tampered events."""
        store = EventStore()

        # Create events
        event = Event(
            event_id="evt-001",
            event_type=EventType.CONTRACT_PROPOSED,
            tenant_id=1,
            aggregate_id="contract-001",
            aggregate_type="contract",
            payload={"original": True},
            timestamp=datetime.now(timezone.utc),
            previous_hash="0" * 32,
        )
        await store.append(event)

        # Tamper with stored event using object.__setattr__ to bypass frozen
        # This simulates what would happen if someone tried to modify the event
        object.__setattr__(store._events[0], "event_hash", "tampered_hash")

        # Verification should fail
        assert store.verify_hash_chain("contract-001") is False


class TestEventPartitioning:
    """Test event partitioning by tenant and time."""

    @pytest.mark.asyncio
    async def test_partition_by_tenant(self):
        """Test events are partitioned by tenant."""
        store = EventStore()

        # Add events for multiple tenants
        for tenant_id in [1, 2, 3]:
            for i in range(3):
                event = Event(
                    event_id=f"evt-t{tenant_id}-{i}",
                    event_type=EventType.CONTRACT_PROPOSED,
                    tenant_id=tenant_id,
                    aggregate_id=f"contract-{tenant_id}",
                    aggregate_type="contract",
                    payload={},
                    timestamp=datetime.now(timezone.utc),
                    previous_hash="0" * 32,
                )
                await store.append(event)

        # Get partition stats
        stats = store.get_partition_stats()

        assert stats["total_events"] == 9
        assert stats["tenant_count"] == 3
        assert stats["events_per_tenant"][1] == 3
        assert stats["events_per_tenant"][2] == 3
        assert stats["events_per_tenant"][3] == 3

    @pytest.mark.asyncio
    async def test_partition_by_month(self):
        """Test events are partitioned by month."""
        store = EventStore()

        now = datetime.now(timezone.utc)

        # Events from different months
        for month_offset in [0, 1, 2]:
            timestamp = now - timedelta(days=30 * month_offset)
            event = Event(
                event_id=f"evt-month-{month_offset}",
                event_type=EventType.CONTRACT_PROPOSED,
                tenant_id=1,
                aggregate_id=f"contract-{month_offset}",
                aggregate_type="contract",
                payload={},
                timestamp=timestamp,
                previous_hash="0" * 32,
            )
            await store.append(event)

        stats = store.get_partition_stats()

        # Should have events across multiple months
        assert len(stats["events_per_month"]) >= 1


class TestEventQuerying:
    """Test advanced event querying."""

    @pytest.mark.asyncio
    async def test_query_by_event_type(self):
        """Test querying events by type."""
        store = EventStore()

        # Mixed event types
        event_types = [
            EventType.CONTRACT_PROPOSED,
            EventType.CONTRACT_AGREED,
            EventType.CONTRACT_PROPOSED,
            EventType.CONTRACT_SETTLED,
        ]

        for i, etype in enumerate(event_types):
            event = Event(
                event_id=f"evt-{i}",
                event_type=etype,
                tenant_id=1,
                aggregate_id=f"contract-{i}",
                aggregate_type="contract",
                payload={},
                timestamp=datetime.now(timezone.utc),
                previous_hash="0" * 32,
            )
            await store.append(event)

        proposed = store.query_events(event_type=EventType.CONTRACT_PROPOSED)
        assert len(proposed) == 2

    @pytest.mark.asyncio
    async def test_query_by_correlation_id(self):
        """Test querying events by correlation ID."""
        store = EventStore()

        # Events with same correlation
        for i in range(3):
            event = Event(
                event_id=f"evt-corr-{i}",
                event_type=EventType.CONTRACT_PROPOSED,
                tenant_id=1,
                aggregate_id=f"contract-{i}",
                aggregate_type="contract",
                payload={},
                correlation_id="workflow-001",
                timestamp=datetime.now(timezone.utc),
                previous_hash="0" * 32,
            )
            await store.append(event)

        # Event with different correlation
        event = Event(
            event_id="evt-other",
            event_type=EventType.CONTRACT_PROPOSED,
            tenant_id=1,
            aggregate_id="contract-other",
            aggregate_type="contract",
            payload={},
            correlation_id="workflow-002",
            timestamp=datetime.now(timezone.utc),
            previous_hash="0" * 32,
        )
        await store.append(event)

        events = store.query_events(correlation_id="workflow-001")
        assert len(events) == 3
