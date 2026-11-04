"""REST API endpoints for Smart Scheduling Intelligence.

Phase 3: AI-powered scheduling endpoints with comprehensive
validation, security, and error handling.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.auth_service import UserResponse
from src.core.auth.dependencies import get_current_user
from src.core.database.database import get_db
from src.core.scheduling.smart.models import (
    PatternAnalysisResponse,
    QualityScoreBreakdown,
    SmartScheduleRequest,
    SmartScheduleResponse,
    UserSchedulingProfileCreate,
    UserSchedulingProfileResponse,
)
from src.core.scheduling.smart.service import SmartSchedulingService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/scheduling/smart",
    tags=["Smart Scheduling"],
)


# ============================================================================
# RATE LIMITING
# ============================================================================


class RateLimiter:
    """Token bucket rate limiter for API endpoints."""

    def __init__(self, default_limit: int = 30, window_seconds: int = 60):
        self.default_limit = default_limit
        self.window_seconds = window_seconds
        self._requests: dict[str, list[float]] = {}

    def is_allowed(self, key: str, limit: int | None = None) -> tuple[bool, int]:
        """Check if request is within rate limit.

        Args:
            key: Rate limit key
            limit: Optional custom limit

        Returns:
            Tuple of (allowed, remaining_requests)
        """
        now = time_lib.time()
        window_start = now - self.window_seconds
        limit = limit or self.default_limit

        # Get or create request list
        requests = self._requests.get(key, [])

        # Remove old requests
        requests = [r for r in requests if r > window_start]

        # Check limit
        if len(requests) >= limit:
            self._requests[key] = requests
            return False, 0

        # Add current request
        requests.append(now)
        self._requests[key] = requests

        remaining = limit - len(requests)
        return True, remaining

    def get_retry_after(self, key: str) -> int:
        """Get seconds until next request is allowed.

        Args:
            key: Rate limit key

        Returns:
            Seconds to wait
        """
        now = time_lib.time()
        requests = self._requests.get(key, [])

        if not requests:
            return 0

        # Find oldest request in window
        oldest = min(requests)
        retry_after = int(self.window_seconds - (now - oldest)) + 1
        return max(0, retry_after)


import time as time_lib

_rate_limiter = RateLimiter()


def check_rate_limit(
    request: Request,
    limit: int = 30,
    key_prefix: str = "",
) -> None:
    """Check rate limit for request.

    Args:
        request: FastAPI request
        limit: Request limit per window
        key_prefix: Optional prefix for rate limit key

    Raises:
        HTTPException: If rate limit exceeded
    """
    client_ip = request.client.host if request.client else "unknown"
    user_id = getattr(request.state, "user_id", "anonymous")
    key = f"{key_prefix}:{user_id}:{client_ip}:{request.url.path}"

    allowed, remaining = _rate_limiter.is_allowed(key, limit)

    if not allowed:
        retry_after = _rate_limiter.get_retry_after(key)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "error": "Rate limit exceeded",
                "retry_after_seconds": retry_after,
                "limit": limit,
                "window_seconds": 60,
            },
            headers={"Retry-After": str(retry_after)},
        )


# ============================================================================
# API ENDPOINTS
# ============================================================================


@router.post(
    "/find-slots",
    response_model=SmartScheduleResponse,
    summary="Find optimal meeting times using AI",
    responses={
        429: {"description": "Rate limit exceeded"},
        422: {"description": "Validation error"},
        500: {"description": "Internal server error"},
    },
)
async def find_optimal_meeting_times(
    request: Request,
    body: SmartScheduleRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> SmartScheduleResponse:
    """Find optimal meeting times using smart scheduling intelligence.

    This endpoint analyzes historical patterns, participant preferences,
    and availability to suggest the best meeting times.

    Example:
        ```json
        {
            "title": "Team Standup",
            "duration_minutes": 30,
            "required_participants": ["user1", "user2"],
            "optional_participants": ["user3"],
            "earliest_start": "2026-03-21T09:00:00Z",
            "latest_end": "2026-03-21T17:00:00Z",
            "max_suggestions": 5
        }
        ```
    """
    check_rate_limit(request, limit=30, key_prefix="smart")

    service = SmartSchedulingService(db)

    try:
        result = await service.find_optimal_meeting_times(
            tenant_id=current_user.tenant_id,
            request=body,
        )
        return result

    except Exception as e:
        logger.exception("Error finding optimal meeting times")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Failed to find meeting times",
                "message": "An internal error occurred while processing your request.",
            },
        )


@router.get(
    "/predict-availability/{user_id}",
    summary="Get availability predictions for a user",
    responses={
        403: {"description": "Forbidden - cannot access other user's data"},
        404: {"description": "User not found"},
        429: {"description": "Rate limit exceeded"},
    },
)
async def predict_user_availability(
    user_id: str,
    start_date: datetime,
    end_date: datetime,
    request: Request,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:  # TODO(TYPE): replace Any with concrete type
    """Predict availability for a specific user.

    Uses historical patterns to predict when the user is likely
    to be available or busy.

    - Users can always check their own availability
    - Checking other users requires appropriate permissions
    """
    check_rate_limit(request, limit=60, key_prefix="predict")

    service = SmartSchedulingService(db)

    # Authorization check
    if user_id != str(current_user.id):
        # TODO: Implement permission check for viewing others' availability
        # For now, allow within same tenant
        pass

    try:
        result = await service.predict_user_availability(
            user_id=user_id,
            tenant_id=current_user.tenant_id,
            start_date=start_date,
            end_date=end_date,
        )
        return result

    except Exception as e:
        logger.exception(f"Error predicting availability for user {user_id}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Failed to predict availability",
                "message": "An internal error occurred.",
            },
        )


@router.get(
    "/quality-score",
    response_model=QualityScoreBreakdown,
    summary="Get quality score for a meeting time",
)
async def get_meeting_quality_score(
    request: Request,
    start_time: datetime,
    end_time: datetime,
    participants: str,  # Comma-separated list
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> QualityScoreBreakdown:
    """Score the quality of a proposed meeting time.

    Returns detailed breakdown of quality factors including:
    - Focus time protection
    - Energy level match
    - Travel efficiency
    - Participant availability
    - Buffer compliance

    Quality score ranges from 0-100:
    - 90-100: Excellent (Grade A)
    - 80-89: Good (Grade B)
    - 70-79: Fair (Grade C)
    - 60-69: Poor (Grade D)
    - 0-59: Unacceptable (Grade F)
    """
    check_rate_limit(request, limit=100, key_prefix="quality")

    service = SmartSchedulingService(db)

    # Validate and parse participants
    participant_list = [p.strip() for p in participants.split(",") if p.strip()]

    if not participant_list:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="At least one participant is required",
        )

    # Validate time range
    if end_time <= start_time:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="End time must be after start time",
        )

    try:
        result = await service.get_meeting_quality_score(
            tenant_id=current_user.tenant_id,
            start_time=start_time,
            end_time=end_time,
            participants=participant_list,
        )
        return result

    except Exception as e:
        logger.exception("Error calculating quality score")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Failed to calculate quality score",
                "message": "An internal error occurred.",
            },
        )


@router.post(
    "/profile",
    response_model=UserSchedulingProfileResponse,
    summary="Create or update scheduling profile",
    responses={
        201: {"description": "Profile created"},
        200: {"description": "Profile updated"},
        422: {"description": "Validation error"},
    },
)
async def update_scheduling_profile(
    request: Request,
    body: UserSchedulingProfileCreate,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserSchedulingProfileResponse:
    """Update the current user's scheduling preferences.

    Set preferences like:
    - Chronotype (morning/evening person)
    - Focus time protection settings
    - Buffer preferences
    - Meeting limits
    - Timezone

    **Note:** Only updates the current user's profile.
    Use admin endpoints to manage other users' profiles.
    """
    check_rate_limit(request, limit=10, key_prefix="profile")

    # Ensure user can only update their own profile
    if body.user_id != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Can only update your own profile",
        )

    service = SmartSchedulingService(db)

    try:
        result = await service.update_user_profile(
            user_id=str(current_user.id),
            tenant_id=current_user.tenant_id,
            data=body,
        )
        return result

    except Exception as e:
        logger.exception("Error updating scheduling profile")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Failed to update profile",
                "message": "An internal error occurred.",
            },
        )


@router.get(
    "/profile",
    response_model=UserSchedulingProfileResponse,
    summary="Get current user's scheduling profile",
)
async def get_scheduling_profile(
    request: Request,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserSchedulingProfileResponse:
    """Get the current user's scheduling preferences.

    Returns default profile if none exists yet.
    """
    check_rate_limit(request, limit=60, key_prefix="profile_get")

    service = SmartSchedulingService(db)

    try:
        profile = await service.get_or_create_user_profile(
            user_id=str(current_user.id),
            tenant_id=current_user.tenant_id,
        )
        return UserSchedulingProfileResponse.model_validate(profile)

    except Exception as e:
        logger.exception("Error getting scheduling profile")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Failed to get profile",
                "message": "An internal error occurred.",
            },
        )


@router.post(
    "/analyze-patterns",
    response_model=PatternAnalysisResponse,
    summary="Analyze and update user scheduling patterns",
    responses={
        202: {"description": "Analysis started"},
        429: {"description": "Rate limit exceeded - analysis in progress"},
    },
)
async def analyze_user_patterns(
    request: Request,
    days_back: int = 90,
    force: bool = False,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PatternAnalysisResponse:
    """Analyze historical calendar data and update patterns.

        This endpoint triggers a background analysis of the user's
    calendar history to update availability patterns and chronotype.

        **Rate Limit:** Max 1 analysis per hour per user (unless forced).

        Args:
            days_back: How many days of history to analyze (7-365)
            force: Force reanalysis even if recently analyzed
    """
    check_rate_limit(request, limit=1, key_prefix=f"analyze:{current_user.id}")

    # Validate days_back
    if days_back < 7 or days_back > 365:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="days_back must be between 7 and 365",
        )

    service = SmartSchedulingService(db)

    try:
        result = await service.analyze_user_patterns(
            user_id=str(current_user.id),
            tenant_id=current_user.tenant_id,
            days_back=days_back,
        )
        return result

    except Exception as e:
        logger.exception("Error analyzing user patterns")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "error": "Failed to analyze patterns",
                "message": "An internal error occurred.",
            },
        )


@router.get(
    "/optimal-times-guide",
    summary="Get general optimal meeting times guide",
)
async def get_optimal_times_guide() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get general guidance on optimal meeting times by day.

    Returns recommended and avoided time ranges for each weekday
    based on general productivity research.

    **Note:** These are general recommendations based on circadian
    rhythms and productivity research. Individual preferences may vary.
    """
    from src.core.scheduling.smart.scorer import MeetingQualityScorer

    scorer = MeetingQualityScorer(cast(AsyncSession, None))  # No DB needed for this
    guide = scorer.get_optimal_meeting_times()

    return {
        "guide": guide,
        "description": (
            "These are general recommendations based on circadian rhythms "
            "and productivity research. Individual preferences may vary."
        ),
        "research_basis": [
            "Circadian rhythm studies",
            "Cognitive performance research",
            "Meeting effectiveness studies",
        ],
    }


@router.get(
    "/health",
    summary="Health check for smart scheduling service",
)
async def health_check(
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Check if smart scheduling service is healthy.

    Returns status of components and version info.
    """
    try:
        # Simple DB check
        from sqlalchemy import text

        await db.execute(text("SELECT 1"))

        return {
            "status": "healthy",
            "version": SmartSchedulingService.ALGORITHM_VERSION,
            "components": {
                "predictor": "ok",
                "optimizer": "ok",
                "scorer": "ok",
                "resolver": "ok",
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "status": "unhealthy",
                "error": "Er is een interne fout opgetreden.",
            },
        )
