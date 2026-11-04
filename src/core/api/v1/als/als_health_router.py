"""ALS health sub-router (ADR-033 Laag 1)."""
# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)

import asyncio

from fastapi import APIRouter, Depends, HTTPException

from src.core.api.v1.als.shared import (
    ALS_ORCHESTRATOR_TIMEOUT_SECONDS,
    HealthResponse,
    get_orchestrator,
)
from src.core.middleware.tenant_context import get_current_tenant_id

als_health_router = APIRouter()


@als_health_router.get("/health", response_model=HealthResponse)
async def get_system_health(
    tenant_id: int = Depends(get_current_tenant_id),
) -> HealthResponse:
    """Get health status of the symbiotic organism."""
    orchestrator = get_orchestrator(tenant_id)
    try:
        health = await asyncio.wait_for(
            orchestrator.get_system_health(),
            timeout=ALS_ORCHESTRATOR_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        raise HTTPException(status_code=504, detail="ALS health check timed out")

    return HealthResponse(**health)
