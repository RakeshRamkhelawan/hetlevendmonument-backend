"""Tests for the optimization service."""

from datetime import datetime, timedelta, timezone

import pytest

from src.core.scheduling.schemas import SchedulingOption
from src.core.scheduling.services.optimization_service import OptimizationService


class TestOptimizationService:
    """Test suite for OptimizationService."""

    @pytest.fixture
    def service(self):
        """Create an OptimizationService instance."""
        return OptimizationService()

    @pytest.fixture
    def sample_options(self):
        """Create sample scheduling options."""
        base_time = datetime(2026, 3, 20, 9, 0, tzinfo=timezone.utc)
        return [
            SchedulingOption(
                start_time=base_time,
                end_time=base_time + timedelta(hours=1),
                confidence_score=0.5,
                conflicts=[],
            ),
            SchedulingOption(
                start_time=base_time + timedelta(hours=2),
                end_time=base_time + timedelta(hours=3),
                confidence_score=0.5,
                conflicts=["event_1"],
            ),
            SchedulingOption(
                start_time=base_time + timedelta(hours=20),
                end_time=base_time + timedelta(hours=21),
                confidence_score=0.5,
                conflicts=[],
            ),
        ]

    def test_score_options_with_working_hours(self, service, sample_options):
        """Test scoring with working hours alignment."""
        scored = service.score_options(
            sample_options,
            work_start_hour=9,
            work_end_hour=17,
        )

        # Find the 9 AM option (should have high working hours score)
        morning_option = [s for s in scored if s.start_time.hour == 9][0]
        assert morning_option.score_breakdown["working_hours"] == 1.0

        # Find the early morning option (5 AM next day) (should have low working hours score)
        early_option = [s for s in scored if s.start_time.hour == 5][0]
        assert early_option.score_breakdown["working_hours"] == 0.2

    def test_score_options_with_conflicts(self, service):
        """Test scoring applies conflict penalty."""
        base_time = datetime(2026, 3, 20, 10, 0, tzinfo=timezone.utc)
        options = [
            SchedulingOption(
                start_time=base_time,
                end_time=base_time + timedelta(hours=1),
                confidence_score=0.5,
                conflicts=[],
            ),
            SchedulingOption(
                start_time=base_time + timedelta(hours=2),
                end_time=base_time + timedelta(hours=3),
                confidence_score=0.5,
                conflicts=["event_1", "event_2"],
            ),
        ]

        scored = service.score_options(options)

        # Option with more conflicts should have lower participant availability
        no_conflict_pa = scored[0].score_breakdown["participant_availability"]
        with_conflict_pa = scored[1].score_breakdown["participant_availability"]
        assert no_conflict_pa > with_conflict_pa

    def test_score_options_with_duration_match(self, service):
        """Test scoring with preferred duration matching."""
        base_time = datetime(2026, 3, 20, 10, 0, tzinfo=timezone.utc)
        options = [
            SchedulingOption(
                start_time=base_time,
                end_time=base_time + timedelta(minutes=30),
                confidence_score=0.5,
                conflicts=[],
            ),
            SchedulingOption(
                start_time=base_time + timedelta(hours=1),
                end_time=base_time + timedelta(hours=2),
                confidence_score=0.5,
                conflicts=[],
            ),
        ]

        scored = service.score_options(
            options,
            preferred_duration_minutes=30,
        )

        # First option should have better duration match
        assert (
            scored[0].score_breakdown["duration_match"]
            > scored[1].score_breakdown["duration_match"]
        )

    def test_select_best_option(self, service):
        """Test selecting the best option."""
        base_time = datetime(2026, 3, 20, 10, 0, tzinfo=timezone.utc)
        options = [
            SchedulingOption(
                start_time=base_time,
                end_time=base_time + timedelta(hours=1),
                confidence_score=0.9,
                conflicts=[],
            ),
            SchedulingOption(
                start_time=base_time + timedelta(hours=2),
                end_time=base_time + timedelta(hours=3),
                confidence_score=0.5,
                conflicts=["event_1"],
            ),
        ]

        best = service.select_best_option(options)
        assert best is not None
        assert best.confidence_score == 0.9

    def test_select_best_option_empty_list(self, service):
        """Test selecting from empty list returns None."""
        best = service.select_best_option([])
        assert best is None

    def test_select_best_option_min_confidence(self, service):
        """Test selecting with minimum confidence threshold."""
        base_time = datetime(2026, 3, 20, 10, 0, tzinfo=timezone.utc)
        options = [
            SchedulingOption(
                start_time=base_time,
                end_time=base_time + timedelta(hours=1),
                confidence_score=0.4,
                conflicts=[],
            ),
        ]

        # With min_confidence=0.5, should still return the option
        # (falls back to best available)
        best = service.select_best_option(options, min_confidence=0.5)
        assert best is not None
        assert best.confidence_score == 0.4

    def test_filter_by_constraints_time(self, service):
        """Test filtering by time constraints."""
        base_time = datetime(2026, 3, 20, 10, 0, tzinfo=timezone.utc)
        options = [
            SchedulingOption(
                start_time=base_time,
                end_time=base_time + timedelta(hours=1),
                confidence_score=0.5,
                conflicts=[],
            ),
            SchedulingOption(
                start_time=base_time + timedelta(hours=4),
                end_time=base_time + timedelta(hours=5),
                confidence_score=0.5,
                conflicts=[],
            ),
        ]

        filtered = service.filter_by_constraints(
            options,
            min_start_time=base_time + timedelta(hours=2),
        )

        assert len(filtered) == 1
        assert filtered[0].start_time == base_time + timedelta(hours=4)

    def test_filter_by_constraints_exclude_conflicts(self, service):
        """Test filtering to exclude options with conflicts."""
        base_time = datetime(2026, 3, 20, 10, 0, tzinfo=timezone.utc)
        options = [
            SchedulingOption(
                start_time=base_time,
                end_time=base_time + timedelta(hours=1),
                confidence_score=0.5,
                conflicts=[],
            ),
            SchedulingOption(
                start_time=base_time + timedelta(hours=2),
                end_time=base_time + timedelta(hours=3),
                confidence_score=0.5,
                conflicts=["event_1"],
            ),
        ]

        filtered = service.filter_by_constraints(
            options,
            exclude_conflicts=True,
        )

        assert len(filtered) == 1
        assert len(filtered[0].conflicts) == 0

    def test_score_options_returns_sorted(self, service, sample_options):
        """Test that scored options are returned sorted by confidence."""
        scored = service.score_options(sample_options)

        # Should be sorted highest first
        for i in range(len(scored) - 1):
            assert scored[i].confidence_score >= scored[i + 1].confidence_score

    def test_default_weights_sum_to_one(self, service):
        """Test that default weights sum to 1.0."""
        total = sum(service.weights.values())
        assert total == pytest.approx(1.0)
