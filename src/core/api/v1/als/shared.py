"""ALS shared schemas and helpers (ADR-033)."""
# orphan:exempt reason: shared module, imported by ALS sub-routers (ADR-033)

from typing import Any

from pydantic import BaseModel

from src.core.api.v1.als.dependencies import ChiefOrchestrator, SignalBus, get_redis_pool

ALS_ORCHESTRATOR_TIMEOUT_SECONDS: float = 30.0

_orchestrators: dict[int, ChiefOrchestrator] = {}


def get_orchestrator(tenant_id: int) -> ChiefOrchestrator:
    """Get or create orchestrator for tenant."""
    if tenant_id not in _orchestrators:
        pool = get_redis_pool()
        signal_bus = SignalBus(pool)
        _orchestrators[tenant_id] = ChiefOrchestrator(tenant_id=tenant_id, signal_bus=signal_bus)
    return _orchestrators[tenant_id]


class TaskRequest(BaseModel):
    """Task delegation request."""

    task_type: str
    payload: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    preferred_agents: list[str] | None = None


class TaskResponse(BaseModel):
    """Task delegation response."""

    success: bool
    task_id: str
    assigned_agent: str | None = None
    error: str | None = None


class HealthResponse(BaseModel):
    """System health response."""

    tenant_id: int
    total_agents: int
    healthy: int
    stressed: int
    health_percentage: float
    active_tasks: int
