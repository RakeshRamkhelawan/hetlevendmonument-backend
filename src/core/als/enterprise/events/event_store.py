"""
Event Sourcing - Immutable Event Log

This module implements event sourcing for the ALS system:
1. Event Store: Append-only log of all domain events
2. State Projector: Reconstruct aggregate state from events
3. Hash Chain: Tamper-evident event chain

Architecture:
- Events are immutable (no updates/deletes)
- Hash chain links events for tamper detection
- Partitioned by tenant_id for multi-tenancy
- Events can be replayed to reconstruct state

Usage:
    store = EventStore()

    # Append event
    event = Event(
        event_type=EventType.CONTRACT_PROPOSED,
        tenant_id=1,
        aggregate_id="contract-001",
        payload={"prana_cost": 50}
    )
    await store.append(event)

    # Reconstruct state
    projector = StateProjector()
    events = store.get_events_by_aggregate("contract-001")
    state = projector.reconstruct_contract_state(events)
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger("EventStore")


class EventType(Enum):
    """Domain event types."""

    # Contract lifecycle
    CONTRACT_PROPOSED = "contract_proposed"
    CONTRACT_AGREED = "contract_agreed"
    CONTRACT_REJECTED = "contract_rejected"
    CONTRACT_COUNTERED = "contract_countered"
    CONTRACT_EXECUTING = "contract_executing"
    CONTRACT_SETTLED = "contract_settled"
    CONTRACT_FAILED = "contract_failed"
    CONTRACT_RETRYING = "contract_retrying"
    CONTRACT_TIMEOUT = "contract_timeout"
    CONTRACT_VETOED = "contract_vetoed"
    CONTRACT_OVERRIDDEN = "contract_overridden"

    # Agent lifecycle
    AGENT_REGISTERED = "agent_registered"
    AGENT_STARTED = "agent_started"
    AGENT_STOPPED = "agent_stopped"
    AGENT_HEALTHY = "agent_healthy"
    AGENT_UNHEALTHY = "agent_unhealthy"

    # Procedure execution
    PROCEDURE_STARTED = "procedure_started"
    PROCEDURE_STEP_STARTED = "procedure_step_started"
    PROCEDURE_STEP_COMPLETED = "procedure_step_completed"
    PROCEDURE_STEP_FAILED = "procedure_step_failed"
    PROCEDURE_COMPLETED = "procedure_completed"
    PROCEDURE_ROLLED_BACK = "procedure_rolled_back"


class ContractState(Enum):
    """Contract states for projection."""

    PROPOSED = "proposed"
    AGREED = "agreed"
    REJECTED = "rejected"
    COUNTERED = "countered"
    EXECUTING = "executing"
    SETTLED = "settled"
    FAILED = "failed"
    RETRYING = "retrying"
    TIMEOUT = "timeout"
    VETOED = "vetoed"
    OVERRIDDEN = "overridden"


@dataclass(frozen=True)
class Event:
    """
    Immutable domain event.

    Attributes:
        event_id: Unique event identifier
        event_type: Type of event
        tenant_id: Tenant ID for partitioning
        aggregate_id: ID of the aggregate (e.g., contract ID)
        aggregate_type: Type of aggregate (e.g., "contract")
        payload: Event data (JSON-serializable)
        timestamp: When the event occurred
        correlation_id: Traces event through the system
        idempotency_key: Prevents duplicate processing
        previous_hash: Hash of previous event (for chain)
        event_hash: Hash of this event
    """

    event_id: str
    event_type: EventType
    tenant_id: int
    aggregate_id: str
    aggregate_type: str
    payload: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    timestamp: datetime
    previous_hash: str
    correlation_id: str | None = None
    idempotency_key: str | None = None
    event_hash: str | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if self.event_hash is None:
            object.__setattr__(self, "event_hash", self.compute_hash())

    def compute_hash(self) -> str:
        """Compute SHA-256 hash of event data."""
        data = {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "tenant_id": self.tenant_id,
            "aggregate_id": self.aggregate_id,
            "aggregate_type": self.aggregate_type,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
            "previous_hash": self.previous_hash,
            "correlation_id": self.correlation_id,
            "idempotency_key": self.idempotency_key,
        }
        canonical = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()[:32]


class EventStore:
    """
    Append-only event store.

    Stores events immutably with hash chaining for tamper evidence.
    Supports multi-tenant partitioning.

    Note: This is an in-memory implementation for Sprint D.
    Production would use PostgreSQL with partitioning.
    """

    def __init__(self) -> None:
        self._events: list[Event] = []
        self._events_by_aggregate: dict[str, list[Event]] = {}
        self._events_by_tenant: dict[int, list[Event]] = {}
        self._idempotency_keys: set[str] = set()

        logger.info("EventStore initialized")

    async def append(self, event: Event) -> bool:
        """
        Append an event to the store.

        Returns True if event was added, False if duplicate.
        """
        # Check idempotency
        if event.idempotency_key:
            if event.idempotency_key in self._idempotency_keys:
                logger.debug(f"Duplicate event rejected: {event.event_id}")
                return False
            self._idempotency_keys.add(event.idempotency_key)

        # Check for duplicate event ID
        if any(e.event_id == event.event_id for e in self._events):
            logger.debug(f"Event ID already exists: {event.event_id}")
            return False

        # Store event
        self._events.append(event)

        # Index by aggregate
        if event.aggregate_id not in self._events_by_aggregate:
            self._events_by_aggregate[event.aggregate_id] = []
        self._events_by_aggregate[event.aggregate_id].append(event)

        # Index by tenant
        if event.tenant_id not in self._events_by_tenant:
            self._events_by_tenant[event.tenant_id] = []
        self._events_by_tenant[event.tenant_id].append(event)

        logger.debug(
            f"Event appended: {event.event_type.value} "
            f"for {event.aggregate_type}:{event.aggregate_id}"
        )

        return True

    def get_events_by_aggregate(
        self, aggregate_id: str, since: datetime | None = None
    ) -> list[Event]:
        """Get all events for an aggregate, optionally filtered by time."""
        events = self._events_by_aggregate.get(aggregate_id, [])

        if since:
            events = [e for e in events if e.timestamp >= since]

        # Return sorted by timestamp
        return sorted(events, key=lambda e: e.timestamp)

    def get_events_by_tenant(self, tenant_id: int, since: datetime | None = None) -> list[Event]:
        """Get all events for a tenant, optionally filtered by time."""
        events = self._events_by_tenant.get(tenant_id, [])

        if since:
            events = [e for e in events if e.timestamp >= since]

        return sorted(events, key=lambda e: e.timestamp)

    def get_events_by_timerange(
        self, since: datetime, until: datetime | None = None
    ) -> list[Event]:
        """Get events within a time range."""
        events = self._events

        events = [e for e in events if e.timestamp >= since]

        if until:
            events = [e for e in events if e.timestamp <= until]

        return sorted(events, key=lambda e: e.timestamp)

    def query_events(
        self,
        event_type: EventType | None = None,
        tenant_id: int | None = None,
        aggregate_type: str | None = None,
        correlation_id: str | None = None,
        since: datetime | None = None,
    ) -> list[Event]:
        """Query events with filters."""
        events = self._events

        if event_type:
            events = [e for e in events if e.event_type == event_type]

        if tenant_id:
            events = [e for e in events if e.tenant_id == tenant_id]

        if aggregate_type:
            events = [e for e in events if e.aggregate_type == aggregate_type]

        if correlation_id:
            events = [e for e in events if e.correlation_id == correlation_id]

        if since:
            events = [e for e in events if e.timestamp >= since]

        return sorted(events, key=lambda e: e.timestamp)

    def verify_hash_chain(self, aggregate_id: str) -> bool:
        """
        Verify the hash chain for an aggregate.

        Returns True if chain is valid, False if tampered.
        """
        events = self.get_events_by_aggregate(aggregate_id)

        if not events:
            return True

        # Verify each event's hash
        for i, event in enumerate(events):
            computed_hash = event.compute_hash()
            if event.event_hash != computed_hash:
                logger.error(
                    f"Hash mismatch for event {event.event_id}: "
                    f"stored={event.event_hash}, computed={computed_hash}"
                )
                return False

            # Verify chain link (except for first event)
            if i > 0:
                expected_previous = events[i - 1].event_hash
                if event.previous_hash != expected_previous:
                    logger.error(
                        f"Chain break at event {event.event_id}: "
                        f"previous_hash={event.previous_hash}, "
                        f"expected={expected_previous}"
                    )
                    return False

        return True

    def get_partition_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get partition statistics."""
        events_per_tenant = {
            tenant_id: len(events) for tenant_id, events in self._events_by_tenant.items()
        }

        events_per_month: dict[str, int] = {}
        for event in self._events:
            month_key = event.timestamp.strftime("%Y-%m")
            events_per_month[month_key] = events_per_month.get(month_key, 0) + 1

        return {
            "total_events": len(self._events),
            "tenant_count": len(self._events_by_tenant),
            "aggregate_count": len(self._events_by_aggregate),
            "events_per_tenant": events_per_tenant,
            "events_per_month": events_per_month,
        }

    def get_latest_event(self, aggregate_id: str) -> Event | None:
        """Get the most recent event for an aggregate."""
        events = self.get_events_by_aggregate(aggregate_id)
        return events[-1] if events else None


