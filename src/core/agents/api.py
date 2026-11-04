"""Agent runtime facade -- ADR-034 service boundary (external access only)."""

import logging
from typing import Protocol, runtime_checkable

from src.core.shared.interfaces import AgentCapability, AgentStatus, ExecutionResult, TaskData

__all__ = [
    "ICacheBackend",
    "IAgentRuntime",
    "ICapabilityRegistry",
    "IHealthMonitor",
    "get_agent_runtime",
    "get_health_monitor",
    "register_agent_runtime",
    "register_health_monitor",
]

logger = logging.getLogger(__name__)


@runtime_checkable
class IAgentRuntime(Protocol):
    """Public facade interface for agent_runtime (ADR-034)."""

    async def orchestrate(self, task: TaskData) -> ExecutionResult: ...

    async def route(self, task: TaskData) -> ExecutionResult: ...

    async def get_health(self) -> dict[str, object]: ...


@runtime_checkable
class ICacheBackend(Protocol):
    """Generic async cache backend for agent_runtime components (SP-AGT-004 Dag 2)."""

    async def set(self, key: str, value: str, ttl: int) -> None: ...

    async def get(self, key: str) -> str | None: ...

    async def keys(self, pattern: str) -> list[str]: ...


@runtime_checkable
class ICapabilityRegistry(Protocol):
    """Interface for capability discovery and registration (SP-AGT-004)."""

    async def discover(self, query: str, tenant_id: int) -> list[AgentCapability]: ...

    async def register_agent(self, tenant_id: int, capability: AgentCapability) -> None: ...


@runtime_checkable
class IHealthMonitor(Protocol):
    """Health-bridge write interface (CG-005)."""

    async def update_agent_health(
        self,
        agent_id: str,
        status: AgentStatus,
        metrics: dict[str, float],
    ) -> None: ...


_agent_runtime_instance: IAgentRuntime | None = None
_health_monitor_instance: IHealthMonitor | None = None


def get_agent_runtime() -> IAgentRuntime:
    """Return the registered IAgentRuntime. Raises RuntimeError if not registered."""
    if _agent_runtime_instance is None:
        raise RuntimeError(
            "agent_runtime not registered. Call register_agent_runtime() in app lifespan."
        )
    return _agent_runtime_instance


def register_agent_runtime(runtime: IAgentRuntime) -> None:
    """Register the concrete IAgentRuntime (once at startup)."""
    global _agent_runtime_instance
    if _agent_runtime_instance is not None:
        logger.warning(
            "agent_runtime already registered as %s, overwriting with %s",
            type(_agent_runtime_instance).__name__,
            type(runtime).__name__,
        )
    _agent_runtime_instance = runtime
    logger.info("agent_runtime registered: %s", type(runtime).__name__)


def get_health_monitor() -> IHealthMonitor | None:
    """Return the registered IHealthMonitor, or None if not registered."""
    return _health_monitor_instance


def register_health_monitor(monitor: IHealthMonitor) -> None:
    """Register the concrete IHealthMonitor (once at startup)."""
    global _health_monitor_instance
    _health_monitor_instance = monitor
    logger.info("health_monitor registered: %s", type(monitor).__name__)
