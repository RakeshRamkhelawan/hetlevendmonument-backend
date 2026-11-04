# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""AI Features -- Adaptive Learning sub-router (ADR-033 Laag 1)."""

import uuid
from datetime import datetime, timezone
from typing import cast

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from src.core.ai.adaptive_learning_engine import (
    AdaptiveLearningEngine,
    LearningEvent,
)
from src.core.auth.api_deps import UserResponse, get_current_user, require_scopes, OAuth2Scope
from src.core.container import Container
from src.core.shared.production_logging import SafeLogger

logger = SafeLogger(__name__)

router = APIRouter()


class LearningEventRequest(BaseModel):
    """Request model voor learning events."""

    event_type: str = Field(description="Type of learning event")
    context: dict[str, object] = Field(description="Event context")
    outcome: float | str | bool | dict[str, object] | None = Field(
        default=None, description="Event outcome"
    )
    confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="Confidence in the event")
    user_id: str | None = None
    session_id: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class LearningInsightResponse(BaseModel):
    """Response model voor learning insights."""

    insights: list[dict[str, object]] = Field(description="List of learning insights")
    summary: dict[str, object] = Field(description="Summary statistics")
    timestamp: str = Field(description="Response timestamp")


@router.post("/learning/event", response_model=dict[str, object])
@inject
async def record_learning_event(
    request: LearningEventRequest,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_WRITE)),
    engine: AdaptiveLearningEngine = Depends(Provide[Container.adaptive_learning_engine]),
) -> dict[str, object]:
    """
    Record a learning event for adaptive learning system.
    Requires: WRITE permission (EDITOR level).
    """
    try:
        logger.info(
            "User %s recording learning event: type=%s, session=%s",
            current_user.id,
            request.event_type,
            request.session_id,
        )

        from src.core.ai.adaptive_learning_engine import LearningEventType

        learning_event = LearningEvent(
            event_id=f"event_{uuid.uuid4().hex[:8]}",
            event_type=(
                LearningEventType(request.event_type)
                if isinstance(request.event_type, str)
                else request.event_type
            ),
            timestamp=datetime.now(timezone.utc),
            context=request.context,
            metrics=cast(dict[str, float], request.metadata.get("metrics", {}))
            if request.metadata
            else {},
            user_id=request.user_id or str(current_user.id),
            session_id=request.session_id,
            confidence=request.confidence,
        )

        await engine.record_event(learning_event)

        return {
            "success": True,
            "message": "Learning event recorded successfully",
            "event_type": request.event_type,
            "recorded_by": current_user.id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.exception("Error recording learning event: %s: %s", type(e).__name__, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record event",
        ) from e


@router.get("/learning/insights", response_model=LearningInsightResponse)
@inject
async def get_learning_insights(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
    category: str | None = None,
    min_confidence: float = 0.7,
    limit: int = 50,
    offset: int = 0,
    engine: AdaptiveLearningEngine = Depends(Provide[Container.adaptive_learning_engine]),
) -> LearningInsightResponse:
    """
    Get insights from adaptive learning system.
    Requires: READ permission (USER level).
    """
    try:
        logger.info(
            "User %s requesting learning insights: category=%s, min_confidence=%s",
            current_user.id,
            category,
            min_confidence,
        )

        # Fetch limit+offset items, then slice -- engine heeft geen native offset-support
        all_insights = await engine.get_insights(
            category=category, min_confidence=min_confidence, limit=limit + offset
        )
        insights = all_insights[offset : offset + limit]

        return LearningInsightResponse(
            insights=[insight.to_dict() for insight in insights],
            summary={
                "total_insights": len(insights),
                "average_confidence": (
                    sum(i.confidence for i in insights) / len(insights) if insights else 0
                ),
                "categories": list({i.pattern_type for i in insights}),
            },
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    except Exception as e:
        logger.exception("Error getting learning insights: %s: %s", type(e).__name__, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get insights",
        ) from e
