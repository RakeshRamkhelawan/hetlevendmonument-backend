from __future__ import annotations

"""Smart Scheduling Service.

Main service that orchestrates all smart scheduling capabilities with
transaction management and comprehensive error handling.
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.scheduling.smart.models import (
    AvailabilityPredictionResponse,
    Chronotype,
    PatternAnalysisResponse,
    QualityScoreBreakdown,
    SmartScheduleOption,
    SmartScheduleRequest,
    SmartScheduleResponse,
    UserSchedulingProfile,
    UserSchedulingProfileCreate,
    UserSchedulingProfileResponse,
)
from src.core.scheduling.smart.optimizer import MultiParticipantOptimizer
from src.core.scheduling.smart.predictor import AvailabilityPredictor
from src.core.scheduling.smart.resolver import ConflictResolver

logger = logging.getLogger(__name__)


class SmartSchedulingService:
    """Main service for smart scheduling intelligence."""

    ALGORITHM_VERSION = "1.0"

    def __init__(self, db_session: AsyncSession) -> None:
        """Initialize service.

        Args:
            db_session: Database session
        """
        self.db = db_session
        self.predictor = AvailabilityPredictor(db_session)
        self.optimizer = MultiParticipantOptimizer(db_session)
        self.resolver = ConflictResolver(db_session)

    async def find_optimal_meeting_times(
        self,
        tenant_id: int,
        request: SmartScheduleRequest,
    ) -> SmartScheduleResponse:
        """Find optimal meeting times using AI-powered scheduling.

        This is the main entry point for smart scheduling. It:
        1. Analyzes historical patterns for all participants
        2. Finds optimal overlapping time slots
        3. Scores each option based on quality factors
        4. Detects and suggests resolutions for conflicts

        Args:
            tenant_id: Tenant ID
            request: Scheduling request

        Returns:
            Smart schedule response with options
        """
        start_time = time.time()

        logger.info(
            f"Finding optimal meeting times for {len(request.required_participants)} "
            f"required participants in tenant {tenant_id}"
        )

        try:
            # Step 1: Find optimal slots using optimizer
            options, total_considered = await self.optimizer.find_optimal_slots(tenant_id, request)

            # Step 2: Enhance options with conflict resolution
            enhanced_options = await self._enhance_with_conflicts(tenant_id, options, request)

            # Filter out options that don't meet minimum quality
            filtered_options = [
                opt for opt in enhanced_options if opt.quality_score >= request.min_quality_score
            ]

            total_filtered = len(enhanced_options) - len(filtered_options)

            generation_time = int((time.time() - start_time) * 1000)

            logger.info(
                f"Generated {len(filtered_options)} options (filtered {total_filtered}) "
                f"in {generation_time}ms"
            )

            return SmartScheduleResponse(
                request=request,
                options=filtered_options[: request.max_suggestions],
                total_options_considered=total_considered,
                total_options_filtered=total_filtered,
                generated_at=datetime.now(timezone.utc),
                generation_time_ms=generation_time,
                algorithm_version=self.ALGORITHM_VERSION,
            )

        except Exception as e:
            logger.exception(f"Error finding optimal meeting times: {e}")
            # Return empty response on error
            return SmartScheduleResponse(
                request=request,
                options=[],
                total_options_considered=0,
                total_options_filtered=0,
                generated_at=datetime.now(timezone.utc),
                generation_time_ms=int((time.time() - start_time) * 1000),
                algorithm_version=self.ALGORITHM_VERSION,
            )

    async def _enhance_with_conflicts(
        self,
        tenant_id: int,
        options: list[SmartScheduleOption],
        request: SmartScheduleRequest,
    ) -> list[SmartScheduleOption]:
        """Enhance options with conflict detection and resolution.

        Args:
            tenant_id: Tenant ID
            options: Schedule options
            request: Original request

        Returns:
            Enhanced options with conflict info
        """
        enhanced = []

        for option in options:
            try:
                # Detect conflicts for unavailable participants
                unavailable = option.unavailable_participants

                if unavailable:
                    conflicts = await self.resolver.detect_conflicts(
                        tenant_id=tenant_id,
                        proposed_start=option.start_time,
                        proposed_end=option.end_time,
                        participants=unavailable,
                    )

                    if conflicts:
                        # Resolve conflicts
                        resolutions = await self.resolver.resolve_conflicts(
                            tenant_id=tenant_id,
                            conflicts=conflicts,
                            original_start=option.start_time,
                            original_end=option.end_time,
                        )

                        option.conflicts = conflicts
                        option.suggested_resolutions = resolutions

                enhanced.append(option)

            except Exception as e:
                logger.warning(f"Error enhancing option with conflicts: {e}")
                enhanced.append(option)

        return enhanced

    async def predict_user_availability(
        self,
        user_id: str,
        tenant_id: int,
        start_date: datetime,
        end_date: datetime,
    ) -> AvailabilityPredictionResponse:
        """Predict availability for a user.

        Args:
            user_id: User ID
            tenant_id: Tenant ID
            start_date: Start date
            end_date: End date

        Returns:
            Availability predictions
        """
        from src.core.scheduling.smart.models import AvailabilityPredictionResponse  # noqa: F401

        try:
            # Get user's timezone
            profile = await self.get_or_create_user_profile(user_id, tenant_id)
            user_timezone = profile.timezone if profile else "UTC"

            predictions = await self.predictor.predict_availability(
                user_id=user_id,
                tenant_id=tenant_id,
                start_date=start_date,
                end_date=end_date,
                granularity_minutes=30,
            )

            return AvailabilityPredictionResponse(
                user_id=user_id,
                start_date=start_date,
                end_date=end_date,
                predictions=predictions,
                generated_at=datetime.now(timezone.utc),
                timezone=user_timezone,
            )

        except Exception as e:
            logger.exception(f"Error predicting availability: {e}")
            raise

    async def analyze_user_patterns(
        self,
        user_id: str,
        tenant_id: int,
        days_back: int = 90,
    ) -> PatternAnalysisResponse:
        """Analyze and update user scheduling patterns.

        This should be called periodically (e.g., weekly) to update
        the ML models with new calendar data.

        Args:
            user_id: User ID
            tenant_id: Tenant ID
            days_back: Days of history to analyze

        Returns:
            Analysis summary
        """
        start_time = time.time()

        try:
            # Analyze historical patterns
            summary = await self.predictor.analyze_historical_patterns(
                user_id=user_id,
                tenant_id=tenant_id,
                days_back=days_back,
            )

            if not summary.get("success", False):
                return PatternAnalysisResponse(
                    user_id=user_id,
                    events_analyzed=0,
                    date_range="",
                    patterns_generated=0,
                    recommended_chronotype=Chronotype.NEUTRAL,
                    confidence=0.0,
                    analysis_time_ms=int((time.time() - start_time) * 1000),
                    completed_at=datetime.now(timezone.utc),
                )

            # Update chronotype recommendation
            chronotype = await self.predictor.get_chronotype_recommendation(user_id, tenant_id)

            await self._update_user_chronotype(user_id, tenant_id, chronotype)

            analysis_time = int((time.time() - start_time) * 1000)

            return PatternAnalysisResponse(
                user_id=user_id,
                events_analyzed=summary.get("events_analyzed", 0),  # type: ignore[arg-type]
                date_range=summary.get("date_range", ""),  # type: ignore[arg-type]
                patterns_generated=summary.get("patterns_generated", 0),  # type: ignore[arg-type]
                recommended_chronotype=Chronotype(chronotype),
                confidence=summary.get("pattern_confidence", 0.5),  # type: ignore[arg-type]
                analysis_time_ms=analysis_time,
                completed_at=datetime.now(timezone.utc),
            )

        except Exception as e:
            logger.exception(f"Error analyzing user patterns: {e}")
            raise

    async def _update_user_chronotype(
        self,
        user_id: str,
        tenant_id: int,
        chronotype: str,
    ) -> None:
        """Update user's chronotype in their profile.

        Args:
            user_id: User ID
            tenant_id: Tenant ID
            chronotype: New chronotype
        """
        try:
            from sqlalchemy import select

            result = await self.db.execute(
                select(UserSchedulingProfile).where(
                    UserSchedulingProfile.user_id == user_id,
                    UserSchedulingProfile.tenant_id == tenant_id,
                )
            )
            profile = result.scalar_one_or_none()

            if profile:
                profile.chronotype = chronotype
                profile.pattern_confidence = 0.8
                profile.last_pattern_analysis = datetime.now(timezone.utc)
                await self.db.commit()

        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error(f"Error updating chronotype: {e}")
            raise

    async def get_or_create_user_profile(
        self,
        user_id: str,
        tenant_id: int,
    ) -> UserSchedulingProfile:
        """Get or create user scheduling profile.

        Args:
            user_id: User ID
            tenant_id: Tenant ID

        Returns:
            User scheduling profile
        """
        from sqlalchemy import select

        result = await self.db.execute(
            select(UserSchedulingProfile).where(
                UserSchedulingProfile.user_id == user_id,
                UserSchedulingProfile.tenant_id == tenant_id,
            )
        )
        profile = result.scalar_one_or_none()

        if profile:
            return profile

        # Create default profile within transaction
        try:
            profile = UserSchedulingProfile(
                user_id=user_id,
                tenant_id=tenant_id,
            )
            self.db.add(profile)
            await self.db.commit()
            await self.db.refresh(profile)

            logger.info(f"Created scheduling profile for user {user_id}")
            return profile

        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error(f"Error creating profile: {e}")
            raise

    async def update_user_profile(
        self,
        user_id: str,
        tenant_id: int,
        data: UserSchedulingProfileCreate,
    ) -> UserSchedulingProfileResponse:
        """Update user scheduling profile.

        Args:
            user_id: User ID
            tenant_id: Tenant ID
            data: Profile update data

        Returns:
            Updated profile
        """
        try:
            from sqlalchemy import select

            result = await self.db.execute(
                select(UserSchedulingProfile).where(
                    UserSchedulingProfile.user_id == user_id,
                    UserSchedulingProfile.tenant_id == tenant_id,
                )
            )
            profile = result.scalar_one_or_none()

            if not profile:
                profile = UserSchedulingProfile(
                    user_id=user_id,
                    tenant_id=tenant_id,
                )
                self.db.add(profile)

            # Update fields
            profile.chronotype = (
                data.chronotype if isinstance(data.chronotype, str) else data.chronotype.value
            )
            profile.timezone = data.timezone
            profile.preferred_morning_start = data.preferred_morning_start
            profile.preferred_morning_end = data.preferred_morning_end
            profile.preferred_afternoon_start = data.preferred_afternoon_start
            profile.preferred_afternoon_end = data.preferred_afternoon_end
            profile.focus_time_min_duration = data.focus_time_min_duration
            profile.protect_focus_time = data.protect_focus_time
            profile.default_prep_buffer = data.default_prep_buffer
            profile.default_recovery_buffer = data.default_recovery_buffer
            profile.travel_buffer_minutes = data.travel_buffer_minutes
            profile.max_meetings_per_day = data.max_meetings_per_day
            profile.max_consecutive_meetings = data.max_consecutive_meetings
            profile.updated_at = datetime.now(timezone.utc)

            await self.db.commit()
            await self.db.refresh(profile)

            return UserSchedulingProfileResponse.model_validate(profile)

        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error(f"Error updating profile: {e}")
            raise

    async def get_meeting_quality_score(
        self,
        tenant_id: int,
        start_time: datetime,
        end_time: datetime,
        participants: list[str],
    ) -> QualityScoreBreakdown:
        """Get quality score for a specific meeting time.

        Args:
            tenant_id: Tenant ID
            start_time: Meeting start
            end_time: Meeting end
            participants: Participant IDs

        Returns:
            Quality score breakdown
        """
        try:
            return await self.optimizer.scorer.score_meeting_slot(
                tenant_id=tenant_id,
                start_time=start_time,
                end_time=end_time,
                participants=participants,
            )
        except Exception as e:
            logger.error(f"Error getting quality score: {e}")
            # Return neutral score on error
            return QualityScoreBreakdown(
                focus_time_protection=12,
                energy_level=10,
                travel_efficiency=10,
                participant_availability=10,
                buffer_compliance=7,
                total_score=49,
            )

    async def resolve_scheduling_conflicts(
        self,
        tenant_id: int,
        event_id: str,
        resolution_strategy: str | None = None,
    ) -> list[Any]:  # TODO(TYPE): replace Any with concrete type
        """Resolve conflicts for an existing event.

        Args:
            tenant_id: Tenant ID
            event_id: Event ID
            resolution_strategy: Optional specific strategy to use

        Returns:
            Resolution options
        """
        # This would load the event and generate resolution options
        # Implementation depends on event storage
        logger.info(f"Resolving conflicts for event {event_id}")
        return []

    async def get_optimal_times_for_participants(
        self,
        tenant_id: int,
        participants: list[str],
        duration_minutes: int,
        days_ahead: int = 7,
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get optimal meeting times for a group of participants.

        Args:
            tenant_id: Tenant ID
            participants: List of participant IDs
            duration_minutes: Meeting duration
            days_ahead: Number of days to look ahead

        Returns:
            List of optimal time suggestions
        """
        try:
            start_date = datetime.now(timezone.utc)
            end_date = start_date + timedelta(days=days_ahead)

            request = SmartScheduleRequest(
                title="Suggested Meeting",
                description=None,
                duration_minutes=duration_minutes,
                required_participants=participants,
                earliest_start=start_date,
                latest_end=end_date,
                max_suggestions=5,
            )

            result = await self.find_optimal_meeting_times(tenant_id, request)

            return [
                {
                    "start": opt.start_time.isoformat(),
                    "end": opt.end_time.isoformat(),
                    "quality_score": opt.quality_score,
                    "available_participants": opt.available_participants,
                }
                for opt in result.options
            ]

        except Exception as e:
            logger.error(f"Error getting optimal times: {e}")
            return []
