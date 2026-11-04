# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""Orchestration stats endpoint (ADR-033 Laag 1)."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from src.core.api.v1.orchestration.dependencies import (
    AgentHealthMonitorAgent,
    AgentRouterAgent,
    MasterOrchestratorAgent,
    get_agent_router,
    get_current_tenant_id,
    get_health_monitor,
    get_master_orchestrator,
)
from src.core.api.v1.orchestration.schemas import OrchestrationStatsResponse
from src.core.api.v1.orchestration.dependencies import limiter

logger = logging.getLogger(__name__)

stats_router = APIRouter()


def _get_tenant_id(tenant_id: int | None = Depends(get_current_tenant_id)) -> int:
    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Tenant context required for this operation",
        )
    return tenant_id


@stats_router.get("/stats", response_model=OrchestrationStatsResponse)
@limiter.limit("10/minute")
async def get_stats(
    request: Request,
    response: Response,
    orchestrator: MasterOrchestratorAgent = Depends(get_master_orchestrator),
    agent_router: AgentRouterAgent = Depends(get_agent_router),
    health_monitor: AgentHealthMonitorAgent = Depends(get_health_monitor),
    tenant_id: int = Depends(_get_tenant_id),
) -> OrchestrationStatsResponse:
    """Get comprehensive orchestration statistics."""
    cache_stats = agent_router.get_cache_stats()
    active_workflows = orchestrator.get_active_workflow_count()
    registered_agents = agent_router.get_registered_agent_count()

    return OrchestrationStatsResponse(
        tenant_id=tenant_id,
        master_orchestrator_id=orchestrator.agent_id,
        router_id=agent_router.agent_id,
        health_monitor_id=health_monitor.agent_id,
        registered_agents=registered_agents,
        active_workflows=active_workflows,
        cache_stats=cache_stats,
    )
