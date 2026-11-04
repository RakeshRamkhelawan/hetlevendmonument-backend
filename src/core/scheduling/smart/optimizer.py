"""Multi-Participant Optimizer.

Finds optimal meeting times for multiple participants using
overlap detection and scoring algorithms with caching and
configurable parameters.
"""

import asyncio
import logging
import time as time_lib
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.scheduling.smart.models import (
    AvailabilityPrediction,
    BufferConfig,
    SmartScheduleOption,
    SmartScheduleRequest,
    TimeRange,
)
from src.core.scheduling.smart.predictor import AvailabilityPredictor
from src.core.scheduling.smart.scorer import MeetingQualityScorer

logger = logging.getLogger(__name__)


@dataclass
class OptimizationConfig:
    """Configuration for optimization algorithm."""

    slot_increment_minutes: int = 30
    availability_threshold: float = 0.7
    high_availability_threshold: float = 0.8
    tentative_threshold: float = 0.5
    max_candidate_slots: int = 1000
    early_morning_hour: int = 8
    late_evening_hour: int = 18
    cache_ttl_seconds: int = 300


@dataclass
class OptimizationContext:
    """Context passed through optimization pipeline."""

    tenant_id: int
    request: SmartScheduleRequest
    config: OptimizationConfig = field(default_factory=OptimizationConfig)
    participant_profiles: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    performance_metrics: dict[str, float] = field(default_factory=dict)


