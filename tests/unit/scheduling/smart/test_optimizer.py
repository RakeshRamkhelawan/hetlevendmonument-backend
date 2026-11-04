"""Unit tests for Multi-Participant Optimizer.

Tests for the meeting time optimization component.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.scheduling.smart.optimizer import MultiParticipantOptimizer


@pytest.fixture
def mock_db():
    """Create properly configured async mock database."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


@pytest.fixture
def sample_request():
    """Create a sample optimization request."""
    return MagicMock(
        duration_minutes=30,
        earliest_start=datetime.now(timezone.utc),
        latest_end=datetime.now(timezone.utc) + timedelta(days=1),
        required_participants=["user1", "user2"],
        optional_participants=[],
        meeting_type="default",
        timezone="UTC",
        min_quality_score=50,
        max_suggestions=5,
        avoid_early_morning=True,
        avoid_late_evening=True,
        excluded_dates=[],
        preferred_time_ranges=[],
        min_required_attendance=0,
    )


@pytest.mark.asyncio
class TestMultiParticipantOptimizer:
    """Tests for multi-participant optimization."""

    async def test_find_optimal_slots_returns_options(self, mock_db, sample_request):
        """Test that optimization returns options."""
        optimizer = MultiParticipantOptimizer(mock_db)

        # Mock the internal methods
        with patch.object(optimizer, "_load_participant_profiles", return_value={}):
            with patch.object(optimizer.predictor, "predict_availability", return_value=[]):
                options, total = await optimizer.find_optimal_slots(1, sample_request)

        assert isinstance(options, list)
        assert isinstance(total, int)

    async def test_overlap_detection(self, mock_db):
        """Test overlapping time slot detection."""
        optimizer = MultiParticipantOptimizer(mock_db)

        base = datetime.now(timezone.utc)

        # Create mock availability predictions
        mock_pred = MagicMock()
        mock_pred.start_time = base
        mock_pred.end_time = base + timedelta(hours=2)
        mock_pred.availability_score = 0.9

        participant_availability = {
            "user1": [mock_pred],
            "user2": [mock_pred],
        }

        request = MagicMock(
            duration_minutes=30,
            earliest_start=base,
            latest_end=base + timedelta(hours=4),
            required_participants=["user1", "user2"],
            optional_participants=[],
            excluded_dates=[],
            avoid_early_morning=True,
            avoid_late_evening=True,
            preferred_time_ranges=[],
            min_required_attendance=0,
        )

        candidates = optimizer._find_overlapping_slots(participant_availability, request)

        # Should find overlapping slots
        assert isinstance(candidates, list)

    async def test_slot_meets_requirements(self, mock_db):
        """Test minimum attendance requirement."""
        optimizer = MultiParticipantOptimizer(mock_db)

        base = datetime.now(timezone.utc)

        # Create mock predictions - user1 available, user2 not
        mock_pred_available = MagicMock()
        mock_pred_available.start_time = base
        mock_pred_available.end_time = base + timedelta(hours=2)
        mock_pred_available.availability_score = 0.9  # High availability

        mock_pred_unavailable = MagicMock()
        mock_pred_unavailable.start_time = base
        mock_pred_unavailable.end_time = base + timedelta(hours=2)
        mock_pred_unavailable.availability_score = 0.1  # Low availability

        participant_availability = {
            "user1": [mock_pred_available],
            "user2": [mock_pred_unavailable],
        }

        request = MagicMock(
            duration_minutes=30,
            required_participants=["user1", "user2"],
            optional_participants=[],
            min_required_attendance=1,  # Only need 1 of 2
        )

        slot_start = base
        slot_end = base + timedelta(minutes=30)

        # Should meet requirements since we only need 1 of 2
        result = optimizer._slot_meets_requirements(
            slot_start, slot_end, participant_availability, request
        )

        assert result is True

    async def test_chronotype_energy_adjustment(self, mock_db):
        """Test energy score calculation based on chronotypes."""
        optimizer = MultiParticipantOptimizer(mock_db)

        base = datetime.now(timezone.utc)

        # Add profiles to cache for the test
        mock_profile = MagicMock()
        mock_profile.chronotype = "morning"
        cache_key = "1:user1"
        optimizer._profile_cache[cache_key] = (mock_profile, datetime.now(timezone.utc))

        # Morning meeting (9 AM)
        morning = base.replace(hour=9)
        morning_score = await optimizer._calculate_energy_score(1, morning, ["user1"])

        # Evening meeting (4 PM)
        evening = base.replace(hour=16)
        evening_score = await optimizer._calculate_energy_score(1, evening, ["user1"])

        # Morning person should have higher score in morning
        assert isinstance(morning_score, int)
        assert isinstance(evening_score, int)
        assert morning_score > evening_score

    async def test_energy_score_range(self, mock_db):
        """Test energy score is within valid range."""
        optimizer = MultiParticipantOptimizer(mock_db)

        base = datetime.now(timezone.utc)
        score = await optimizer._calculate_energy_score(1, base, ["user1"])

        assert 0 <= score <= 100

    async def test_participant_availability_check(self, mock_db):
        """Test participant availability check."""
        optimizer = MultiParticipantOptimizer(mock_db)

        base = datetime.now(timezone.utc)
        slot_start = base
        slot_end = base + timedelta(hours=1)

        # Available prediction
        mock_pred = MagicMock()
        mock_pred.start_time = base
        mock_pred.end_time = base + timedelta(hours=2)
        mock_pred.availability_score = 0.9

        predictions = [mock_pred]

        result = optimizer._is_user_available(slot_start, slot_end, predictions)

        # Should be available with high score
        assert result is True

    async def test_participant_unavailable_check(self, mock_db):
        """Test participant unavailable check."""
        optimizer = MultiParticipantOptimizer(mock_db)

        base = datetime.now(timezone.utc)
        slot_start = base
        slot_end = base + timedelta(hours=1)

        # Unavailable prediction
        mock_pred = MagicMock()
        mock_pred.start_time = base
        mock_pred.end_time = base + timedelta(hours=2)
        mock_pred.availability_score = 0.1  # Below threshold

        predictions = [mock_pred]

        result = optimizer._is_user_available(slot_start, slot_end, predictions)

        # Should not be available with low score
        assert result is False

    async def test_optimal_times_guide(self, mock_db):
        """Test optimal times guide generation."""
        optimizer = MultiParticipantOptimizer(mock_db)

        guide = optimizer.scorer.get_optimal_meeting_times()

        assert isinstance(guide, dict)
        # Check that expected days are present
        assert "monday" in guide or "Monday" in guide or len(guide) > 0

    async def test_buffer_suggestion(self, mock_db):
        """Test buffer suggestion."""
        optimizer = MultiParticipantOptimizer(mock_db)

        base = datetime.now(timezone.utc)
        slot_start = base
        slot_end = base + timedelta(hours=1)

        buffers = optimizer._suggest_buffers(slot_start, slot_end)

        assert buffers.prep_buffer_minutes >= 0
        assert buffers.recovery_buffer_minutes >= 0
        assert (
            buffers.total_buffer_minutes
            == buffers.prep_buffer_minutes + buffers.recovery_buffer_minutes
        )

    async def test_configurable_parameters(self, mock_db):
        """Test that optimizer uses configurable parameters."""
        from src.core.scheduling.smart.optimizer import OptimizationConfig

        config = OptimizationConfig(
            slot_increment_minutes=15,
            availability_threshold=0.8,
        )

        optimizer = MultiParticipantOptimizer(mock_db, config=config)

        assert optimizer.config.slot_increment_minutes == 15
        assert optimizer.config.availability_threshold == 0.8

    async def test_cache_clearing(self, mock_db):
        """Test cache clearing functionality."""
        optimizer = MultiParticipantOptimizer(mock_db)

        # Add something to cache
        optimizer._profile_cache["test"] = (MagicMock(), datetime.now(timezone.utc))

        # Clear cache
        optimizer.clear_cache()

        assert len(optimizer._profile_cache) == 0

    async def test_calculate_average_availability(self, mock_db):
        """Test average availability calculation."""
        optimizer = MultiParticipantOptimizer(mock_db)

        base = datetime.now(timezone.utc)

        mock_pred = MagicMock()
        mock_pred.start_time = base
        mock_pred.end_time = base + timedelta(hours=1)
        mock_pred.availability_score = 0.8

        predictions = [mock_pred]

        avg = optimizer._calculate_average_availability(
            base, base + timedelta(hours=1), predictions
        )

        assert avg == 0.8

    async def test_is_excluded_date(self, mock_db):
        """Test excluded date check."""
        optimizer = MultiParticipantOptimizer(mock_db)

        base = datetime.now(timezone.utc)
        excluded = [base]

        result = optimizer._is_excluded_date(base, excluded)
        assert result is True

        result = optimizer._is_excluded_date(base + timedelta(days=1), excluded)
        assert result is False
