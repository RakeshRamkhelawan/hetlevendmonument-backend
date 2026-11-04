# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""Privacy AI transparency + profiling opt-out endpoints (ADR-033 Laag 1, GDPR Art. 13/14/21/22)."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.v1.privacy.dependencies import (
    AIDecision,
    AITransparencyService,
    ProfilingType,
    UserProfilingOptOut,
    ai_transparency_limit,
    get_current_user,
    get_db,
)
from src.core.models.rbac_models import User

logger = logging.getLogger(__name__)

ai_transparency_router = APIRouter()


class ProfilingOptOutRequest(BaseModel):
    profiling_type: str
    opt_out: bool


@ai_transparency_router.get("/ai-decisions")
@ai_transparency_limit
async def get_ai_decisions(
    request: Request,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get AI decisions for the current user (GDPR Art. 13/14)."""
    from sqlalchemy import func, select

    count_query = (
        select(func.count())
        .select_from(AIDecision)
        .where(
            AIDecision.user_id == str(current_user.id),
            AIDecision.tenant_id == current_user.tenant_id,
        )
    )
    total_result = await db.execute(count_query)
    total_count = total_result.scalar() or 0

    result = await db.execute(
        select(AIDecision)
        .where(
            AIDecision.user_id == str(current_user.id),
            AIDecision.tenant_id == current_user.tenant_id,
        )
        .order_by(AIDecision.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    decisions = result.scalars().all()

    return {
        "decisions": [
            {
                "id": d.id,
                "agent_id": d.agent_id,
                "decision_type": d.decision_type,
                "explanation": d.explanation,
                "confidence_score": d.confidence_score,
                "profiling_involved": d.profiling_involved,
                "human_review_available": d.human_review_available,
                "human_review_requested": d.human_review_requested,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in decisions
        ],
        "limit": limit,
        "offset": offset,
        "total_count": total_count,
    }


@ai_transparency_router.get("/profiling-opt-out")
@ai_transparency_limit
async def get_profiling_opt_out(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get profiling opt-out status (GDPR Art. 21)."""
    from sqlalchemy import select

    result = await db.execute(
        select(UserProfilingOptOut).where(
            UserProfilingOptOut.user_id == str(current_user.id),
            UserProfilingOptOut.tenant_id == current_user.tenant_id,
        )
    )
    opt_outs = result.scalars().all()

    return {
        "opt_outs": [
            {
                "profiling_type": o.profiling_type,
                "opted_out": o.opted_out,
                "created_at": o.created_at.isoformat() if o.created_at else None,
            }
            for o in opt_outs
        ],
    }


@ai_transparency_router.post("/profiling-opt-out")
@ai_transparency_limit
async def update_profiling_opt_out(
    request: Request,
    optout_request: ProfilingOptOutRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Update profiling opt-out preference (GDPR Art. 21)."""
    service = AITransparencyService(db)

    try:
        await service.set_profiling_opt_out(
            user_id=str(current_user.id),
            tenant_id=current_user.tenant_id,
            profiling_type=ProfilingType(optout_request.profiling_type),
            opt_out=optout_request.opt_out,
        )

        return {
            "status": "success",
            "message": f"Profiling opt-out updated for {optout_request.profiling_type}",
            "profiling_type": optout_request.profiling_type,
            "opted_out": optout_request.opt_out,
        }
    except Exception as e:
        logger.error(
            "Failed to update profiling opt-out: %s: %s", type(e).__name__, e, exc_info=True
        )
        raise HTTPException(
            status_code=500,
            detail="Failed to update profiling opt-out preference",
        )
