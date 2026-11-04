"""AgentConfig API Router."""
# orphan:exempt reason: pre-ADR-033 domain sub-file, pending Strangler Fig migration (Dag 4/5)

from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from src.core.api.dependencies import get_db
from src.core.auth.api_deps import UserResponse, get_current_user
from src.core.repositories.agent_config_repository import AgentConfigRepository
from src.core.api.v1.agent_configs.dependencies import (
    AgentConfigCreateRequest,
    AgentConfigUpdateRequest,
    AgentConfigResponse,
    CircuitStatusResponse,
    _to_response,
)

router = APIRouter(prefix="/agent-configs", tags=["Agent Configuration"])


@router.post(
    "",
    response_model=AgentConfigResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Agent Config",
)
async def create_agent_config(
    request: AgentConfigCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentConfigResponse:
    repo = AgentConfigRepository(db)
    try:
        cfg = await repo.create(
            tenant_id=current_user.tenant_id,
            agent_type=request.agent_type,
            agent_id=request.agent_id,
            department=request.department,
            department_user_id=request.department_user_id,
            subscribed_topics=request.subscribed_topics,
            is_active=request.is_active,
            config_json=request.config_json,
        )
        return _to_response(cfg)
    except Exception as exc:
        if "unique" in str(exc).lower() or "integrity" in str(exc).lower():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Agent with agent_id '{request.agent_id}' already exists",
            )
        raise


@router.get("", summary="List Agent Configs")
async def list_agent_configs(
    active_only: bool = Query(default=True),
    limit: int = Query(default=50, le=1000, ge=1),
    offset: int = Query(default=0, ge=0),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    repo = AgentConfigRepository(db)
    configs = await repo.get_active_configs(
        tenant_id=current_user.tenant_id,
        active_only=active_only,
        limit=limit,
        offset=offset,
    )
    return {"data": [_to_response(c) for c in configs], "limit": limit, "offset": offset}


@router.get("/{agent_id}", response_model=AgentConfigResponse, summary="Get Agent Config")
async def get_agent_config(
    agent_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentConfigResponse:
    repo = AgentConfigRepository(db)
    cfg = await repo.get_by_agent_id(agent_id, tenant_id=current_user.tenant_id)
    if cfg is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent config '{agent_id}' not found"
        )
    return _to_response(cfg)


@router.patch("/{agent_id}", response_model=AgentConfigResponse, summary="Update Agent Config")
async def update_agent_config(
    agent_id: str,
    request: AgentConfigUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentConfigResponse:
    repo = AgentConfigRepository(db)
    cfg = await repo.get_by_agent_id(agent_id, tenant_id=current_user.tenant_id)
    if cfg is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent config '{agent_id}' not found"
        )
    update_data: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
    if request.agent_type is not None:
        update_data["agent_type"] = request.agent_type
    if request.department is not None:
        update_data["department"] = request.department
    if request.department_user_id is not None:
        update_data["department_user_id"] = request.department_user_id
    if request.subscribed_topics is not None:
        update_data["subscribed_topics"] = request.subscribed_topics
    if request.is_active is not None:
        update_data["is_active"] = request.is_active
    if request.config_json is not None:
        update_data["config_json"] = request.config_json
    updated = await repo.update(cfg.id, tenant_id=current_user.tenant_id, **update_data)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent config '{agent_id}' not found"
        )
    return _to_response(updated)


@router.delete("/{agent_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete Agent Config")
async def delete_agent_config(
    agent_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    repo = AgentConfigRepository(db)
    cfg = await repo.get_by_agent_id(agent_id, tenant_id=current_user.tenant_id)
    if cfg is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent config '{agent_id}' not found"
        )
    await repo.delete(cfg.id, tenant_id=current_user.tenant_id)


@router.get(
    "/{agent_id}/circuit",
    response_model=CircuitStatusResponse,
    summary="Get Circuit Breaker Status",
)
async def get_circuit_status(
    agent_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CircuitStatusResponse:
    repo = AgentConfigRepository(db)
    cfg = await repo.get_by_agent_id(agent_id, tenant_id=current_user.tenant_id)
    if cfg is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent config '{agent_id}' not found"
        )
    return CircuitStatusResponse(
        agent_id=agent_id, state="closed", failure_threshold=5, reset_timeout_seconds=30
    )
