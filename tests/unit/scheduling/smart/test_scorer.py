"""Unit tests for Meeting Quality Scorer.

Tests for the 100-point meeting quality scoring system.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.scheduling.smart.scorer import MeetingQualityScorer, ScoringContext


@pytest.fixture
def mock_db():
    """Create properly configured async mock database."""
    db = AsyncMock()
    db.execute = AsyncMock()
    return db


@pytest.mark.asyncio
class TestMeetingQualityScorer:
    """Tests for meeting quality scoring."""

    async def test_score_meeting_slot_returns_breakdown(self, mock_db):
        """Test that scoring returns proper breakdown."""
        scorer = MeetingQualityScorer(mock_db)

        # Mock profile query
        mock_profile = MagicMock()
        mock_profile.chronotype = "morning"
        mock_profile.protect_focus_time = True
        mock_profile.focus_time_min_duration = 120
        mock_profile.default_prep_buffer = 15
        mock_profile.default_recovery_buffer = 15

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_profile]
        mock_db.execute.return_value = mock_result

        result = await scorer.score_meeting_slot(
            tenant_id=1,
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc) + timedelta(hours=1),
            participants=["user1", "user2"],
        )

        assert result.total_score >= 0
        assert result.total_score <= 100
        assert hasattr(result, "focus_time_protection")
        assert hasattr(result, "energy_level")
        assert hasattr(result, "travel_efficiency")
        assert hasattr(result, "participant_availability")
        assert hasattr(result, "buffer_compliance")

    async def test_energy_level_scoring(self, mock_db):
        """Test energy level scoring."""
        scorer = MeetingQualityScorer(mock_db)

        # Morning slot
        start = datetime.now(timezone.utc).replace(hour=9, minute=0)
        end = start + timedelta(hours=1)

        context = ScoringContext(
            tenant_id=1,
            start_time=start,
            end_time=end,
            participants=["user1"],
            respect_focus_time=True,
            respect_chronotypes=True,
        )

        score = await scorer._score_energy_level(context)

        assert isinstance(score, int)
        assert 0 <= score <= 20

    async def test_energy_level_with_chronotypes(self, mock_db):
        """Test energy level with chronotype adjustments."""
        scorer = MeetingQualityScorer(mock_db)

        # Morning slot
        start = datetime.now(timezone.utc).replace(hour=9, minute=0)
        end = start + timedelta(hours=1)

        context = ScoringContext(
            tenant_id=1,
            start_time=start,
            end_time=end,
            participants=["user1"],
            respect_focus_time=True,
            respect_chronotypes=True,
        )

        # Mock morning person profile
        mock_profile = MagicMock()
        mock_profile.chronotype = "morning"

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_profile]
        mock_db.execute.return_value = mock_result

        score = await scorer._score_energy_level(context)

        assert isinstance(score, int)
        assert 0 <= score <= 20

    async def test_travel_efficiency_scoring(self, mock_db):
        """Test travel efficiency scoring."""
        scorer = MeetingQualityScorer(mock_db)

        context = ScoringContext(
            tenant_id=1,
            start_time=datetime.now(timezone.utc).replace(hour=10),
            end_time=datetime.now(timezone.utc).replace(hour=11),
            participants=["user1"],
            respect_focus_time=True,
            respect_chronotypes=True,
        )

        score = await scorer._score_travel_efficiency(context)

        assert isinstance(score, int)
        assert 0 <= score <= 20

    async def test_participant_availability_scoring(self, mock_db):
        """Test participant availability scoring."""
        scorer = MeetingQualityScorer(mock_db)

        context = ScoringContext(
            tenant_id=1,
            start_time=datetime.now(timezone.utc).replace(hour=10),
            end_time=datetime.now(timezone.utc).replace(hour=11),
            participants=["user1", "user2"],
            respect_focus_time=True,
            respect_chronotypes=True,
        )

        score = await scorer._score_participant_availability(context)

        assert isinstance(score, int)
        assert 0 <= score <= 20

    async def test_buffer_compliance_scoring(self, mock_db):
        """Test buffer compliance scoring."""
        scorer = MeetingQualityScorer(mock_db)

        context = ScoringContext(
            tenant_id=1,
            start_time=datetime.now(timezone.utc).replace(hour=10),
            end_time=datetime.now(timezone.utc).replace(hour=11),
            participants=["user1"],
            respect_focus_time=True,
            respect_chronotypes=True,
        )

        score = await scorer._score_buffer_compliance(context)

        assert isinstance(score, int)
        assert 0 <= score <= 15

    async def test_optimal_times_guide(self, mock_db):
        """Test optimal times guide generation."""
        scorer = MeetingQualityScorer(mock_db)

        guide = scorer.get_optimal_meeting_times()

        assert isinstance(guide, dict)
        assert "monday" in guide
        assert "tuesday" in guide
        assert "friday" in guide

        for day_data in guide.values():
            assert "optimal" in day_data
            assert "avoid" in day_data
            assert "reasoning" in day_data

    async def test_quality_score_grades(self, mock_db):
        """Test quality score grade interpretation."""
        scorer = MeetingQualityScorer(mock_db)

        # Test different score ranges via _get_quality_grade
        # Note: This method doesn't exist in scorer, let's add it to QualityScoreBreakdown
        from src.core.scheduling.smart.models import QualityScoreBreakdown

        # Create breakdowns with different scores
        breakdown_a = QualityScoreBreakdown(
            focus_time_protection=25,
            energy_level=20,
            travel_efficiency=20,
            participant_availability=20,
            buffer_compliance=15,
            total_score=95,
        )
        assert breakdown_a.get_grade() == "A"

        breakdown_f = QualityScoreBreakdown(
            focus_time_protection=5,
            energy_level=5,
            travel_efficiency=5,
            participant_availability=5,
            buffer_compliance=5,
            total_score=25,
        )
        assert breakdown_f.get_grade() == "F"

    async def test_timezone_awareness(self, mock_db):
        """Test that scoring is timezone-aware."""
        scorer = MeetingQualityScorer(mock_db)

        # Create times with explicit timezone
        start = datetime(2026, 3, 20, 9, 0, tzinfo=timezone.utc)
        end = start + timedelta(hours=1)

        result = await scorer.score_meeting_slot(
            tenant_id=1,
            start_time=start,
            end_time=end,
            participants=["user1"],
        )

        assert isinstance(result.total_score, int)

    async def test_error_handling(self, mock_db):
        """Test error handling in scoring."""
        scorer = MeetingQualityScorer(mock_db)

        # Make db.execute raise an error
        mock_db.execute.side_effect = Exception("Database error")

        result = await scorer.score_meeting_slot(
            tenant_id=1,
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc) + timedelta(hours=1),
            participants=["user1"],
        )

        # Should return a fallback score on error (could be neutral or calculated)
        assert isinstance(result.total_score, int)
        assert 0 <= result.total_score <= 100

    async def test_no_participants_energy_score(self, mock_db):
        """Test energy score with no participants."""
        scorer = MeetingQualityScorer(mock_db)

        context = ScoringContext(
            tenant_id=1,
            start_time=datetime.now(timezone.utc).replace(hour=10),
            end_time=datetime.now(timezone.utc).replace(hour=11),
            participants=[],
            respect_focus_time=True,
            respect_chronotypes=True,
        )

        score = await scorer._score_energy_level(context)

        # Should return base score
        assert isinstance(score, int)
        assert 0 <= score <= 20

    async def test_focus_time_protection_scoring(self, mock_db):
        """Test focus time protection scoring."""
        scorer = MeetingQualityScorer(mock_db)

        # Morning slot (10 AM) - prime focus time
        context = ScoringContext(
            tenant_id=1,
            start_time=datetime.now(timezone.utc).replace(hour=10),
            end_time=datetime.now(timezone.utc).replace(hour=11),
            participants=["user1"],
            respect_focus_time=True,
            respect_chronotypes=True,
        )

        # Mock user with focus time protection
        mock_profile = MagicMock()
        mock_profile.protect_focus_time = True

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_profile]
        mock_db.execute.return_value = mock_result

        score = await scorer._score_focus_time_protection(context)

        assert isinstance(score, int)
        assert 0 <= score <= 25

    async def test_respect_focus_time_disabled(self, mock_db):
        """Test scoring when focus time protection is disabled."""
        scorer = MeetingQualityScorer(mock_db)

        context = ScoringContext(
            tenant_id=1,
            start_time=datetime.now(timezone.utc).replace(hour=10),
            end_time=datetime.now(timezone.utc).replace(hour=11),
            participants=["user1"],
            respect_focus_time=False,  # Disabled
            respect_chronotypes=True,
        )

        score = await scorer._score_focus_time_protection(context)

        # Should return max score when disabled
        assert score == 25