class MultiParticipantOptimizer:
    """Optimizes meeting times for multiple participants."""

    def __init__(
        self,
        db_session: AsyncSession,
        config: OptimizationConfig | None = None,
    ):
        """Initialize optimizer.

        Args:
            db_session: Database session
            config: Optional optimization configuration
        """
        self.db = db_session
        self.config = config or OptimizationConfig()
        self.predictor = AvailabilityPredictor(db_session)
        self.scorer = MeetingQualityScorer(db_session)
        self._profile_cache: dict[str, tuple[Any, datetime]] = {}  # TODO(TYPE): replace Any with concrete type

    async def find_optimal_slots(
        self,
        tenant_id: int,
        request: SmartScheduleRequest,
    ) -> tuple[list[SmartScheduleOption], int]:
        """Find optimal meeting slots for all participants.

        Args:
            tenant_id: Tenant ID
            request: Scheduling request

        Returns:
            Tuple of (options list, total considered count)
        """
        start_time = time_lib.time()
        context = OptimizationContext(
            tenant_id=tenant_id,
            request=request,
            config=self.config,
        )

        try:
            # Step 1: Pre-load participant profiles (with caching)
            context.participant_profiles = await self._load_participant_profiles(
                tenant_id,
                request.required_participants + request.optional_participants,
            )

            # Step 2: Get availability for all participants
            participant_availability = await self._get_participant_availability(tenant_id, request)

            # Step 3: Find overlapping slots
            candidate_slots = self._find_overlapping_slots(
                participant_availability,
                request,
            )

            total_considered = len(candidate_slots)

            # Limit candidates to prevent performance issues
            if len(candidate_slots) > self.config.max_candidate_slots:
                logger.warning(
                    f"Limiting candidates from {len(candidate_slots)} to "
                    f"{self.config.max_candidate_slots}"
                )
                candidate_slots = candidate_slots[: self.config.max_candidate_slots]

            # Step 4: Score candidates in parallel
            scored_options = await self._score_candidates_parallel(
                tenant_id,
                candidate_slots,
                request,
                participant_availability,
            )

            # Step 5: Sort and filter
            scored_options.sort(key=lambda x: x.quality_score, reverse=True)

            filtered_options = [
                opt for opt in scored_options if opt.quality_score >= request.min_quality_score
            ]

            # Limit results
            final_options = filtered_options[: request.max_suggestions]

            generation_time = int((time_lib.time() - start_time) * 1000)
            context.performance_metrics["generation_time_ms"] = generation_time

            logger.info(
                f"Found {len(final_options)} optimal slots from "
                f"{total_considered} candidates in {generation_time}ms"
            )

            return final_options, total_considered

        except Exception as e:
            logger.exception(f"Error finding optimal slots: {e}")
            raise

    async def _load_participant_profiles(
        self,
        tenant_id: int,
        user_ids: list[str],
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Load participant profiles with caching.

        Args:
            tenant_id: Tenant ID
            user_ids: List of user IDs

        Returns:
            Dict mapping user_id to profile
        """
        from sqlalchemy import select

        from src.core.scheduling.smart.models import UserSchedulingProfile

        profiles = {}
        uncached_users = []

        # Check cache first
        now = datetime.now(timezone.utc)
        for user_id in user_ids:
            cache_key = f"{tenant_id}:{user_id}"
            if cache_key in self._profile_cache:
                profile, cached_at = self._profile_cache[cache_key]
                if (now - cached_at).total_seconds() < self.config.cache_ttl_seconds:
                    profiles[user_id] = profile
                    continue
            uncached_users.append(user_id)

        # Load uncached profiles
        if uncached_users:
            try:
                result = await self.db.execute(
                    select(UserSchedulingProfile).where(
                        UserSchedulingProfile.user_id.in_(uncached_users),
                        UserSchedulingProfile.tenant_id == tenant_id,
                    )
                )
                loaded_profiles = result.scalars().all()

                for profile in loaded_profiles:
                    profiles[profile.user_id] = profile
                    cache_key = f"{tenant_id}:{profile.user_id}"
                    self._profile_cache[cache_key] = (profile, now)

            except Exception as e:
                logger.error(f"Error loading profiles: {e}")

        return profiles

    async def _get_participant_availability(
        self,
        tenant_id: int,
        request: SmartScheduleRequest,
    ) -> dict[str, list[AvailabilityPrediction]]:
        """Get availability predictions for all participants.

        Args:
            tenant_id: Tenant ID
            request: Scheduling request

        Returns:
            Dict mapping user_id to availability predictions
        """
        all_participants = list(set(request.required_participants + request.optional_participants))

        # Fetch availability in parallel
        async def fetch_user_availability(
            user_id: str,
        ) -> tuple[str, list[AvailabilityPrediction]]:
            try:
                predictions = await self.predictor.predict_availability(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    start_date=request.earliest_start,
                    end_date=request.latest_end,
                    granularity_minutes=self.config.slot_increment_minutes,
                )
                return user_id, predictions
            except Exception as e:
                logger.error(f"Error fetching availability for {user_id}: {e}")
                return user_id, []

        # Execute all fetches concurrently
        results = await asyncio.gather(
            *[fetch_user_availability(uid) for uid in all_participants],
            return_exceptions=True,
        )

        availability = {}
        for result in results:
            if isinstance(result, BaseException):
                logger.error(f"Exception in availability fetch: {result}")
                continue
            user_id, predictions = result
            availability[user_id] = predictions

        return availability

    def _find_overlapping_slots(
        self,
        participant_availability: dict[str, list[AvailabilityPrediction]],
        request: SmartScheduleRequest,
    ) -> list[tuple[datetime, datetime]]:
        """Find time slots where required participants are available.

        Args:
            participant_availability: Availability per participant
            request: Scheduling request

        Returns:
            List of (start, end) tuples
        """
        candidates = []
        duration = timedelta(minutes=request.duration_minutes)
        increment = timedelta(minutes=self.config.slot_increment_minutes)

        # Generate time slots
        current = request.earliest_start
        max_iterations = 10000  # Safety limit
        iterations = 0

        while current + duration <= request.latest_end and iterations < max_iterations:
            iterations += 1
            slot_end = current + duration

            # Skip excluded dates
            if self._is_excluded_date(current, request.excluded_dates):
                current += increment
                continue

            # Skip early morning if requested
            if request.avoid_early_morning and current.hour < self.config.early_morning_hour:
                current += increment
                continue

            # Skip late evening if requested
            if request.avoid_late_evening and current.hour >= self.config.late_evening_hour:
                current += increment
                continue

            # Check if slot works for minimum required participants
            if self._slot_meets_requirements(current, slot_end, participant_availability, request):
                # Check preferred time ranges if specified
                if self._is_in_preferred_range(current, request.preferred_time_ranges):
                    candidates.append((current, slot_end))

            current += increment

        if iterations >= max_iterations:
            logger.warning("Max iterations reached in slot generation")

        return candidates

    def _is_excluded_date(
        self,
        dt: datetime,
        excluded_dates: list[datetime],
    ) -> bool:
        """Check if date is in excluded list.

        Args:
            dt: Datetime to check
            excluded_dates: List of excluded dates

        Returns:
            True if excluded
        """
        if not excluded_dates:
            return False

        check_date = dt.date()
        for excluded in excluded_dates:
            if excluded.date() == check_date:
                return True
        return False

    def _slot_meets_requirements(
        self,
        slot_start: datetime,
        slot_end: datetime,
        availability: dict[str, list[AvailabilityPrediction]],
        request: SmartScheduleRequest,
    ) -> bool:
        """Check if slot meets minimum participant requirements.

        Args:
            slot_start: Slot start time
            slot_end: Slot end time
            availability: Participant availability
            request: Scheduling request

        Returns:
            True if slot meets requirements
        """
        available_required = 0

        for user_id in request.required_participants:
            if user_id not in availability:
                return False

            if self._is_user_available(slot_start, slot_end, availability[user_id]):
                available_required += 1

        min_required = request.min_required_attendance
        if min_required == 0:
            min_required = len(request.required_participants)

        return available_required >= min_required

    def _is_user_available(
        self,
        slot_start: datetime,
        slot_end: datetime,
        predictions: list[AvailabilityPrediction],
    ) -> bool:
        """Check if user is available for entire slot.

        Args:
            slot_start: Slot start
            slot_end: Slot end
            predictions: User's availability predictions

        Returns:
            True if available
        """
        for pred in predictions:
            if pred.start_time < slot_end and pred.end_time > slot_start:
                if pred.availability_score < self.config.availability_threshold:
                    return False
        return True

    def _is_in_preferred_range(
        self,
        slot_start: datetime,
        preferred_ranges: list[TimeRange],
    ) -> bool:
        """Check if slot is within preferred time ranges.

        Args:
            slot_start: Slot start time
            preferred_ranges: List of preferred time ranges

        Returns:
            True if in preferred range or no preferences specified
        """
        if not preferred_ranges:
            return True

        slot_time = slot_start.time()

        for range_ in preferred_ranges:
            if range_.start <= slot_time <= range_.end:
                return True

        return False

    async def _score_candidates_parallel(
        self,
        tenant_id: int,
        candidate_slots: list[tuple[datetime, datetime]],
        request: SmartScheduleRequest,
        participant_availability: dict[str, list[AvailabilityPrediction]],
    ) -> list[SmartScheduleOption]:
        """Score candidate slots with controlled concurrency.

        Args:
            tenant_id: Tenant ID
            candidate_slots: List of candidate slots
            request: Scheduling request
            participant_availability: Availability predictions

        Returns:
            List of scored options
        """
        semaphore = asyncio.Semaphore(10)  # Limit concurrent scoring

        async def score_with_limit(
            slot_start: datetime,
            slot_end: datetime,
        ) -> SmartScheduleOption | None:
            async with semaphore:
                try:
                    return await self._score_slot(
                        tenant_id,
                        slot_start,
                        slot_end,
                        request,
                        participant_availability,
                    )
                except Exception as e:
                    logger.error(f"Error scoring slot {slot_start}: {e}")
                    return None

        # Score all candidates
        results = await asyncio.gather(
            *[score_with_limit(start, end) for start, end in candidate_slots],
            return_exceptions=True,
        )

        # Filter out None results and exceptions
        scored_options: list[SmartScheduleOption] = [
            r
            for r in results
            if r is not None and not isinstance(r, Exception) and isinstance(r, SmartScheduleOption)
        ]

        return scored_options

    async def _score_slot(
        self,
        tenant_id: int,
        slot_start: datetime,
        slot_end: datetime,
        request: SmartScheduleRequest,
        participant_availability: dict[str, list[AvailabilityPrediction]],
    ) -> SmartScheduleOption:
        """Score a potential meeting slot.

        Args:
            tenant_id: Tenant ID
            slot_start: Slot start
            slot_end: Slot end
            request: Scheduling request
            participant_availability: Availability predictions

        Returns:
            Scored schedule option
        """
        # Determine participant availability
        available = []
        unavailable = []
        tentative = []

        all_participants = list(set(request.required_participants + request.optional_participants))

        for user_id in all_participants:
            if user_id in participant_availability:
                preds = participant_availability[user_id]
                avg_availability = self._calculate_average_availability(slot_start, slot_end, preds)

                if avg_availability >= self.config.high_availability_threshold:
                    available.append(user_id)
                elif avg_availability >= self.config.tentative_threshold:
                    tentative.append(user_id)
                else:
                    unavailable.append(user_id)

        # Get quality score
        quality_result = await self.scorer.score_meeting_slot(
            tenant_id=tenant_id,
            start_time=slot_start,
            end_time=slot_end,
            participants=all_participants,
            respect_focus_time=request.prefer_focus_time_protection,
            respect_chronotypes=request.respect_chronotypes,
        )

        # Calculate availability score
        total_required = len(request.required_participants)
        available_required = sum(1 for p in available if p in request.required_participants)
        availability_score = int((available_required / total_required) * 100)

        # Calculate focus impact
        focus_impact = await self._calculate_focus_impact(
            tenant_id, slot_start, slot_end, all_participants
        )

        # Calculate energy score
        energy_score = await self._calculate_energy_score(tenant_id, slot_start, all_participants)

        return SmartScheduleOption(
            start_time=slot_start,
            end_time=slot_end,
            timezone="UTC",
            quality_score=quality_result.total_score,
            quality_breakdown=quality_result,
            availability_score=availability_score,
            focus_impact_score=focus_impact,
            energy_score=energy_score,
            available_participants=available,
            unavailable_participants=unavailable,
            tentative_participants=tentative,
            conflicts=[],
            suggested_resolutions=[],
            suggested_buffers=self._suggest_buffers(slot_start, slot_end),
        )

    def _calculate_average_availability(
        self,
        slot_start: datetime,
        slot_end: datetime,
        predictions: list[AvailabilityPrediction],
    ) -> float:
        """Calculate average availability for a time slot.

        Args:
            slot_start: Slot start
            slot_end: Slot end
            predictions: Availability predictions

        Returns:
            Average availability score
        """
        scores = []
        for pred in predictions:
            if pred.start_time < slot_end and pred.end_time > slot_start:
                scores.append(pred.availability_score)

        if not scores:
            return 0.0

        return sum(scores) / len(scores)

    async def _calculate_focus_impact(
        self,
        tenant_id: int,
        slot_start: datetime,
        slot_end: datetime,
        participants: list[str],
    ) -> int:
        """Calculate focus time impact score (0-100).

        Args:
            tenant_id: Tenant ID
            slot_start: Slot start
            slot_end: Slot end
            participants: Participant IDs

        Returns:
            Focus impact score
        """
        score = 100

        # Morning slots (9-12) are more likely to impact focus time
        if 9 <= slot_start.hour < 12:
            score -= 10

        # Long meetings have more impact
        duration = (slot_end - slot_start).total_seconds() / 60
        if duration > 60:
            score -= 10

        # Check participant profiles for focus time preference
        for user_id in participants:
            cache_key = f"{tenant_id}:{user_id}"
            if cache_key in self._profile_cache:
                profile, _ = self._profile_cache[cache_key]
                if getattr(profile, "protect_focus_time", False):
                    score -= 5

        return max(0, score)

    async def _calculate_energy_score(
        self,
        tenant_id: int,
        slot_start: datetime,
        participants: list[str],
    ) -> int:
        """Calculate energy level score based on chronotypes.

        Args:
            tenant_id: Tenant ID
            slot_start: Slot start (UTC)
            participants: Participant IDs

        Returns:
            Energy score (0-100)
        """
        hour = slot_start.hour

        # Base score by time of day
        base_scores = {
            range(6, 9): 45,  # Early morning
            range(9, 12): 75,  # Mid-morning (optimal)
            range(12, 13): 55,  # Lunch
            range(13, 14): 50,  # Post-lunch dip
            range(14, 17): 70,  # Afternoon
            range(17, 20): 60,  # Evening
            range(20, 24): 40,  # Late evening
        }

        base_score = 50
        for hour_range, score in base_scores.items():
            if hour in hour_range:
                base_score = score
                break

        # Adjust based on participant chronotypes
        if participants:
            adjustments = []
            for user_id in participants:
                cache_key = f"{tenant_id}:{user_id}"
                if cache_key in self._profile_cache:
                    profile, _ = self._profile_cache[cache_key]
                    chronotype = getattr(profile, "chronotype", "neutral")

                    if chronotype == "morning" and hour < 12:
                        adjustments.append(10)
                    elif chronotype == "evening" and hour >= 14:
                        adjustments.append(10)
                    elif chronotype == "neutral":
                        adjustments.append(3)
                    else:
                        adjustments.append(-5)

            if adjustments:
                avg_adjustment = sum(adjustments) / len(adjustments)
                base_score += int(avg_adjustment)

        return max(0, min(100, base_score))

    def _suggest_buffers(
        self,
        slot_start: datetime,
        slot_end: datetime,
    ) -> BufferConfig:
        """Suggest buffer times around meeting.

        Args:
            slot_start: Meeting start
            slot_end: Meeting end

        Returns:
            BufferConfig
        """
        duration = (slot_end - slot_start).total_seconds() / 60

        # Dynamic buffer calculation based on meeting duration
        if duration <= 30:
            prep = 5
            recovery = 5
            reasoning = "Short meeting requires minimal buffer"
        elif duration <= 60:
            prep = 10
            recovery = 10
            reasoning = "Standard buffer for medium meeting"
        else:
            prep = 15
            recovery = 15
            reasoning = "Long meeting requires extended buffer"

        return BufferConfig(
            prep_buffer_minutes=prep,
            recovery_buffer_minutes=recovery,
            travel_buffer_minutes=0,  # Would need location data
            total_buffer_minutes=prep + recovery,
            reasoning=reasoning,
        )

    def clear_cache(self) -> None:
        """Clear the profile cache."""
        self._profile_cache.clear()
        logger.debug("Cleared optimizer cache")
