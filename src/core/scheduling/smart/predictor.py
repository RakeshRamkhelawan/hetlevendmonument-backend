"""Predictive Availability Service.

Analyzes historical calendar patterns to predict future availability.
Uses statistical analysis (not heavy ML) for lightweight predictions.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.scheduling.models import CalendarEvent
from src.core.scheduling.repository import CalendarEventRepository
from src.core.scheduling.smart.models import (
    AvailabilityPattern,
    AvailabilityPrediction,
    CachedUserProfile,
)

logger = logging.getLogger(__name__)


@dataclass
class BatchConfig:
    """Configuration for batch processing."""

    batch_size: int = 1000
    max_batches: int = 100  # Safety limit


class AvailabilityPredictor:
    """Predicts future availability based on historical patterns."""

    # Minimum data points for confidence
    MIN_SAMPLE_SIZE = 4
    MAX_HISTORY_DAYS = 90
    DEFAULT_BATCH_SIZE = 1000

    def __init__(self, db_session: AsyncSession):
        """Initialize predictor with database session.

        Args:
            db_session: Async SQLAlchemy session
        """
        self.db = db_session
        self._profile_cache: dict[str, CachedUserProfile] = {}

    async def predict_availability(
        self,
        user_id: str,
        tenant_id: int,
        start_date: datetime,
        end_date: datetime,
        granularity_minutes: int = 30,
    ) -> list[AvailabilityPrediction]:
        """Predict availability for a date range.

        Args:
            user_id: User to predict for
            tenant_id: Tenant ID
            start_date: Start of prediction range
            end_date: End of prediction range
            granularity_minutes: Time slot granularity (default 30 min)

        Returns:
            List of availability predictions
        """
        try:
            # Normalize dates to UTC
            start_date = self._ensure_utc(start_date)
            end_date = self._ensure_utc(end_date)

            # Load patterns for this user
            patterns = await self._load_patterns(user_id, tenant_id)

            # Generate time slots
            predictions = []
            current = start_date
            while current < end_date:
                slot_end = current + timedelta(minutes=granularity_minutes)
                prediction = self._predict_slot(current, slot_end, patterns)
                predictions.append(prediction)
                current = slot_end

            logger.debug(f"Generated {len(predictions)} predictions for user {user_id}")
            return predictions

        except SQLAlchemyError as e:
            logger.error(f"Database error predicting availability: {e}")
            raise
        except Exception as e:
            logger.exception(f"Unexpected error predicting availability: {e}")
            raise

    async def _load_patterns(
        self, user_id: str, tenant_id: int
    ) -> dict[tuple[int, int], AvailabilityPattern]:
        """Load availability patterns for user.

        Args:
            user_id: User ID
            tenant_id: Tenant ID

        Returns:
            Dict mapping (day_of_week, hour_block) to pattern
        """
        try:
            result = await self.db.execute(
                select(AvailabilityPattern).where(
                    and_(
                        AvailabilityPattern.user_id == user_id,
                        AvailabilityPattern.tenant_id == tenant_id,
                    )
                )
            )
            patterns = result.scalars().all()

            # Index by (day, hour)
            pattern_map = {}
            for pattern in patterns:
                key = (pattern.day_of_week, pattern.hour_block)
                pattern_map[key] = pattern

            return pattern_map
        except SQLAlchemyError as e:
            logger.error(f"Error loading patterns: {e}")
            return {}

    def _predict_slot(
        self,
        start: datetime,
        end: datetime,
        patterns: dict[tuple[int, int], AvailabilityPattern],
    ) -> AvailabilityPrediction:
        """Predict availability for a single time slot.

        Args:
            start: Slot start time (UTC)
            end: Slot end time (UTC)
            patterns: Loaded patterns dict

        Returns:
            Availability prediction
        """
        day_of_week = start.weekday()
        hour_block = start.hour
        key = (day_of_week, hour_block)

        if key in patterns:
            pattern = patterns[key]
            return AvailabilityPrediction(
                start_time=start,
                end_time=end,
                availability_score=pattern.availability_score,
                confidence=pattern.confidence,
                pattern_type="historical",
            )

        # No pattern data - return neutral prediction
        return AvailabilityPrediction(
            start_time=start,
            end_time=end,
            availability_score=0.5,
            confidence=0.0,
            pattern_type="default",
        )

    async def analyze_historical_patterns(
        self,
        user_id: str,
        tenant_id: int,
        days_back: int = 90,
    ) -> dict[str, object]:  # TODO(TYPE): replace Any with concrete type
        """Analyze historical calendar data to build patterns.

        This should be called periodically (weekly) to update patterns.

        Args:
            user_id: User to analyze
            tenant_id: Tenant ID
            days_back: How many days to analyze

        Returns:
            Analysis summary statistics
        """
        import time

        start_time = time.time()

        try:
            end_date = datetime.now(timezone.utc)
            start_date = end_date - timedelta(days=days_back)

            # Get historical events with batching
            events = await self._get_events_batched(
                tenant_id=tenant_id,
                user_id=user_id,
                start=start_date,
                end=end_date,
            )

            # Aggregate by day/hour
            pattern_data = self._aggregate_events(events, start_date, end_date)

            # Save patterns to database
            await self._save_patterns(user_id, tenant_id, pattern_data)  # type: ignore[arg-type]

            analysis_time = int((time.time() - start_time) * 1000)

            return {
                "user_id": user_id,
                "events_analyzed": len(events),
                "date_range": f"{start_date.date()} to {end_date.date()}",
                "patterns_generated": len(pattern_data),
                "analysis_time_ms": analysis_time,
                "success": True,
            }

        except SQLAlchemyError as e:
            logger.error(f"Database error analyzing patterns: {e}")
            return {
                "user_id": user_id,
                "success": False,
                "error": f"Database error: {str(e)}",
            }
        except Exception as e:
            logger.exception(f"Unexpected error analyzing patterns: {e}")
            return {
                "user_id": user_id,
                "success": False,
                "error": str(e),
            }

    async def _get_events_batched(
        self,
        tenant_id: int,
        user_id: str,
        start: datetime,
        end: datetime,
        batch_size: int = 1000,
    ) -> list[CalendarEvent]:
        """Get events with batching for memory efficiency.

        Args:
            tenant_id: Tenant ID
            user_id: User ID
            start: Start date
            end: End date
            batch_size: Number of events per batch

        Returns:
            List of all events
        """

        repo = CalendarEventRepository(self.db)
        all_events = []
        offset = 0
        max_batches = 100  # Safety limit

        for batch_num in range(max_batches):
            batch = await repo.list_by_user_in_range(
                tenant_id=tenant_id,
                user_id=user_id,
                start=start,
                end=end,
            )

            if not batch:
                break

            all_events.extend(batch)
            offset += len(batch)

            if len(batch) < batch_size:
                break

        batch_num = max(0, len(all_events) // batch_size)
        logger.debug(f"Retrieved {len(all_events)} events in {batch_num + 1} batches")
        return all_events

    def _aggregate_events(
        self,
        events: list[CalendarEvent],
        start_date: datetime,
        end_date: datetime,
    ) -> dict[tuple[int, int], dict[str, int]]:
        """Aggregate events into day/hour patterns.

        Args:
            events: List of calendar events
            start_date: Analysis start
            end_date: Analysis end

        Returns:
            Aggregated pattern data
        """
        busy_slots: dict[tuple[int, int], int] = {}
        tentative_slots: dict[tuple[int, int], int] = {}
        total_weeks = max(1, (end_date - start_date).days // 7)

        for event in events:
            try:
                event_start = event.start_time
                event_end = event.end_time

                # Handle None values gracefully
                if not event_start or not event_end:
                    continue

                # Determine event status
                status = self._get_event_status(event)

                current = event_start.replace(minute=0, second=0, microsecond=0)
                while current < event_end:
                    day = current.weekday()
                    hour = current.hour
                    key = (day, hour)

                    if status == "tentative":
                        tentative_slots[key] = tentative_slots.get(key, 0) + 1
                    else:
                        busy_slots[key] = busy_slots.get(key, 0) + 1

                    current += timedelta(hours=1)

            except Exception as e:
                logger.warning(f"Error processing event {getattr(event, 'id', 'unknown')}: {e}")
                continue

        # Build pattern data
        pattern_data = {}
        for day in range(7):
            for hour in range(24):
                key = (day, hour)

                busy_count = busy_slots.get(key, 0)
                tentative_count = tentative_slots.get(key, 0)
                free_count = max(0, total_weeks - busy_count - tentative_count)

                pattern_data[key] = {
                    "day_of_week": day,
                    "hour_block": hour,
                    "total_slots": total_weeks,
                    "busy_slots": busy_count,
                    "free_slots": free_count,
                    "tentative_slots": tentative_count,
                    "sample_weeks": total_weeks,
                }

        return pattern_data

    def _get_event_status(self, event: object) -> str:  # TODO(TYPE): replace Any with concrete type
        """Safely get event status from CalendarEvent.

        Args:
            event: CalendarEvent instance

        Returns:
            Status string: "busy", "tentative", or "free"
        """
        # Check common status fields
        if hasattr(event, "status") and event.status:  # pyright: ignore[reportAttributeAccessIssue]
            status = str(event.status).lower()  # pyright: ignore[reportAttributeAccessIssue]
            if status in ("tentative", "free", "busy"):
                return status

        # Check if it's marked as tentative in other ways
        if hasattr(event, "is_tentative") and event.is_tentative:  # pyright: ignore[reportAttributeAccessIssue]
            return "tentative"

        # Check transparency (transparent = free time)
        if hasattr(event, "transparency"):
            trans = str(event.transparency).lower()  # pyright: ignore[reportAttributeAccessIssue]
            if trans in ("transparent", "free"):
                return "free"

        # Default to busy
        return "busy"

    async def _save_patterns(
        self,
        user_id: str,
        tenant_id: int,
        pattern_data: dict[
            tuple[int, int], dict[str, object]
        ],  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Save aggregated patterns to database.

        Args:
            user_id: User ID
            tenant_id: Tenant ID
            pattern_data: Aggregated pattern data
        """
        try:
            # Delete old patterns
            await self.db.execute(
                delete(AvailabilityPattern).where(
                    and_(
                        AvailabilityPattern.user_id == user_id,
                        AvailabilityPattern.tenant_id == tenant_id,
                    )
                )
            )

            # Insert new patterns in batches
            batch = []
            batch_size = 100

            for data in pattern_data.values():
                pattern = AvailabilityPattern(
                    user_id=user_id,
                    tenant_id=tenant_id,
                    day_of_week=data["day_of_week"],
                    hour_block=data["hour_block"],
                    total_slots=data["total_slots"],
                    busy_slots=data["busy_slots"],
                    free_slots=data["free_slots"],
                    tentative_slots=data["tentative_slots"],
                    sample_weeks=data["sample_weeks"],
                )
                pattern.update_from_stats()
                batch.append(pattern)

                if len(batch) >= batch_size:
                    self.db.add_all(batch)
                    await self.db.flush()
                    batch = []

            # Add remaining patterns
            if batch:
                self.db.add_all(batch)

            await self.db.commit()
            logger.info(f"Saved {len(pattern_data)} patterns for user {user_id}")

        except SQLAlchemyError as e:
            await self.db.rollback()
            logger.error(f"Error saving patterns: {e}")
            raise

    async def get_chronotype_recommendation(self, user_id: str, tenant_id: int) -> str:
        """Recommend chronotype based on patterns.

        Analyzes when user typically has meetings to infer preferences.

        Args:
            user_id: User ID
            tenant_id: Tenant ID

        Returns:
            Recommended chronotype: "morning", "evening", or "neutral"
        """
        try:
            patterns = await self._load_patterns(user_id, tenant_id)

            if not patterns:
                return "neutral"

            # Calculate average meeting density by time of day
            morning_busy = 0
            afternoon_busy = 0
            evening_busy = 0
            morning_total = 0
            afternoon_total = 0
            evening_total = 0

            for (day, hour), pattern in patterns.items():
                if 9 <= hour < 12:
                    morning_busy += pattern.busy_slots
                    morning_total += pattern.total_slots
                elif 13 <= hour < 17:
                    afternoon_busy += pattern.busy_slots
                    afternoon_total += pattern.total_slots
                elif 17 <= hour < 20:
                    evening_busy += pattern.busy_slots
                    evening_total += pattern.total_slots

            # Need data in at least 2 time periods
            valid_periods = sum(1 for t in [morning_total, afternoon_total, evening_total] if t > 0)
            if valid_periods < 2:
                return "neutral"

            # Calculate densities
            morning_density = morning_busy / morning_total if morning_total > 0 else 0
            afternoon_density = afternoon_busy / afternoon_total if afternoon_total > 0 else 0
            evening_density = evening_busy / evening_total if evening_total > 0 else 0

            # Determine chronotype
            threshold = 1.3

            if (
                morning_density > afternoon_density * threshold
                and morning_density > evening_density * threshold
            ):
                return "morning"
            elif (
                evening_density > morning_density * threshold
                and evening_density > afternoon_density * threshold
            ):
                return "evening"
            elif (
                afternoon_density > morning_density * threshold
                and afternoon_density > evening_density * threshold
            ):
                return "neutral"  # Standard work hours

            return "neutral"

        except Exception as e:
            logger.error(f"Error determining chronotype: {e}")
            return "neutral"

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

    def clear_cache(self) -> None:
        """Clear the profile cache."""
        self._profile_cache.clear()
        logger.debug("Cleared predictor cache")
