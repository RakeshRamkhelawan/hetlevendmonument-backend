"""Smart Conflict Resolver.

Provides intelligent conflict resolution suggestions when scheduling
conflicts occur. Analyzes conflicts and proposes alternatives.
"""

import logging
from datetime import datetime, timedelta
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.scheduling.smart.models import (
    ConflictInfo,
    ResolutionOption,
    UserSchedulingProfile,
)
from src.core.scheduling.smart.predictor import AvailabilityPredictor

logger = logging.getLogger(__name__)


class ConflictResolver:
    """Resolves scheduling conflicts with intelligent suggestions."""

    def __init__(self, db_session: AsyncSession):
        """Initialize resolver.

        Args:
            db_session: Database session
        """
        self.db = db_session
        self.predictor = AvailabilityPredictor(db_session)

    async def resolve_conflicts(
        self,
        tenant_id: int,
        conflicts: list[ConflictInfo],
        original_start: datetime,
        original_end: datetime,
    ) -> list[ResolutionOption]:
        """Generate resolution options for conflicts.

        Args:
            tenant_id: Tenant ID
            conflicts: List of conflict information
            original_start: Original meeting start
            original_end: Original meeting end

        Returns:
            List of resolution options sorted by confidence
        """
        if not conflicts:
            return []

        resolutions = []
        duration = original_end - original_start

        # Strategy 1: Find adjacent slots
        adjacent = await self._find_adjacent_slots(
            tenant_id, conflicts, original_start, original_end, duration
        )
        resolutions.extend(adjacent)

        # Strategy 2: Alternative day, same time
        alternative_days = await self._find_alternative_days(
            tenant_id, conflicts, original_start, original_end, duration
        )
        resolutions.extend(alternative_days)

        # Strategy 3: Shorter duration
        shorter = await self._suggest_shorter_duration(
            tenant_id, conflicts, original_start, original_end
        )
        if shorter:
            resolutions.append(shorter)

        # Strategy 4: Virtual alternative
        virtual = self._suggest_virtual_alternative(conflicts, original_start, original_end)
        if virtual:
            resolutions.append(virtual)

        # Strategy 5: Async alternative
        async_option = self._suggest_async_alternative(conflicts, original_start, original_end)
        if async_option:
            resolutions.append(async_option)

        # Sort by confidence
        resolutions.sort(key=lambda x: x.confidence, reverse=True)

        return resolutions[:10]  # Return top 10

    async def _find_adjacent_slots(
        self,
        tenant_id: int,
        conflicts: list[ConflictInfo],
        original_start: datetime,
        original_end: datetime,
        duration: timedelta,
    ) -> list[ResolutionOption]:
        """Find slots immediately before or after conflicts.

        Args:
            tenant_id: Tenant ID
            conflicts: Conflicts to work around
            original_start: Original start
            original_end: Original end
            duration: Meeting duration

        Returns:
            List of adjacent slot options
        """
        resolutions = []
        conflicting_ids = [c.participant_id for c in conflicts]

        # Find earliest and latest conflicts
        sorted_conflicts = sorted(conflicts, key=lambda c: c.conflict_start)
        earliest_conflict = sorted_conflicts[0]
        latest_conflict = sorted_conflicts[-1]

        # Try before the earliest conflict
        before_start = earliest_conflict.conflict_start - duration
        before_end = earliest_conflict.conflict_start

        if before_start.hour >= 8:  # Business hours check
            resolutions.append(
                ResolutionOption(
                    type="adjacent",
                    description=(f"Schedule before '{earliest_conflict.conflicting_event_title}'"),
                    new_start=before_start,
                    new_end=before_end,
                    new_duration_minutes=int(duration.total_seconds() / 60),
                    confidence=0.8,
                    impacted_participants=conflicting_ids,
                    trade_offs=["Earlier than originally planned"],
                )
            )

        # Try after the latest conflict
        after_start = latest_conflict.conflict_end
        after_end = latest_conflict.conflict_end + duration

        if after_end.hour <= 18:  # Business hours check
            resolutions.append(
                ResolutionOption(
                    type="adjacent",
                    description=(f"Schedule after '{latest_conflict.conflicting_event_title}'"),
                    new_start=after_start,
                    new_end=after_end,
                    new_duration_minutes=int(duration.total_seconds() / 60),
                    confidence=0.8,
                    impacted_participants=conflicting_ids,
                    trade_offs=["Later than originally planned"],
                )
            )

        return resolutions

    async def _find_alternative_days(
        self,
        tenant_id: int,
        conflicts: list[ConflictInfo],
        original_start: datetime,
        original_end: datetime,
        duration: timedelta,
    ) -> list[ResolutionOption]:
        """Find same time on alternative days.

        Args:
            tenant_id: Tenant ID
            conflicts: Conflicts
            original_start: Original start
            original_end: Original end
            duration: Meeting duration

        Returns:
            List of alternative day options
        """
        resolutions = []
        original_time = original_start.time()

        # Try next 5 business days
        for day_offset in range(1, 6):
            new_start = original_start + timedelta(days=day_offset)
            new_end = original_end + timedelta(days=day_offset)

            # Skip weekends
            if new_start.weekday() >= 5:
                continue

            # Simple confidence: closer days = higher confidence
            confidence = max(0.4, 0.7 - (day_offset * 0.06))

            day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
            day_name = day_names[new_start.weekday()]

            resolutions.append(
                ResolutionOption(
                    type="alternative_day",
                    description=f"Same time on {day_name} ({new_start.strftime('%b %d')})",
                    new_start=new_start,
                    new_end=new_end,
                    new_duration_minutes=int(duration.total_seconds() / 60),
                    confidence=confidence,
                    impacted_participants=[],
                    trade_offs=[f"Rescheduled to {day_name}"],
                )
            )

        return resolutions

    async def _suggest_shorter_duration(
        self,
        tenant_id: int,
        conflicts: list[ConflictInfo],
        original_start: datetime,
        original_end: datetime,
    ) -> ResolutionOption | None:
        """Suggest a shorter meeting that fits in available window.

        Args:
            tenant_id: Tenant ID
            conflicts: Conflicts
            original_start: Original start
            original_end: Original end

        Returns:
            Resolution option or None
        """
        original_duration = (original_end - original_start).total_seconds() / 60

        # Find earliest conflict
        sorted_conflicts = sorted(conflicts, key=lambda c: c.conflict_start)
        earliest_conflict = sorted_conflicts[0]

        available_window = (earliest_conflict.conflict_start - original_start).total_seconds() / 60

        # Suggest shorter durations
        suggestions = [
            (30, "30 minutes"),
            (15, "15 minutes"),
        ]

        for new_duration, label in suggestions:
            if available_window >= new_duration and original_duration > new_duration:
                new_end = original_start + timedelta(minutes=new_duration)
                return ResolutionOption(
                    type="shorter",
                    description=f"Shorten to {label} to fit before conflict",
                    new_start=original_start,
                    new_end=new_end,
                    new_duration_minutes=new_duration,
                    confidence=0.6 if new_duration == 30 else 0.5,
                    impacted_participants=[],
                    trade_offs=[f"Reduced from {int(original_duration)} to {new_duration} minutes"],
                )

        return None

    def _suggest_virtual_alternative(
        self,
        conflicts: list[ConflictInfo],
        original_start: datetime,
        original_end: datetime,
    ) -> ResolutionOption | None:
        """Suggest switching to virtual meeting.

        Virtual meetings eliminate travel time and can sometimes
        be scheduled when physical meetings conflict.

        Args:
            conflicts: Conflicts
            original_start: Original start
            original_end: Original end

        Returns:
            Resolution option or None
        """
        duration = (original_end - original_start).total_seconds() / 60

        return ResolutionOption(
            type="virtual",
            description="Switch to virtual meeting to reduce travel conflicts and increase flexibility",
            new_start=original_start,
            new_end=original_end,
            new_duration_minutes=int(duration),
            confidence=0.5,
            impacted_participants=[],
            trade_offs=[
                "No travel time required",
                "Less personal interaction",
                "Requires video conferencing setup",
            ],
        )

    def _suggest_async_alternative(
        self,
        conflicts: list[ConflictInfo],
        original_start: datetime,
        original_end: datetime,
    ) -> ResolutionOption | None:
        """Suggest async communication instead of meeting.

        For informational meetings, async might be more efficient.

        Args:
            conflicts: Conflicts
            original_start: Original start
            original_end: Original end

        Returns:
            Resolution option or None
        """
        return ResolutionOption(
            type="async",
            description="Replace meeting with async communication (email, document, video recording)",
            new_start=None,
            new_end=None,
            new_duration_minutes=None,  # No duration for async
            confidence=0.4,
            impacted_participants=[c.participant_id for c in conflicts],
            trade_offs=[
                "No scheduling needed",
                "Participants review at their own pace",
                "No real-time discussion possible",
                "May take longer to reach consensus",
            ],
        )

    async def detect_conflicts(
        self,
        tenant_id: int,
        proposed_start: datetime,
        proposed_end: datetime,
        participants: list[str],
    ) -> list[ConflictInfo]:
        """Detect conflicts for proposed meeting time.

        Args:
            tenant_id: Tenant ID
            proposed_start: Proposed start
            proposed_end: Proposed end
            participants: Participant IDs

        Returns:
            List of conflicts
        """
        from src.core.scheduling.repository import CalendarEventRepository

        conflicts = []
        repo = CalendarEventRepository(self.db)

        for user_id in participants:
            try:
                # Get overlapping events
                events = await repo.list_by_user_in_range(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    start=proposed_start,
                    end=proposed_end,
                )

                for event in events:
                    # Determine conflict type
                    conflict_type = self._determine_conflict_type(event)

                    # Get participant info
                    participant_name = await self._get_participant_name(user_id)
                    participant_email = await self._get_participant_email(user_id, tenant_id=tenant_id)

                    conflicts.append(
                        ConflictInfo(
                            participant_id=user_id,
                            participant_name=participant_name,
                            participant_email=participant_email,
                            conflicting_event_title=getattr(event, "title", "Unknown"),
                            conflicting_event_id=str(getattr(event, "id", "")),
                            conflict_start=event.start_time,
                            conflict_end=event.end_time,
                            conflict_type=conflict_type,
                            is_recurring=getattr(event, "is_recurring", False),
                        )
                    )

            except Exception as e:
                logger.error(f"Error detecting conflicts for user {user_id}: {e}")
                continue

        return conflicts

    def _determine_conflict_type(self, event: Any) -> str:  # TODO(TYPE): replace Any with concrete type
        """Determine the type of conflict based on event properties.

        Args:
            event: Calendar event

        Returns:
            Conflict type: "hard", "soft", or "tentative"
        """
        # Check status
        status = getattr(event, "status", "busy")
        if status:
            status = str(status).lower()
            if status in ("tentative", "maybe"):
                return "tentative"
            if status in ("free", "transparent"):
                return "soft"

        # Check transparency
        transparency = getattr(event, "transparency", None)
        if transparency:
            if str(transparency).lower() in ("transparent", "free"):
                return "soft"

        # Check if event is blocking
        is_blocking = getattr(event, "is_blocking", True)
        if not is_blocking:
            return "soft"

        # Default to hard conflict
        return "hard"

    async def _get_participant_name(self, user_id: str) -> str | None:
        """Get participant display name.

        Args:
            user_id: User ID

        Returns:
            Display name or None
        """
        try:
            # Try to get from user profile
            result = await self.db.execute(
                select(UserSchedulingProfile).where(UserSchedulingProfile.user_id == user_id)
            )
            profile = result.scalar_one_or_none()
            if profile:
                return getattr(profile, "display_name", None)
        except Exception:
            pass
        return None

    async def _get_participant_email(
        self, user_id: str, tenant_id: int | None = None
    ) -> str | None:
        """Get participant email with tenant check.

        Args:
            user_id: User ID
            tenant_id: Optional Tenant ID for multi-tenant isolation

        Returns:
            Email or None
        """
        try:
            profile_query = select(UserSchedulingProfile).where(UserSchedulingProfile.user_id == user_id)
            if tenant_id is not None:
                profile_query = profile_query.where(UserSchedulingProfile.tenant_id == tenant_id)

            result = await self.db.execute(profile_query)
            profile = result.scalar_one_or_none()
            if profile and hasattr(profile, "email") and getattr(profile, "email", None):
                email_val = getattr(profile, "email")
                return str(email_val) if email_val is not None else None

            from src.core.models.rbac_models import User

            uid = int(user_id) if str(user_id).isdigit() else None
            if uid is not None:
                user_query = select(User).where(User.id == uid)
                if tenant_id is not None:
                    user_query = user_query.where(User.tenant_id == tenant_id)
                user_res = await self.db.execute(user_query)
                user = user_res.scalar_one_or_none()
                if user and hasattr(user, "email") and user.email:
                    return str(user.email)
        except Exception:
            pass
        return None

    def calculate_conflict_severity(self, conflicts: list[ConflictInfo]) -> str:
        """Calculate overall conflict severity.

        Args:
            conflicts: List of conflicts

        Returns:
            Severity level: "low", "medium", "high", "critical"
        """
        if not conflicts:
            return "low"

        hard_conflicts = sum(1 for c in conflicts if c.conflict_type == "hard")
        total = len(conflicts)
        recurring = sum(1 for c in conflicts if c.is_recurring)

        ratio = hard_conflicts / total if total > 0 else 0

        # Factor in recurring events (harder to reschedule)
        recurring_penalty = min(0.2, recurring * 0.05)
        adjusted_ratio = ratio + recurring_penalty

        if adjusted_ratio >= 0.8:
            return "critical"
        elif adjusted_ratio >= 0.5:
            return "high"
        elif adjusted_ratio >= 0.2:
            return "medium"

        return "low"

    async def suggest_best_alternative(
        self,
        tenant_id: int,
        original_start: datetime,
        original_end: datetime,
        participants: list[str],
    ) -> ResolutionOption | None:
        """Suggest the best alternative when conflicts exist.

        Args:
            tenant_id: Tenant ID
            original_start: Original start
            original_end: Original end
            participants: Participants

        Returns:
            Best resolution option or None
        """
        conflicts = await self.detect_conflicts(
            tenant_id, original_start, original_end, participants
        )

        if not conflicts:
            return None

        resolutions = await self.resolve_conflicts(
            tenant_id, conflicts, original_start, original_end
        )

        if resolutions:
            return resolutions[0]

        return None
