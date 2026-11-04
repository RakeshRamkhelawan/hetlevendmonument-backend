# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""Privacy human review endpoints (ADR-033 Laag 1, GDPR Art. 22(3))."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.v1.privacy.dependencies import (
    AITransparencyService,
    HumanReviewRequest,
    ai_transparency_limit,
    get_current_user,
    get_db,
    human_review_limit,
)
from src.core.models.rbac_models import User

logger = logging.getLogger(__name__)

human_review_router = APIRouter()


class HumanReviewRequestPayload(BaseModel):
    decision_id: int
    reason: str


@human_review_router.post("/human-review")
@human_review_limit
async def request_human_review(
    request: Request,
    review_request: HumanReviewRequestPayload,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Request human review of an AI decision (GDPR Art. 22(3))."""
    service = AITransparencyService(db)

    try:
        review = await service.request_human_review(
            decision_id=str(review_request.decision_id),
            user_id=str(current_user.id),
            reason=review_request.reason,
        )

        return {
            "status": "success",
            "message": "Human review requested",
            "review_id": review.review_id,
            "review_status": review.status,
            "estimated_resolution_days": review.estimated_resolution_days,
            "user_rights": review.user_rights,
        }
    except Exception as e:
        logger.error("Failed to request human review: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Failed to request human review",
        )


@human_review_router.get("/human-review-requests")
@ai_transparency_limit
async def get_human_review_requests(
    request: Request,
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get human review requests for the current user."""
    from sqlalchemy import func, select

    count_query = (
        select(func.count())
        .select_from(HumanReviewRequest)
        .where(HumanReviewRequest.user_id == str(current_user.id))
    )
    total_result = await db.execute(count_query)
    total_count = total_result.scalar() or 0

    result = await db.execute(
        select(HumanReviewRequest)
        .where(HumanReviewRequest.user_id == str(current_user.id))
        .order_by(HumanReviewRequest.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    requests = result.scalars().all()

    return {
        "requests": [
            {
                "id": r.id,
                "decision_id": r.decision_id,
                "reason": r.reason,
                "status": r.status,
                "reviewer_notes": r.reviewer_notes,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "reviewed_at": r.reviewed_at.isoformat() if r.reviewed_at else None,
            }
            for r in requests
        ],
        "limit": limit,
        "offset": offset,
        "total_count": total_count,
    }
