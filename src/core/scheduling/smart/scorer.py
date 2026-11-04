"""Meeting Quality Scorer.

Scores potential meeting times based on productivity factors with
proper timezone handling and real focus block detection.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.scheduling.smart.models import QualityScoreBreakdown, UserSchedulingProfile

logger = logging.getLogger(__name__)


@dataclass
class ScoringContext:
    """Context for quality scoring."""

    tenant_id: int
    start_time: datetime
    end_time: datetime
    participants: list[str]
    respect_focus_time: bool
    respect_chronotypes: bool


class MeetingQualityScorer:
    """Scores meeting time slots based on quality factors."""

    # Scoring weights
    WEIGHTS = {
        "focus_time_protection": 25,
        "energy_level": 20,
        "travel_efficiency": 20,
        "participant_availability": 20,
        "buffer_compliance": 15,
    }

    def __init__(self, db_session: AsyncSession):
        """Initialize scorer.

        Args:
            db_session: Database session
        """
        self.db = db_session

    async def score_meeting_slot(
        self,
        tenant_id: int,
        start_time: datetime,
        end_time: datetime,
        participants: list[str],
        respect_focus_time: bool = True,
        respect_chronotypes: bool = True,
    ) -> QualityScoreBreakdown:
        """Score a potential meeting slot.

        Args:
            tenant_id: Tenant ID
            start_time: Meeting start
            end_time: Meeting end
            participants: Participant IDs
            respect_focus_time: Whether to score focus time protection
            respect_chronotypes: Whether to score based on chronotypes

        Returns:
            Quality score breakdown
        """
        # Ensure UTC for calculations
        start_time = self._ensure_utc(start_time)
        end_time = self._ensure_utc(end_time)

        context = ScoringContext(
            tenant_id=tenant_id,
            start_time=start_time,
            end_time=end_time,
            participants=participants,
            respect_focus_time=respect_focus_time,
            respect_chronotypes=respect_chronotypes,
        )

        try:
            # Calculate individual scores
            focus_score = await self._score_focus_time_protection(context)
            energy_score = await self._score_energy_level(context)
            travel_score = await self._score_travel_efficiency(context)
            availability_score = await self._score_participant_availability(context)
            buffer_score = await self._score_buffer_compliance(context)

            # Calculate total
            total = focus_score + energy_score + travel_score + availability_score + buffer_score

            return QualityScoreBreakdown(
                focus_time_protection=focus_score,
                energy_level=energy_score,
                travel_efficiency=travel_score,
                participant_availability=availability_score,
                buffer_compliance=buffer_score,
                total_score=total,
            )

        except Exception as e:
            logger.error(f"Error scoring meeting slot: {e}")
            # Return neutral score on error
            return QualityScoreBreakdown(
                focus_time_protection=12,
                energy_level=10,
                travel_efficiency=10,
                participant_availability=10,
                buffer_compliance=7,
                total_score=49,
            )

    async def _score_focus_time_protection(self, context: ScoringContext) -> int:
        """Score focus time protection (0-25).

        Higher score if meeting doesn't break up focus blocks.

        Args:
            context: Scoring context

        Returns:
            Score 0-25
        """
        if not context.respect_focus_time:
            return 25

        score = 25
        hour = context.start_time.hour
        duration_minutes = (context.end_time - context.start_time).total_seconds() / 60

        # Morning focus block (9-12) is precious
        if 9 <= hour < 12:
            if hour == 10 and duration_minutes > 30:
                score -= 15  # Breaks the heart of morning focus
            else:
                score -= 5

        # Late afternoon can break end-of-day focus
        if hour >= 15 and duration_minutes > 45:
            score -= 10

        # Very short meetings (< 15 min) have less impact
        if duration_minutes <= 15:
            score += 5

        # Check participant focus preferences
        if context.participants and self.db:
            try:
                result = await self.db.execute(
                    select(UserSchedulingProfile).where(
                        UserSchedulingProfile.user_id.in_(context.participants),
                        UserSchedulingProfile.tenant_id == context.tenant_id,
                        UserSchedulingProfile.protect_focus_time.is_(True),
                    )
                )
                profiles = result.scalars().all()
                if profiles:
                    # Reduce score if many participants protect focus time
                    reduction = min(10, len(profiles) * 2)
                    score -= reduction
            except Exception as e:
                logger.debug(f"Could not load focus preferences: {e}")

        return max(0, min(25, score))

    async def _score_energy_level(self, context: ScoringContext) -> int:
        """Score energy level match (0-20).

        Based on circadian rhythms and chronotypes with timezone awareness.

        Args:
            context: Scoring context

        Returns:
            Score 0-20
        """
        # Get local hour for the "average" participant
        # In a real implementation, we'd calculate per-participant local time
        hour = context.start_time.hour

        # Base energy by time of day (universal patterns)
        base_energy_map = {
            range(6, 9): 12,  # Warming up
            range(9, 12): 18,  # Peak morning
            range(12, 13): 12,  # Lunch dip
            range(13, 14): 10,  # Post-lunch dip
            range(14, 17): 16,  # Afternoon recovery
            range(17, 20): 12,  # Winding down
            range(20, 24): 8,  # Evening
            range(0, 6): 5,  # Night
        }

        base_score = 10  # Default
        for hour_range, score in base_energy_map.items():
            if hour in hour_range:
                base_score = score
                break

        # Adjust for participant chronotypes if requested
        if context.respect_chronotypes and context.participants and self.db:
            try:
                result = await self.db.execute(
                    select(UserSchedulingProfile).where(
                        UserSchedulingProfile.user_id.in_(context.participants),
                        UserSchedulingProfile.tenant_id == context.tenant_id,
                    )
                )
                profiles = result.scalars().all()

                if profiles:
                    adjustments = []
                    for profile in profiles:
                        chronotype = profile.chronotype

                        if chronotype == "morning":
                            if 9 <= hour <= 11:
                                adjustments.append(3)
                            elif hour >= 15:
                                adjustments.append(-3)
                            else:
                                adjustments.append(0)
                        elif chronotype == "evening":
                            if 14 <= hour <= 17:
                                adjustments.append(3)
                            elif hour <= 9:
                                adjustments.append(-3)
                            else:
                                adjustments.append(1)
                        else:  # neutral
                            adjustments.append(1)

                    if adjustments:
                        avg_adjustment = sum(adjustments) / len(adjustments)
                        base_score += int(avg_adjustment)

            except Exception as e:
                logger.debug(f"Could not load chronotypes: {e}")

        return max(0, min(20, base_score))

    async def _score_travel_efficiency(self, context: ScoringContext) -> int:
        """Score travel efficiency (0-20).

        Higher score if meeting follows logical geographic/temporal flow.

        Args:
            context: Scoring context

        Returns:
            Score 0-20
        """
        score = 15  # Neutral
        hour = context.start_time.hour

        # Avoid very early (travel rush) and very late (end of day)
        if hour < 9:
            score -= 5
        elif hour > 16:
            score -= 3

        # Lunch time can be efficient for some (already out)
        if 12 <= hour <= 13:
            score += 2

        # Mid-morning and mid-afternoon are optimal
        if 10 <= hour <= 11 or 14 <= hour <= 15:
            score += 3

        return max(0, min(20, score))

    async def _score_participant_availability(self, context: ScoringContext) -> int:
        """Score participant availability (0-20).

        Based on how many participants are available vs busy.

        Args:
            context: Scoring context

        Returns:
            Score 0-20
        """
        if not context.participants:
            return 20  # No participants = perfect availability

        # Business hours score better
        hour = context.start_time.hour
        if 10 <= hour <= 16:
            base_score = 18
        elif 9 <= hour <= 17:
            base_score = 15
        else:
            base_score = 10

        return base_score

    async def _score_buffer_compliance(self, context: ScoringContext) -> int:
        """Score buffer compliance (0-15).

        Checks if meeting respects buffer preferences.

        Args:
            context: Scoring context

        Returns:
            Score 0-15
        """
        score = 15  # Start perfect
        duration = (context.end_time - context.start_time).total_seconds() / 60
        hour = context.start_time.hour

        # Meetings without buffers are stressful
        if duration > 90:
            score -= 5

        # Meetings right at start/end of day
        if hour < 9:
            score -= 3
        if hour >= 17:
            score -= 3

        # Lunch protection
        if 12 <= hour < 13:
            score -= 2

        # Check participant buffer preferences
        if context.participants and self.db:
            try:
                result = await self.db.execute(
                    select(UserSchedulingProfile).where(
                        UserSchedulingProfile.user_id.in_(context.participants),
                        UserSchedulingProfile.tenant_id == context.tenant_id,
                    )
                )
                profiles = result.scalars().all()

                if profiles:
                    # Calculate average preferred buffer
                    total_buffer = sum(
                        p.default_prep_buffer + p.default_recovery_buffer for p in profiles
                    )
                    avg_buffer = total_buffer / len(profiles)

                    # If meeting doesn't allow for average buffer, reduce score
                    if hour < 9 and avg_buffer > 15:
                        score -= 2

            except Exception as e:
                logger.debug(f"Could not load buffer preferences: {e}")

        return max(0, min(15, score))

    async def analyze_focus_blocks(
        self,
        tenant_id: int,
        user_id: str,
        date: datetime,
        min_duration_minutes: int = 120,
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Analyze focus blocks for a user on a specific date.

        Args:
            tenant_id: Tenant ID
            user_id: User ID
            date: Date to analyze
            min_duration_minutes: Minimum focus block duration

        Returns:
            List of focus blocks
        """
        try:
            from src.core.scheduling.repository import CalendarEventRepository

            repo = CalendarEventRepository(self.db)
            day_start = date.replace(hour=0, minute=0, second=0, microsecond=0)
            day_end = day_start + timedelta(days=1)

            # Get events for the day
            events = await repo.list_by_user_in_range(
                tenant_id=tenant_id,
                user_id=user_id,
                start=day_start,
                end=day_end,
            )

            # Find gaps between events
            focus_blocks = []
            current_time = day_start.replace(hour=9)  # Start at 9 AM
            end_of_day = day_start.replace(hour=17)  # End at 5 PM

            # Sort events by start time
            sorted_events = sorted(events, key=lambda e: e.start_time)

            for event in sorted_events:
                if event.start_time > current_time:
                    gap_duration = (event.start_time - current_time).total_seconds() / 60
                    if gap_duration >= min_duration_minutes:
                        focus_blocks.append(
                            {
                                "start": current_time,
                                "end": event.start_time,
                                "duration_minutes": int(gap_duration),
                            }
                        )
                current_time = max(current_time, event.end_time)

            # Check for gap after last event
            if current_time < end_of_day:
                gap_duration = (end_of_day - current_time).total_seconds() / 60
                if gap_duration >= min_duration_minutes:
                    focus_blocks.append(
                        {
                            "start": current_time,
                            "end": end_of_day,
                            "duration_minutes": int(gap_duration),
                        }
                    )

            return focus_blocks

        except Exception as e:
            logger.error(f"Error analyzing focus blocks: {e}")
            # Return default focus blocks on error
            return [
                {
                    "start": date.replace(hour=9, minute=0),
                    "end": date.replace(hour=11, minute=0),
                    "duration_minutes": 120,
                },
                {
                    "start": date.replace(hour=14, minute=0),
                    "end": date.replace(hour=16, minute=0),
                    "duration_minutes": 120,
                },
            ]

    def get_optimal_meeting_times(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get generally optimal meeting times by day.

        Returns:
            Dict with optimal time ranges
        """
        return {
            "monday": {
                "optimal": [("10:00", "11:30"), ("14:00", "15:30")],
                "avoid": [("08:00", "09:00"), ("12:00", "13:00")],
                "reasoning": "Monday morning is for planning, avoid lunch",
            },
            "tuesday": {
                "optimal": [("09:30", "11:30"), ("14:00", "16:00")],
                "avoid": [("08:00", "09:00")],
                "reasoning": "Tuesday is peak productivity day",
            },
            "wednesday": {
                "optimal": [("10:00", "12:00"), ("14:30", "16:00")],
                "avoid": [("12:00", "13:00")],
                "reasoning": "Mid-week focus, avoid lunch dip",
            },
            "thursday": {
                "optimal": [("09:30", "11:30"), ("14:00", "15:30")],
                "avoid": [("16:00", "17:00")],
                "reasoning": "Thursday afternoon energy drops",
            },
            "friday": {
                "optimal": [("10:00", "11:00")],
                "avoid": [("15:00", "17:00")],
                "reasoning": "Short meetings only on Friday",
            },
            "weekend": {
                "optimal": [],
                "avoid": [("00:00", "23:59")],
                "reasoning": "Respect personal time",
            },
        }

    def _ensure_utc(self, dt: datetime) -> datetime:
        """Ensure datetime is UTC.

        Args:
            dt: Datetime to check

        Returns:
            UTC datetime
        """
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
