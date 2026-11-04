"""
Agent execution sub-router (ADR-033 Laag 1).

Routes: POST /execute, POST /agent/execute/{agent_id}, POST /execute/{agent_id} (legacy)
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
    AgentExecutionRequest,
    AgentQueryRequest,
    execute_agent,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Agents"])


@router.post("/execute", response_model=dict[str, Any])
async def execute_agent_dispatcher(
    request: AgentQueryRequest,
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
    registry: "AgentRegistry" = Depends(get_agent_registry_dependency),
    council: "AgentCouncil" = Depends(get_council_dependency),
    _rl: None = Depends(agent_execute_limit_dep),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Execute an agent by ID provided in the body (Dispatcher Pattern)."""
    await require_agent_council_approval(
        council=council,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        action_type="agent.execute",
        action_params={"agent_id": request.agent_id},
        reasoning=f"Execute agent {request.agent_id}",
        db=db,
    )
    return await execute_agent(
        agent_id=request.agent_id,
        request=AgentExecutionRequest(
            input=request.query,
            metadata={"use_rag": request.use_rag, "tenant_id": current_user.tenant_id},
        ),
        current_user=current_user,
        _=_,
        registry=registry,
    )


@router.post("/agent/execute/{agent_id}")
async def execute_agent_primary(
    agent_id: str,
    request: AgentExecutionRequest,
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
    registry: "AgentRegistry" = Depends(get_agent_registry_dependency),
    council: "AgentCouncil" = Depends(get_council_dependency),
    _rl: None = Depends(agent_execute_limit_dep),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Execute a specific agent with the provided payload."""
    await require_agent_council_approval(
        council=council,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        action_type="agent.execute",
        action_params={"agent_id": agent_id},
        reasoning=f"Execute agent {agent_id}",
        db=db,
    )
    return await execute_agent(agent_id, request, current_user, _, registry)


@router.post("/execute/{agent_id}", include_in_schema=False)
async def execute_agent_legacy(
    agent_id: str,
    request: AgentExecutionRequest,
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
    registry: "AgentRegistry" = Depends(get_agent_registry_dependency),
    council: "AgentCouncil" = Depends(get_council_dependency),
    _rl: None = Depends(agent_execute_limit_dep),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Legacy alias for plural route consumers."""
    await require_agent_council_approval(
        council=council,
        tenant_id=current_user.tenant_id,
        user_id=current_user.id,
        action_type="agent.execute",
        action_params={"agent_id": agent_id},
        reasoning=f"Execute agent {agent_id}",
        db=db,
    )
    return await execute_agent(agent_id, request, current_user, _, registry)
