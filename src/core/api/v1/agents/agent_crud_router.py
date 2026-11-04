"""
Agent CRUD sub-router (ADR-033 Laag 1).

Routes: POST /register, POST /, POST /agent/register, GET /, GET /{agent_id}, PATCH /{agent_id}
"""

from __future__ import annotations

import logging
import uuid
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from src.core.api.v1.agents.dependencies import AgentRegistry
    from src.core.api.v1.agents.dependencies import AgentRegistryRepository

from src.core.api.v1.agents.dependencies import (
    OAuth2Scope,
    UserResponse,
    get_agent_registry_dependency,
    get_agent_registry_repository_dependency,
    get_current_user_dependency,
    get_db,
    require_scopes,
)
from src.core.api.agent_endpoints import (
    AgentRegistrationRequest,
    AgentRegistrationResponse,
    AgentUpdateRequest,
    SimpleAgentRegistrationRequest,
    _perform_registration,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Agents"])


@router.post(
    "/register",
    response_model=AgentRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_agent(
    request: AgentRegistrationRequest,
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
    registry: "AgentRegistry" = Depends(get_agent_registry_dependency),
) -> AgentRegistrationResponse:
    """Advanced registration accepting explicit agent identifiers."""
    logger.info(
        "User %s registering agent %s",
        getattr(current_user, "id", None),
        request.agent_id,
    )
    result = await _perform_registration(
        registry,
        agent_id=request.agent_id,
        address=request.address,
        agent_type_value=request.agent_type,
        capabilities=request.capabilities,
    )
    return AgentRegistrationResponse(
        success=result.success, message=result.message, agent_id=result.agent_id, id=result.id
    )


@router.post("/", response_model=AgentRegistrationResponse, status_code=status.HTTP_201_CREATED)
@router.post(
    "/agent/register",
    response_model=AgentRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_agent_minimal(
    request: SimpleAgentRegistrationRequest,
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
    registry: "AgentRegistry" = Depends(get_agent_registry_dependency),
) -> AgentRegistrationResponse:
    """Simplified registration backing the unit tests."""
    generated_id = request.name.lower().replace(" ", "_")
    agent_id = f"{generated_id}_{uuid.uuid4().hex[:6]}"
    capabilities = request.capabilities or [f"handle_{request.type}"]
    address = f"agent://{agent_id}"

    result = await _perform_registration(
        registry,
        agent_id=agent_id,
        address=address,
        agent_type_value=request.type,
        capabilities=capabilities,
        name=request.name,
        description=request.description,
    )
    return AgentRegistrationResponse(
        success=result.success, message=result.message, agent_id=result.agent_id, id=result.id
    )


@router.get("/", response_model=dict[str, Any])
async def list_agents(
    category: str | None = Query(default=None),
    capability: str | None = Query(default=None),
    source: str | None = Query(default=None),
    limit: int = Query(default=50, le=1000),
    offset: int = Query(default=0, ge=0),
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
    registry: "AgentRegistry" = Depends(get_agent_registry_dependency),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Return all agents: enterprise catalog (YAML) + ActivePieces integrations."""
    from src.core.api.agent_endpoints import list_agents as _list_agents_impl

    result = await _list_agents_impl(
        category, capability, source, limit, offset, current_user, _, registry
    )
    return {"success": True, "data": {"agents": result.agents, "total_count": result.total_count}}


@router.get("/{agent_id}")
async def get_agent_details(
    agent_id: str,
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
    repo: "AgentRegistryRepository" = Depends(get_agent_registry_repository_dependency),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Return a single agent by agent_id with tenant-safe filtering."""
    tenant_id = getattr(current_user, "tenant_id", None)
    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Tenant context required."
        )

    agent = await repo.get_registered_agent_by_agent_id(agent_id, tenant_id)
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent {agent_id} not found",
        )

    agent_data: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
        "id": agent.id,
        "agent_id": agent.agent_id,
        "name": agent.name,
        "description": agent.description,
        "address": agent.address,
        "capabilities": agent.capabilities or [],
        "tenant_id": agent.tenant_id,
        "last_heartbeat": (agent.last_heartbeat.isoformat() if agent.last_heartbeat else None),
        "created_at": agent.created_at.isoformat() if agent.created_at else None,
        "updated_at": agent.updated_at.isoformat() if agent.updated_at else None,
    }
    return {"success": True, "data": agent_data}


@router.patch("/{agent_id}")
async def update_agent_details(
    agent_id: str,
    request: AgentUpdateRequest,
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
    session: AsyncSession = Depends(get_db),
    repo: "AgentRegistryRepository" = Depends(get_agent_registry_repository_dependency),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Partially update mutable agent fields by agent_id."""
    tenant_id = getattr(current_user, "tenant_id", None)
    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Tenant context required."
        )

    agent = await repo.get_registered_agent_by_agent_id(agent_id, tenant_id)
    if agent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent {agent_id} not found",
        )

    updates = request.model_dump(exclude_none=True)
    if "capabilities" in updates:
        updates["capabilities"] = {cap: f"Capability: {cap}" for cap in updates["capabilities"]}

    await repo.update_agent(agent_id, tenant_id, updates)
    await session.commit()
    await session.refresh(agent)

    update_data: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
        "message": f"Agent {agent_id} updated successfully",
        "agent": {
            "id": agent.id,
            "agent_id": agent.agent_id,
            "name": agent.name,
            "description": agent.description,
            "address": agent.address,
            "capabilities": (
                list((agent.capabilities or {}).keys())
                if isinstance(agent.capabilities, dict)
                else (agent.capabilities or [])
            ),
            "tenant_id": agent.tenant_id,
        },
    }
    return {"success": True, "data": update_data}
