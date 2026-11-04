# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""
Missions CRUD sub-router (ADR-033 Laag 1).

Routes:
- POST /        Create mission
- POST /simple  Create mission (simple, query params)
- GET /         List missions
- GET /{id}     Get mission
- DELETE /{id}  Soft-delete mission
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.auth.dependencies import validate_csrf_token
from src.core.api.v1.missions.dependencies import OAuth2Scope, get_db, require_scopes
from src.core.api.v1.missions.schemas import (
    AgentType,
    CreateMissionRequest,
    Mission,
    MissionListResponse,
    MissionStatus,
    _orm_to_pydantic,
    _parse_mission_id,
    get_tenant,
    get_user_id,
)
from src.core.models.mission_models import Mission as MissionORM
from src.core.models.rbac_models import User

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/",
    response_model=Mission,
    status_code=status.HTTP_201_CREATED,
    summary="Create a mission",
    description="Creates a new mission.",
)
async def create_mission(
    request: CreateMissionRequest,
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(get_tenant),
    current_user: User = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
    _csrf: None = Depends(validate_csrf_token),
) -> Mission:
    """Create a new mission. Requires JWT with agents:write scope."""
    user_id = get_user_id(current_user)

    logger.info(
        "Creating mission",
        extra={"tenant_id": tenant_id, "user_id": user_id, "title": request.title},
    )

    mission = MissionORM(
        tenant_id=tenant_id,
        user_id=current_user.id if hasattr(current_user, "id") else None,
        created_by=user_id,
        title=request.title,
        description=request.description,
        agent_type=request.agent_type.value,
        status=MissionStatus.PLANNED.value,
        payload={"steps": [step.model_dump() for step in request.steps]},
    )
    db.add(mission)
    await db.commit()
    await db.refresh(mission)

    logger.info(
        "Mission created",
        extra={"mission_id": str(mission.id), "tenant_id": tenant_id, "user_id": user_id},
    )

    return _orm_to_pydantic(mission)


@router.post(
    "/simple",
    response_model=Mission,
    status_code=status.HTTP_201_CREATED,
    summary="Create a mission (simple)",
    description="Creates a new mission using query parameters.",
)
async def create_mission_simple(
    title: str = Query(..., description="Mission title"),
    description: str = Query("", description="Mission description"),
    agent_type: AgentType = Query(AgentType.WORKFLOW, description="Agent type"),
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(get_tenant),
    current_user: User = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
    _csrf: None = Depends(validate_csrf_token),
) -> Mission:
    """Create a new mission via query parameters. Requires JWT with agents:write scope."""
    import uuid

    user_id = get_user_id(current_user)

    logger.info(
        "Creating mission (simple)",
        extra={
            "tenant_id": tenant_id,
            "user_id": user_id,
            "title": title,
            "agent_type": agent_type,
        },
    )

    mission = MissionORM(
        tenant_id=tenant_id,
        user_id=current_user.id if hasattr(current_user, "id") else None,
        created_by=user_id,
        title=title,
        description=description,
        agent_type=agent_type.value,
        status=MissionStatus.PLANNED.value,
        payload={
            "steps": [
                {
                    "id": f"step_1_{uuid.uuid4().hex[:8]}",
                    "order": 1,
                    "description": "Initialize agent",
                    "action_type": "init",
                    "status": "pending",
                    "requires_approval": True,
                    "approved_by": None,
                    "approved_at": None,
                    "rejected_by": None,
                    "rejected_at": None,
                    "rejection_reason": None,
                    "duration_ms": None,
                    "cost_usd": None,
                    "error": None,
                },
                {
                    "id": f"step_2_{uuid.uuid4().hex[:8]}",
                    "order": 2,
                    "description": "Execute primary task",
                    "action_type": "execute",
                    "status": "pending",
                    "requires_approval": True,
                    "approved_by": None,
                    "approved_at": None,
                    "rejected_by": None,
                    "rejected_at": None,
                    "rejection_reason": None,
                    "duration_ms": None,
                    "cost_usd": None,
                    "error": None,
                },
                {
                    "id": f"step_3_{uuid.uuid4().hex[:8]}",
                    "order": 3,
                    "description": "Finalize and report",
                    "action_type": "finalize",
                    "status": "pending",
                    "requires_approval": False,
                    "approved_by": None,
                    "approved_at": None,
                    "rejected_by": None,
                    "rejected_at": None,
                    "rejection_reason": None,
                    "duration_ms": None,
                    "cost_usd": None,
                    "error": None,
                },
            ],
            "impact": {
                "time_saved": "1 hour",
                "cost_impact": 0.02,
                "risk_score": 10.0,
                "bias_detected": [],
            },
        },
    )
    db.add(mission)
    await db.commit()
    await db.refresh(mission)

    logger.info(
        "Mission created (simple)",
        extra={"mission_id": str(mission.id), "tenant_id": tenant_id, "user_id": user_id},
    )

    return _orm_to_pydantic(mission)


