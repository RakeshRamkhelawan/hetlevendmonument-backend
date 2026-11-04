"""
Gamification Service - Award points and badges.
Feature 5: User engagement through gamification.
"""

import logging
from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.gamification_models import Badge, PointTransaction, UserBadge, UserPoints

logger = logging.getLogger(__name__)


# Point values for different actions
POINT_VALUES = {
    "workflow_created": 10,
    "workflow_completed": 25,
    "tool_used": 5,
    "daily_login": 15,
    "streak_bonus": 10,  # Per day of streak
    "badge_earned": 50,
    "collaboration_session": 20,
    "first_workflow": 100,  # One-time bonus
}

# Level thresholds
LEVEL_THRESHOLDS = [
    0,  # Level 1
    100,  # Level 2
    300,  # Level 3
    600,  # Level 4
    1000,  # Level 5
    1500,  # Level 6
    2500,  # Level 7
    4000,  # Level 8
    6000,  # Level 9
    10000,  # Level 10
]


def calculate_level(total_points: int) -> int:
    """Calculate user level based on total points."""
    level = 1
    for i, threshold in enumerate(LEVEL_THRESHOLDS):
        if total_points >= threshold:
            level = i + 1
    return min(level, len(LEVEL_THRESHOLDS))


class GamificationService:
    """Service for managing user gamification."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_or_create_user_points(self, user_id: int, tenant_id: int) -> UserPoints:
        """Get or create UserPoints record for a user."""
        result = await self.session.execute(
            select(UserPoints).where(
                UserPoints.user_id == user_id, UserPoints.tenant_id == tenant_id
            )
        )
        user_points = result.scalar_one_or_none()

        if not user_points:
            user_points = UserPoints(user_id=user_id, tenant_id=tenant_id, total_points=0, level=1)
            self.session.add(user_points)
            await self.session.flush()

        return user_points

    async def award_points(
        self,
        user_id: int,
        tenant_id: int,
        action: str,
        description: str | None = None,
        custom_points: int | None = None,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Award points to a user for an action.

        Returns dict with new totals and any level up info.
        """
        points = custom_points if custom_points is not None else POINT_VALUES.get(action, 0)

        if points == 0:
            logger.warning(f"Unknown action for points: {action}")
            return {"points_awarded": 0}

        user_points = await self.get_or_create_user_points(user_id, tenant_id)
        old_level = user_points.level

        # Update points
        user_points.total_points += points
        user_points.level = calculate_level(user_points.total_points)

        # Check streak
        today = date.today()
        if user_points.last_activity_date:
            last_date = user_points.last_activity_date.date()
            days_diff = (today - last_date).days

            if days_diff == 1:
                # Consecutive day - increase streak
                user_points.current_streak += 1
                if user_points.current_streak > user_points.longest_streak:
                    user_points.longest_streak = user_points.current_streak

                # Award streak bonus
                streak_bonus = POINT_VALUES["streak_bonus"] * min(user_points.current_streak, 7)
                user_points.total_points += streak_bonus
                points += streak_bonus

            elif days_diff > 1:
                # Streak broken
                user_points.current_streak = 1
        else:
            user_points.current_streak = 1

        user_points.last_activity_date = datetime.now(timezone.utc)

        # Record transaction
        transaction = PointTransaction(
            user_id=user_id,
            tenant_id=tenant_id,
            points=points,
            action=action,
            description=description,
        )
        self.session.add(transaction)

        await self.session.commit()

        result = {
            "points_awarded": points,
            "total_points": user_points.total_points,
            "level": user_points.level,
            "streak": user_points.current_streak,
            "leveled_up": user_points.level > old_level,
        }

        logger.info(f"Awarded {points} points to user {user_id} for {action}")

        return result

    async def check_and_award_badges(self, user_id: int, tenant_id: int) -> list[Badge]:
        """
        Check if user qualifies for any new badges.
        Returns list of newly earned badges.
        """
        user_points = await self.get_or_create_user_points(user_id, tenant_id)

        # Get all badges for tenant
        result = await self.session.execute(select(Badge).where(Badge.tenant_id == tenant_id))
        all_badges = result.scalars().all()

        # Get already earned badges
        result = await self.session.execute(
            select(UserBadge.badge_id).where(
                UserBadge.user_id == user_id, UserBadge.tenant_id == tenant_id
            )
        )
        earned_badge_ids = {r[0] for r in result.all()}

        newly_earned: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for badge in all_badges:
            if badge.id in earned_badge_ids:
                continue

            # Check if user qualifies
            if user_points.total_points >= (badge.points_required or 0):
                # Award badge
                user_badge = UserBadge(user_id=user_id, badge_id=badge.id, tenant_id=tenant_id)
                self.session.add(user_badge)
                newly_earned.append(badge)

                # Award bonus points for badge
                await self.award_points(
                    user_id, tenant_id, "badge_earned", f"Earned badge: {badge.name}"
                )

        if newly_earned:
            await self.session.commit()
            logger.info(f"User {user_id} earned {len(newly_earned)} new badges")

        return newly_earned

    async def get_user_profile(self, user_id: int, tenant_id: int) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get complete gamification profile for a user."""
        user_points = await self.get_or_create_user_points(user_id, tenant_id)

        # Get earned badges
        result = await self.session.execute(
            select(Badge)
            .join(UserBadge)
            .where(UserBadge.user_id == user_id, UserBadge.tenant_id == tenant_id)
        )
        badges = result.scalars().all()

        # Calculate progress to next level
        current_level = user_points.level
        next_threshold = (
            LEVEL_THRESHOLDS[current_level]
            if current_level < len(LEVEL_THRESHOLDS)
            else LEVEL_THRESHOLDS[-1]
        )
        prev_threshold = LEVEL_THRESHOLDS[current_level - 1] if current_level > 1 else 0

        progress = (
            (user_points.total_points - prev_threshold) / (next_threshold - prev_threshold)
            if next_threshold > prev_threshold
            else 1.0
        )

        return {
            "total_points": user_points.total_points,
            "level": user_points.level,
            "level_progress": round(progress, 2),
            "points_to_next_level": max(0, next_threshold - user_points.total_points),
            "current_streak": user_points.current_streak,
            "longest_streak": user_points.longest_streak,
            "badges": [
                {
                    "code": b.code,
                    "name": b.name,
                    "description": b.description,
                    "icon": b.icon,
                    "color": b.color,
                }
                for b in badges
            ],
        }

    async def get_leaderboard(self, tenant_id: int, limit: int = 10) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get top users by points for a tenant."""
        result = await self.session.execute(
            select(UserPoints)
            .where(UserPoints.tenant_id == tenant_id)
            .order_by(UserPoints.total_points.desc())
            .limit(limit)
        )
        entries = result.scalars().all()

        return [
            {
                "user_id": e.user_id,
                "total_points": e.total_points,
                "level": e.level,
                "streak": e.current_streak,
            }
            for e in entries
        ]
