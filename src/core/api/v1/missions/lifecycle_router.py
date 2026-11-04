# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""
Missions lifecycle sub-router (ADR-033 Laag 1).

Routes:
- POST /{id}/approve          Approve a mission step
- POST /{id}/reject           Reject a mission step
- GET  /{id}/steps/{sid}/explainability  AI Act explainability
"""

import logging
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from src.core.api.auth.dependencies import validate_csrf_token
from src.core.api.v1.missions.dependencies import (
    CouncilDecisionRow,
    OAuth2Scope,
    get_db,
    require_scopes,
)
from src.core.api.v1.missions.schemas import (
    ApproveRequest,
    MissionResponse,
    RejectRequest,
    _orm_to_pydantic,
    _parse_mission_id,
    find_next_pending_step,
    get_tenant,
    get_user_id,
    update_mission_status,
)
from src.core.models.mission_models import Mission as MissionORM
from src.core.models.rbac_models import User

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/{mission_id}/approve",
    response_model=MissionResponse,
    summary="Approve a mission step",
    description="Approves the next pending step or a specific step in a mission.",
)
async def approve_mission_step(
    mission_id: str = Path(..., description="Mission ID"),
    request: ApproveRequest | None = None,
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(get_tenant),
    current_user: User = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
    _csrf: None = Depends(validate_csrf_token),
) -> MissionResponse:
    """Approve a mission step. Requires JWT with agents:write scope."""
    user_id = get_user_id(current_user)
    now = datetime.now(timezone.utc).isoformat()
    mission_uuid = _parse_mission_id(mission_id)

    logger.info(
        "Approving mission step",
        extra={
            "mission_id": mission_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "step_id": request.step_id if request else None,
        },
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mission not found")

    payload = mission.payload or {}
    steps = payload.get("steps", [])

    step_to_approve = None
    if request and request.step_id:
        for step in steps:
            if step.get("id") == request.step_id:
                step_to_approve = step
                break
        if not step_to_approve:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Step '{request.step_id}' not found in mission",
            )
    else:
        step_to_approve = find_next_pending_step(steps)
        if not step_to_approve:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No pending steps to approve",
            )

    if step_to_approve.get("status") not in ["pending"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Step is in '{step_to_approve.get('status')}' status, cannot approve",
        )

    step_to_approve["status"] = "approved"
    step_to_approve["approved_by"] = user_id
    step_to_approve["approved_at"] = now

    payload["steps"] = steps
    mission.payload = payload
    flag_modified(mission, "payload")
    mission.status = update_mission_status(steps)
    mission.updated_at = datetime.now(timezone.utc)

    await db.commit()

    logger.info(
        "Mission step approved",
        extra={
            "mission_id": mission_id,
            "step_id": step_to_approve.get("id"),
            "new_mission_status": mission.status,
        },
    )

    return MissionResponse(
        mission=_orm_to_pydantic(mission),
        message=f"Step '{step_to_approve.get('description')}' approved successfully",
        action="approve",
        timestamp=now,
    )


@router.post(
    "/{mission_id}/reject",
    response_model=MissionResponse,
    summary="Reject a mission step",
    description="Rejects the next pending step or a specific step in a mission.",
)
async def reject_mission_step(
    mission_id: str = Path(..., description="Mission ID"),
    request: RejectRequest | None = None,
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(get_tenant),
    current_user: User = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
    _csrf: None = Depends(validate_csrf_token),
) -> MissionResponse:
    """Reject a mission step. Requires JWT with agents:write scope."""
    user_id = get_user_id(current_user)
    now = datetime.now(timezone.utc).isoformat()
    mission_uuid = _parse_mission_id(mission_id)

    if request is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request body is required with rejection reason",
        )

    logger.info(
        "Rejecting mission step",
        extra={
            "mission_id": mission_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "step_id": request.step_id,
            "reason": request.reason,
        },
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Mission not found")

    payload = mission.payload or {}
    steps = payload.get("steps", [])

    step_to_reject = None
    if request.step_id:
        for step in steps:
            if step.get("id") == request.step_id:
                step_to_reject = step
                break
        if not step_to_reject:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Step '{request.step_id}' not found in mission",
            )
    else:
        step_to_reject = find_next_pending_step(steps)
        if not step_to_reject:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No pending steps to reject",
            )

    if step_to_reject.get("status") not in ["pending", "approved"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Step is in '{step_to_reject.get('status')}' status, cannot reject",
        )

    step_to_reject["status"] = "rejected"
    step_to_reject["rejected_by"] = user_id
    step_to_reject["rejected_at"] = now
    step_to_reject["rejection_reason"] = request.reason

    payload["steps"] = steps
    mission.payload = payload
    flag_modified(mission, "payload")
    mission.status = update_mission_status(steps)
    mission.updated_at = datetime.now(timezone.utc)

    await db.commit()

    logger.info(
        "Mission step rejected",
        extra={
            "mission_id": mission_id,
            "step_id": step_to_reject.get("id"),
            "new_mission_status": mission.status,
            "rejection_reason": request.reason,
        },
    )

    return MissionResponse(
        mission=_orm_to_pydantic(mission),
        message=f"Step '{step_to_reject.get('description')}' rejected: {request.reason}",
        action="reject",
        timestamp=now,
    )


@router.get(
    "/{mission_id}/steps/{step_id}/explainability",
    summary="Get mission step explainability",
    description="Retrieves AI Act explainability details for a specific mission step.",
)
async def get_step_explainability(
    mission_id: str = Path(..., description="Mission ID"),
    step_id: str = Path(..., description="Step ID"),
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(get_tenant),
    current_user: User = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get explainability for a mission step. Requires JWT with agents:read scope."""
    user_id = get_user_id(current_user)

    logger.info(
        "explainability_requested",
        extra={
            "mission_id": mission_id,
            "step_id": step_id,
            "tenant_id": tenant_id,
            "user_id": user_id,
        },
    )

    try:
        step_uuid = UUID(step_id)
    except ValueError:
        return {
            "success": True,
            "data": {
                "available": False,
                "reason": "Invalid step_id format. Must be a valid UUID.",
            },
        }

    mission_uuid = _parse_mission_id(mission_id)

    mission_result = await db.execute(
        select(MissionORM).where(
            MissionORM.id == mission_uuid,
            MissionORM.tenant_id == tenant_id,
            MissionORM.deleted_at.is_(None),
        )
    )
    mission = mission_result.scalar_one_or_none()
    if mission is None:
        return {
            "success": True,
            "data": {"available": False, "reason": "Mission not found for this tenant."},
        }

    mission_steps = (mission.payload or {}).get("steps", [])
    if not any(str(step.get("id")) == step_id for step in mission_steps):
        return {
            "success": True,
            "data": {
                "available": False,
                "reason": "Step does not belong to the specified mission.",
            },
        }

    try:
        result = await db.execute(
            select(CouncilDecisionRow)
            .where(
                CouncilDecisionRow.tenant_id == tenant_id,
                CouncilDecisionRow.proposal_id == step_uuid,
            )
            .order_by(CouncilDecisionRow.timestamp.desc())
            .limit(1)
        )
        decision = result.scalar_one_or_none()

        if decision is None:
            return {
                "success": True,
                "data": {
                    "available": False,
                    "reason": "No council deliberation recorded for this step.",
                },
            }

        return {
            "success": True,
            "data": {
                "available": True,
                "step_id": step_id,
                "agent_type": decision.trigger or "unknown",
                "decision_rationale": decision.explanation_for_user,
                "verdict": decision.verdict,
                "deliberation_ms": decision.deliberation_ms,
                "human_reviewed": decision.verdict == "APPROVED_WITH_OVERRIDE",
                "risk_level": None,
            },
        }

    except Exception as e:
        logger.error(
            "explainability_fetch_failed: %s: %s",
            type(e).__name__,
            e,
            exc_info=True,
            extra={"tenant_id": tenant_id, "step_id": step_id},
        )
        raise