@router.get(
    "/",
    response_model=MissionListResponse,
    summary="List missions",
    description="Lists all missions for the tenant.",
)
async def list_missions(
    status_filter: MissionStatus | None = Query(None, description="Filter by status"),
    agent_type: AgentType | None = Query(None, description="Filter by agent type"),
    agent_id: str | None = Query(None, description="Filter by agent ID"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(10, ge=1, le=100, description="Page size"),
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(get_tenant),
    current_user: User = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> MissionListResponse:
    """List missions for the current tenant. Requires JWT with agents:read scope."""
    user_id = get_user_id(current_user)

    logger.info(
        "Listing missions",
        extra={
            "tenant_id": tenant_id,
            "user_id": user_id,
            "status_filter": status_filter,
            "agent_type": agent_type,
            "page": page,
            "page_size": page_size,
        },
    )

    query = select(MissionORM).where(
        MissionORM.tenant_id == tenant_id,
        MissionORM.deleted_at.is_(None),
    )

    if status_filter:
        query = query.where(MissionORM.status == status_filter.value)
    if agent_type:
        query = query.where(MissionORM.agent_type == agent_type.value)
    if agent_id:
        query = query.where(MissionORM.payload.contains({"agent_id": agent_id}))

    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar() or 0

    query = (
        query.order_by(MissionORM.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    )

    result = await db.execute(query)
    missions = result.scalars().all()

    return MissionListResponse(
        missions=[_orm_to_pydantic(m) for m in missions],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{mission_id}",
    response_model=Mission,
    summary="Get mission details",
    description="Retrieves details of a specific mission.",
)
async def get_mission(
    mission_id: str = Path(..., description="Mission ID"),
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(get_tenant),
    current_user: User = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> Mission:
    """Get mission details by ID. Requires JWT with agents:read scope."""

    user_id = get_user_id(current_user)
    mission_uuid = _parse_mission_id(mission_id)

    logger.info(
        "Getting mission details",
        extra={"mission_id": mission_id, "tenant_id": tenant_id, "user_id": user_id},
    )

    result = await db.execute(
        select(MissionORM).where(
            MissionORM.id == mission_uuid,
            MissionORM.tenant_id == tenant_id,
            MissionORM.deleted_at.is_(None),
        )
    )
    mission = result.scalar_one_or_none()
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")

    return _orm_to_pydantic(mission)


@router.delete(
    "/{mission_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a mission",
    description="Soft deletes a mission by setting deleted_at timestamp.",
)
async def delete_mission(
    mission_id: str = Path(..., description="Mission ID"),
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(get_tenant),
    current_user: User = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
    _csrf: None = Depends(validate_csrf_token),
) -> None:
    """Soft delete a mission. Requires JWT with agents:write scope."""

    user_id = get_user_id(current_user)
    mission_uuid = _parse_mission_id(mission_id)

    logger.info(
        "Deleting mission",
        extra={"mission_id": mission_id, "tenant_id": tenant_id, "user_id": user_id},
    )

    result = await db.execute(
        select(MissionORM).where(
            MissionORM.id == mission_uuid,
            MissionORM.tenant_id == tenant_id,
            MissionORM.deleted_at.is_(None),
        )
    )
    mission = result.scalar_one_or_none()
    if mission is None:
        raise HTTPException(status_code=404, detail="Mission not found")

    mission.deleted_at = datetime.now(timezone.utc)
    await db.commit()

    logger.info(
        "Mission soft deleted",
        extra={"mission_id": mission_id, "tenant_id": tenant_id},
    )
