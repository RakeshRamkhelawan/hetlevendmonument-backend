"""Unit tests for Availability Predictor.

Tests for the predictive availability analysis component.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.scheduling.repository import CalendarEventRepository
from src.core.scheduling.smart.predictor import AvailabilityPredictor


@pytest.fixture
def mock_db():
    """Create properly configured async mock database."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    db.refresh = AsyncMock()
    return db


@pytest.fixture
def sample_events():
    """Create sample calendar events."""
    base_time = datetime.now(timezone.utc).replace(hour=9, minute=0, second=0, microsecond=0)

    events = []
    for i in range(5):
        event = MagicMock()
        event.start_time = base_time + timedelta(days=i)
        event.end_time = base_time + timedelta(days=i, hours=1)
        event.title = f"Meeting {i}"
        event.event_type = "meeting"
        events.append(event)

    return events


@pytest.mark.asyncio
class TestAvailabilityPredictor:
    """Tests for availability prediction."""

    async def test_predict_availability_returns_predictions(self, mock_db):
        """Test that prediction returns list of predictions."""
        predictor = AvailabilityPredictor(mock_db)

        # Mock pattern loading
        mock_patterns = MagicMock()
        mock_patterns.scalars.return_value.all.return_value = []

        mock_db.execute.return_value = mock_patterns

        start = datetime.now(timezone.utc)
        end = start + timedelta(days=1)

        predictions = await predictor.predict_availability(
            user_id="user1",
            tenant_id=1,
            start_date=start,
            end_date=end,
            granularity_minutes=60,
        )

        assert isinstance(predictions, list)

    async def test_chronotype_detection_morning(self, mock_db):
        """Test detection of morning person."""
        predictor = AvailabilityPredictor(mock_db)

        # Create morning-heavy patterns with all time blocks for proper comparison
        patterns = {}
        for day in range(7):
            # Morning hours (9-12) - very busy
            for hour in range(9, 12):
                pattern = MagicMock()
                pattern.day_of_week = day
                pattern.hour_block = hour
                pattern.busy_slots = 10
                pattern.total_slots = 10
                patterns[(day, hour)] = pattern
            # Afternoon hours (13-17) - moderately busy
            for hour in range(13, 17):
                pattern = MagicMock()
                pattern.day_of_week = day
                pattern.hour_block = hour
                pattern.busy_slots = 4
                pattern.total_slots = 10
                patterns[(day, hour)] = pattern
            # Evening hours (17-20) - not busy
            for hour in range(17, 20):
                pattern = MagicMock()
                pattern.day_of_week = day
                pattern.hour_block = hour
                pattern.busy_slots = 1
                pattern.total_slots = 10
                patterns[(day, hour)] = pattern

        with patch.object(predictor, "_load_patterns", return_value=patterns):
            chronotype = await predictor.get_chronotype_recommendation("user1", 1)

        assert chronotype == "morning"

    async def test_chronotype_detection_evening(self, mock_db):
        """Test detection of evening person."""
        predictor = AvailabilityPredictor(mock_db)

        # Create evening-heavy patterns with all time blocks for proper comparison
        patterns = {}
        for day in range(7):
            # Morning hours (9-12) - not busy
            for hour in range(9, 12):
                pattern = MagicMock()
                pattern.day_of_week = day
                pattern.hour_block = hour
                pattern.busy_slots = 1
                pattern.total_slots = 10
                patterns[(day, hour)] = pattern
            # Afternoon hours (13-17) - moderately busy
            for hour in range(13, 17):
                pattern = MagicMock()
                pattern.day_of_week = day
                pattern.hour_block = hour
                pattern.busy_slots = 4
                pattern.total_slots = 10
                patterns[(day, hour)] = pattern
            # Evening hours (17-20) - very busy
            for hour in range(17, 20):
                pattern = MagicMock()
                pattern.day_of_week = day
                pattern.hour_block = hour
                pattern.busy_slots = 10
                pattern.total_slots = 10
                patterns[(day, hour)] = pattern

        with patch.object(predictor, "_load_patterns", return_value=patterns):
            chronotype = await predictor.get_chronotype_recommendation("user1", 1)

        assert chronotype == "evening"

    async def test_pattern_aggregation(self, mock_db):
        """Test event aggregation into patterns."""
        predictor = AvailabilityPredictor(mock_db)

        base_time = datetime.now(timezone.utc)
        events = [
            MagicMock(
                start_time=base_time.replace(hour=9),
                end_time=base_time.replace(hour=10),
                title="Meeting",
                event_type="meeting",
            )
        ]

        start = base_time - timedelta(days=7)
        end = base_time

        patterns = predictor._aggregate_events(events, start, end)

        assert isinstance(patterns, dict)
        # Check first key has the right structure
        first_key = next(iter(patterns))
        assert "busy_slots" in patterns[first_key]
        assert "tentative_slots" in patterns[first_key]
        assert "free_slots" in patterns[first_key]

    async def test_min_sample_size_enforcement(self, mock_db):
        """Test minimum sample size for patterns."""
        predictor = AvailabilityPredictor(mock_db)

        # Mock repository to return only a few events (below minimum sample size)
        mock_event = MagicMock()
        mock_event.start_time = datetime.now(timezone.utc)
        mock_event.end_time = datetime.now(timezone.utc) + timedelta(hours=1)

        mock_repo = MagicMock(spec=CalendarEventRepository)
        mock_repo.list_by_user_in_range = AsyncMock(return_value=[mock_event] * 3)

        with patch("src.core.scheduling.repository.CalendarEventRepository", return_value=mock_repo):
            summary = await predictor.analyze_historical_patterns("user1", 1, days_back=30)

            # Should succeed but with limited data
            assert isinstance(summary, dict)
            assert summary.get("events_analyzed", 0) < 10  # Very few events

    async def test_historical_pattern_analysis(self, mock_db):
        """Test full historical pattern analysis."""
        predictor = AvailabilityPredictor(mock_db)

        # Mock events
        mock_event = MagicMock()
        mock_event.start_time = datetime.now(timezone.utc)
        mock_event.end_time = datetime.now(timezone.utc) + timedelta(hours=1)
        mock_event.title = "Test"
        mock_event.event_type = "meeting"

        # Mock repository
        mock_repo = MagicMock(spec=CalendarEventRepository)
        mock_repo.list_by_user_in_range = AsyncMock(return_value=[mock_event] * 10)

        with patch("src.core.scheduling.repository.CalendarEventRepository", return_value=mock_repo):
            # Mock patterns update
            mock_db.execute = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            mock_db.execute.return_value = mock_result

            summary = await predictor.analyze_historical_patterns("user1", 1, days_back=30)

            assert isinstance(summary, dict)
            assert "success" in summary

    async def test_pattern_confidence_calculation(self, mock_db):
        """Test confidence calculation based on sample size."""
        predictor = AvailabilityPredictor(mock_db)

        # Test pattern objects with different sample sizes
        high_pattern = MagicMock(sample_weeks=12)
        low_pattern = MagicMock(sample_weeks=3)

        # Test via calculate_confidence method
        # Create actual AvailabilityPattern objects with sample_weeks
        from src.core.scheduling.smart.models import AvailabilityPattern

        high_ap = AvailabilityPattern(sample_weeks=12)
        low_ap = AvailabilityPattern(sample_weeks=3)

        confidence_high = high_ap.calculate_confidence()
        confidence_low = low_ap.calculate_confidence()

        assert confidence_high > confidence_low
        assert 0 <= confidence_high <= 1
        assert 0 <= confidence_low <= 1

    async def test_batch_processing_events(self, mock_db):
        """Test batch processing of large event sets."""
        predictor = AvailabilityPredictor(mock_db)

        # Create many events
        events = [MagicMock() for _ in range(100)]
        for i, event in enumerate(events):
            event.start_time = datetime.now(timezone.utc) + timedelta(hours=i)
            event.end_time = event.start_time + timedelta(hours=1)
            event.event_type = "meeting"

        start = datetime.now(timezone.utc) - timedelta(days=90)
        end = datetime.now(timezone.utc)

        # Should process without memory issues
        patterns = predictor._aggregate_events(events, start, end)

        assert isinstance(patterns, dict)

    async def test_prediction_with_existing_patterns(self, mock_db):
        """Test prediction when patterns exist."""
        predictor = AvailabilityPredictor(mock_db)

        # Create a specific start time (Friday at 9 AM)
        start = datetime(2026, 3, 20, 9, 0, 0, tzinfo=timezone.utc)
        end = start + timedelta(hours=2)

        # Create mock patterns dict matching the weekday and hour
        day_of_week = start.weekday()  # Friday = 4
        hour_block = start.hour  # 9

        mock_pattern = MagicMock()
        mock_pattern.day_of_week = day_of_week
        mock_pattern.hour_block = hour_block
        mock_pattern.availability_score = 0.8
        mock_pattern.confidence = 0.9

        mock_patterns = {(day_of_week, hour_block): mock_pattern}

        with patch.object(predictor, "_load_patterns", return_value=mock_patterns):
            predictions = await predictor.predict_availability("user1", 1, start, end)

            assert isinstance(predictions, list)
            assert len(predictions) > 0
            # First prediction should match our pattern
            assert predictions[0].availability_score == 0.8
            assert predictions[0].confidence == 0.9

    async def test_empty_database_handling(self, mock_db):
        """Test handling when no data exists."""
        predictor = AvailabilityPredictor(mock_db)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []

        mock_db.execute.return_value = mock_result

        start = datetime.now(timezone.utc)
        end = start + timedelta(days=7)

        predictions = await predictor.predict_availability("user1", 1, start, end)

        # Should return predictions with default values
        assert isinstance(predictions, list)