class StateProjector:
    """
    Project aggregate state from event stream.

    Reconstructs the current state by replaying events.
    This is the "read model" in CQRS terminology.
    """

    def reconstruct_contract_state(self, events: list[Event]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Reconstruct contract state from events.

        Returns a dictionary with the current state.
        """
        if not events:
            return {
                "contract_id": None,
                "state": None,
                "prana_cost": 0,
                "was_vetoed": False,
                "was_overridden": False,
                "retry_count": 0,
                "created_at": None,
                "updated_at": None,
            }

        state: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "contract_id": events[0].aggregate_id,
            "state": ContractState.PROPOSED,
            "prana_cost": 0,
            "was_vetoed": False,
            "was_overridden": False,
            "retry_count": 0,
            "created_at": events[0].timestamp,
            "updated_at": events[0].timestamp,
            "metadata": {},
        }

        for event in events:
            state["updated_at"] = event.timestamp

            if event.event_type == EventType.CONTRACT_PROPOSED:
                state["state"] = ContractState.PROPOSED
                state["prana_cost"] = event.payload.get("prana_cost", 0)
                state["metadata"].update(event.payload)

            elif event.event_type == EventType.CONTRACT_AGREED:
                state["state"] = ContractState.AGREED

            elif event.event_type == EventType.CONTRACT_REJECTED:
                state["state"] = ContractState.REJECTED

            elif event.event_type == EventType.CONTRACT_COUNTERED:
                state["state"] = ContractState.COUNTERED

            elif event.event_type == EventType.CONTRACT_EXECUTING:
                state["state"] = ContractState.EXECUTING

            elif event.event_type == EventType.CONTRACT_SETTLED:
                state["state"] = ContractState.SETTLED
                state["result"] = event.payload.get("result")

            elif event.event_type == EventType.CONTRACT_FAILED:
                state["state"] = ContractState.FAILED
                state["error"] = event.payload.get("error")

            elif event.event_type == EventType.CONTRACT_RETRYING:
                state["state"] = ContractState.RETRYING
                state["retry_count"] += 1

            elif event.event_type == EventType.CONTRACT_TIMEOUT:
                state["state"] = ContractState.TIMEOUT

            elif event.event_type == EventType.CONTRACT_VETOED:
                state["state"] = ContractState.VETOED
                state["was_vetoed"] = True
                state["veto_reason"] = event.payload.get("veto_reason")

            elif event.event_type == EventType.CONTRACT_OVERRIDDEN:
                state["state"] = ContractState.OVERRIDDEN
                state["was_overridden"] = True
                state["overridden_by"] = event.payload.get("override_by")

        return state

    def reconstruct_agent_state(self, events: list[Event]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Reconstruct agent state from events."""
        if not events:
            return {
                "agent_id": None,
                "status": None,
                "capabilities": [],
                "health_score": 100,
                "registered_at": None,
                "last_heartbeat": None,
            }

        state: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "agent_id": events[0].aggregate_id,
            "status": "unknown",
            "capabilities": [],
            "health_score": 100,
            "registered_at": None,
            "last_heartbeat": None,
        }

        for event in events:
            if event.event_type == EventType.AGENT_REGISTERED:
                state["status"] = "registered"
                state["capabilities"] = event.payload.get("capabilities", [])
                state["registered_at"] = event.timestamp

            elif event.event_type == EventType.AGENT_STARTED:
                state["status"] = "running"

            elif event.event_type == EventType.AGENT_STOPPED:
                state["status"] = "stopped"

            elif event.event_type == EventType.AGENT_HEALTHY:
                state["health_score"] = event.payload.get("health_score", 100)
                state["last_heartbeat"] = event.timestamp

            elif event.event_type == EventType.AGENT_UNHEALTHY:
                state["health_score"] = event.payload.get("health_score", 50)
                state["status"] = "degraded"

        return state
