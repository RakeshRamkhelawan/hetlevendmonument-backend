"""
Agent management sub-router (ADR-033 Laag 1).

Routes: POST /collaborate, GET /stats, GET /health, GET /catalog
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends

if TYPE_CHECKING:
    from src.core.api.v1.agents.dependencies import AgentCouncil, AgentRegistry

from src.core.api.v1.agents.dependencies import (
    AsyncSession,
    OAuth2Scope,
    UserResponse,
    agent_execute_limit_dep,
    get_agent_registry_dependency,
    get_council_dependency,
    get_current_user_dependency,
    get_db,
    require_agent_council_approval,
    require_scopes,
)
from src.core.api.agent_endpoints import (
    AgentCollaborationRequest,
    EnterpriseCatalogResponse,
    agent_system_health,
    collaborate_agents,
    get_agent_stats,
    get_enterprise_catalog,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Agents"])


@router.post("/collaborate")
async def collaborate_agents_route(
    request: AgentCollaborationRequest,
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
    registry: "AgentRegistry" = Depends(get_agent_registry_dependency),
    council: "AgentCouncil" = Depends(get_council_dependency),
    _rl: None = Depends(agent_execute_limit_dep),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Execute a lightweight collaboration flow across multiple agents."""
    await require_agent_council_approval(
        council=council,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        action_type="agent.collaborate",
        action_params={"agent_ids": request.agent_ids or []},
        reasoning=request.query[:500],
        db=db,
    )
    return await collaborate_agents(request, current_user, _, registry)


@router.get("/stats")
async def get_agent_stats_route(
    registry: "AgentRegistry" = Depends(get_agent_registry_dependency),
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get agent statistics for dashboard."""
    return await get_agent_stats(registry, current_user, _)


@router.get("/health")
async def agent_system_health_route(
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
    registry: "AgentRegistry" = Depends(get_agent_registry_dependency),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Expose aggregate registry health metrics."""
    return await agent_system_health(current_user, _, registry)


@router.get("/health", include_in_schema=False)
async def agent_system_health_legacy_route(
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
    registry: "AgentRegistry" = Depends(get_agent_registry_dependency),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    return await agent_system_health(current_user, _, registry)


@router.get("/catalog", response_model=EnterpriseCatalogResponse)
async def get_enterprise_catalog_route(
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> EnterpriseCatalogResponse:
    """Return the complete enterprise agent catalog from YAML config."""
    return await get_enterprise_catalog(current_user, _)
