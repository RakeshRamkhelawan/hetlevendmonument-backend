"""Agentic routing sub-router (ADR-033 Laag 1)."""
# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from src.core.api.v1.agentic.dependencies import AdaptationRuleService, get_adaptation_service
from src.core.auth.api_deps import get_current_user
from src.core.exceptions import AuthError
from src.core.middleware.tenant_context import require_tenant_id
from src.core.routing.router_orchestrator import GunaRouter, RouterRequest, RouterResponse
from src.core.shared.interfaces import TaskData

logger = logging.getLogger(__name__)

agentic_routing_router = APIRouter()


class RouteRequest(BaseModel):
    query: str


class RouteResponse(BaseModel):
    supervisor_id: str
    confidence: float
    routing_path: list[str]


@agentic_routing_router.post("/route", response_model=RouteResponse)
async def route_query(
    request: RouteRequest,
    service: AdaptationRuleService | None = Depends(get_adaptation_service),
    _current_user: object = Depends(get_current_user),
) -> RouteResponse:
    """Route a query to the appropriate supervisor."""
    try:
        guna_router = GunaRouter()
        tenant_id_int = require_tenant_id()
        task_data = TaskData(title=request.query, description=request.query)
        route_request = RouterRequest(task=task_data, tenant_id=tenant_id_int)
        result: RouterResponse = await guna_router.route(route_request)
        return RouteResponse(
            supervisor_id=result.target_supervisor,
            confidence=result.confidence,
            routing_path=[result.target_supervisor],
        )
    except AuthError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.error("routing failed: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Internal error") from e
