import asyncio
import uuid
from datetime import datetime
from typing import Any, Optional
from collections.abc import Awaitable, Callable

from pydantic import BaseModel, Field

from src.core.memory.memory_manager import get_memory_manager_for_tenant, memory_manager
from src.core.shared.datetime_utils import utc_now

# --- DATA MODELS ---


class Event(BaseModel):
    """
    Standardized OODA Event Payload.
    Acts as the 'nerve impulse' traveling through the system.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    agent_id: str
    phase: str  # "OBSERVE", "ORIENT", "DECIDE", "ACT"
    type: str  # e.g., "SECURITY_ALERT", "EMAIL_RECEIVED", "TASK_COMPLETED"
    content: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    timestamp: datetime = Field(default_factory=utc_now)
    vector_id: str | None = None  # Reference to the stored memory in VectorDB

    def to_summary(self) -> str:
        """Returns a string suitable for embedding/logging."""
        return f"[{self.timestamp.isoformat()}] {self.agent_id} ({self.phase}): {self.type} - {str(self.content)[:200]}"


# --- EVENT BUS ---


class EventBus:
    """
    Asynchronous Pub/Sub Event Bus for the OODA Agentic System.
    Integrates with MemoryManager for long-term storage (The 'Hippocampus').
    """

    _instance: Any | None = None  # TODO(TYPE): replace Any with concrete type
    _initialized: bool = False

    def __new__(cls) -> "EventBus":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return

        # Storage for callbacks: { "channel_name": [callback_fn, ...] }
        self._subscribers: dict[str, list[Callable[..., Any]]] = {}  # TODO(TYPE): replace Any with concrete type

        # In-memory buffer for the Dashboard (The 'Short-term visual cortex')
        self._recent_events: list[Event] = []
        self._max_recent_events = 100

        self._initialized = True

    def subscribe(self, channel: str, callback: Callable[..., Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        """
        Register an async callback for a specific channel (phase).
        """
        if channel not in self._subscribers:
            self._subscribers[channel] = []
        self._subscribers[channel].append(callback)

    async def publish(self, event: Event) -> str:
        """
        1. Validate Event.
        2. Save to Vector Memory (Long-term recall).
        3. Notify subscribers.
        4. Return Event ID.
        """
        # 1. Update Short-term Buffer (for Dashboard)
        self._recent_events.insert(0, event)
        if len(self._recent_events) > self._max_recent_events:
            self._recent_events.pop()

        # 2. Save to Long-term Memory (Fire & Forget to avoid blocking)
        # We store it as an 'Episodic Memory' so agents can recall "What happened yesterday?"
        try:
            # Resolve tenant-scoped MemoryManager when possible
            _mm = memory_manager  # default: legacy global
            try:
                from src.core.middleware.tenant_context import get_tenant_id as _ctx_tid

                _tid = _ctx_tid()
                if _tid:
                    _mm = get_memory_manager_for_tenant(_tid)
            except Exception:
                pass

            vector_id = await _mm.store_memory(
                agent_id=event.agent_id,
                memory_type="learning_episode",
                content=event.model_dump(mode="json"),
                importance_score=0.5,
            )
            event.vector_id = vector_id
        except Exception as e:
            # We log but do not crash the bus if memory fails
            print(f"[EventBus] Warning: Failed to persist event to memory: {e}")

        # 3. Notify Subscribers
        channel = event.phase
        if channel in self._subscribers:
            # Execute all callbacks concurrently
            tasks = [callback(event) for callback in self._subscribers[channel]]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

        return event.id

    def get_recent_events(self, limit: int = 50) -> list[Event]:
        """Return last N events from short-term buffer."""
        return self._recent_events[:limit]

    def clear(self) -> None:
        """Clear subscribers and events (Useful for testing)."""
        self._subscribers = {}
        self._recent_events = []


# Global Singleton
event_bus = EventBus()
