"""
API endpoints for gamification features.
Feature 5: User engagement through gamification.
"""

import logging

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from src.core.auth.api_deps import get_current_user
from src.core.models.rbac_models import User
from .dependencies import GamificationService, get_gamification_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/gamification", tags=["gamification"])


class BadgeResponse(BaseModel):
    code: str
    name: str
    description: str | None
    icon: str | None
    color: str | None = "#3B82F6"


class UserProfileResponse(BaseModel):
    total_points: int
    level: int
    level_progress: float
    points_to_next_level: int
    current_streak: int
    longest_streak: int
    badges: list[BadgeResponse]


class LeaderboardEntry(BaseModel):
    user_id: int
    total_points: int
    level: int
    streak: int


class AwardPointsRequest(BaseModel):
    action: str
    description: str | None = None


class AwardPointsResponse(BaseModel):
    points_awarded: int
    total_points: int
    level: int
    streak: int
    leveled_up: bool


@router.get("/profile", response_model=UserProfileResponse)
async def get_my_profile(
    current_user: User = Depends(get_current_user),
    service: GamificationService = Depends(get_gamification_service),
) -> UserProfileResponse:
    """Get the current user's gamification profile."""
    profile = await service.get_user_profile(current_user.id, current_user.tenant_id)
    return UserProfileResponse(**profile)


@router.get("/leaderboard", response_model=list[LeaderboardEntry])
async def get_leaderboard(
    limit: int = Query(default=50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    service: GamificationService = Depends(get_gamification_service),
) -> list[LeaderboardEntry]:
    """Get the top users leaderboard for the current tenant."""
    entries = await service.get_leaderboard(current_user.tenant_id, limit)
    return [LeaderboardEntry(**e) for e in entries]


@router.post("/award", response_model=AwardPointsResponse)
async def award_points(
    request: AwardPointsRequest,
    current_user: User = Depends(get_current_user),
    service: GamificationService = Depends(get_gamification_service),
) -> AwardPointsResponse:
    """Award points to the current user for an action."""
    result = await service.award_points(
        user_id=current_user.id,
        tenant_id=current_user.tenant_id,
        action=request.action,
        description=request.description,
    )
    await service.check_and_award_badges(current_user.id, current_user.tenant_id)
    return AwardPointsResponse(**result)


@router.post("/check-badges", response_model=list[BadgeResponse])
async def check_badges(
    current_user: User = Depends(get_current_user),
    service: GamificationService = Depends(get_gamification_service),
) -> list[BadgeResponse]:
    """Check and award any new badges the user qualifies for."""
    new_badges = await service.check_and_award_badges(current_user.id, current_user.tenant_id)
    return [
        BadgeResponse(
            code=b.code,
            name=b.name,
            description=b.description,
            icon=b.icon,
            color=b.color,
        )
        for b in new_badges
    ]
