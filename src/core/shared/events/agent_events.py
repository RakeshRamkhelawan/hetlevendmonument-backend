"""Agent event types en IEventBus Protocol voor governance-decoupling (ADR-034 s5.5).

Agents publiceren events naar IEventBus; governance-modules abonneren zich.
Dit doorbreekt directe agent_runtime -> governance imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Protocol, TypeVar, runtime_checkable


@dataclass(frozen=True)
class AgentEvent:
    """Base class voor alle agent domain events."""

    tenant_id: int
    occurred_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(frozen=True)
class AgentCapabilityRegistered(AgentEvent):
    """Published when an agent registers a new capability."""

    capability_name: str = ""
    agent_id: str = ""


@dataclass(frozen=True)
class AgentExecutionRequested(AgentEvent):
    """Published when agent execution is requested (pre-oversight hook)."""

    agent_id: str = ""
    task_type: str = ""
    risk_level: str = "LOW"


@dataclass(frozen=True)
class AgentExecutionCompleted(AgentEvent):
    """Published when agent execution completes (audit hook)."""

    agent_id: str = ""
    task_type: str = ""
    success: bool = True


# Public TypeVar export for external callers typing generic event handlers.
AnyAgentEvent = TypeVar("AnyAgentEvent", bound=AgentEvent)


@runtime_checkable
class IEventBus(Protocol):
    """Async event bus voor agent domain events."""

    async def publish(self, event: AgentEvent) -> None:
        """Publish een event naar alle geregistreerde subscribers."""
        ...
