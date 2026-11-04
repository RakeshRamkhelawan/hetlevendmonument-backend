"""Tests for the constraint service."""

from datetime import datetime, time, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.scheduling.models import SchedulingConstraint
from src.core.scheduling.services.constraint_service import ConstraintService, ConstraintViolation


class TestConstraintService:
    """Test suite for ConstraintService."""

    @pytest.fixture
    def service(self):
        """Create a ConstraintService instance with mocked repos."""
        mock_constraint_repo = MagicMock()
        mock_preference_repo = MagicMock()
        return ConstraintService(mock_constraint_repo, mock_preference_repo)

    @pytest.fixture
    def sample_constraint(self):
        """Create a sample scheduling constraint."""
        constraint = MagicMock(spec=SchedulingConstraint)
        constraint.constraint_type = "blocked_time"
        constraint.is_hard = True
        constraint.parameters = {
            "start_time": "2026-03-20T10:00:00",
            "end_time": "2026-03-20T11:00:00",
            "message": "Blocked for focus time",
        }
        return constraint

    @pytest.mark.asyncio
    async def test_check_constraints_no_violations(self, service):
        """Test checking constraints with no violations."""
        # Mock preferences
        mock_prefs = MagicMock()
        mock_prefs.working_hours_start = time(9, 0)
        mock_prefs.working_hours_end = time(17, 0)
        service._preference_repo.get_by_user = AsyncMock(return_value=mock_prefs)

        # Mock constraints
        service._constraint_repo.list_by_user = AsyncMock(return_value=[])

        start_time = datetime(2026, 3, 20, 14, 0, tzinfo=timezone.utc)
        end_time = start_time + timedelta(hours=1)

        result = await service.check_constraints(1, "user_1", start_time, end_time)

        assert result.is_valid is True
        assert len(result.violations) == 0
        assert result.total_penalty == 0.0

    @pytest.mark.asyncio
    async def test_check_constraints_outside_working_hours(self, service):
        """Test violation for time outside working hours."""
        mock_prefs = MagicMock()
        mock_prefs.working_hours_start = time(9, 0)
        mock_prefs.working_hours_end = time(17, 0)
        service._preference_repo.get_by_user = AsyncMock(return_value=mock_prefs)
        service._constraint_repo.list_by_user = AsyncMock(return_value=[])

        # Evening time (outside 9-5)
        start_time = datetime(2026, 3, 20, 20, 0, tzinfo=timezone.utc)
        end_time = start_time + timedelta(hours=1)

        result = await service.check_constraints(1, "user_1", start_time, end_time)

        assert result.is_valid is True  # Working hours is soft constraint
        assert len(result.violations) == 1
        assert result.violations[0].constraint_type == "working_hours"
        assert result.violations[0].severity == "soft"

    @pytest.mark.asyncio
    async def test_check_constraints_blocked_time_hard(self, service):
        """Test hard violation for blocked time."""
        mock_prefs = MagicMock()
        mock_prefs.working_hours_start = time(9, 0)
        mock_prefs.working_hours_end = time(17, 0)
        service._preference_repo.get_by_user = AsyncMock(return_value=mock_prefs)

        # Create blocked time constraint
        blocked_constraint = MagicMock(spec=SchedulingConstraint)
        blocked_constraint.constraint_type = "blocked_time"
        blocked_constraint.is_hard = True
        blocked_constraint.parameters = {
            "start_time": "2026-03-20T10:00:00",
            "end_time": "2026-03-20T11:00:00",
            "message": "Focus time",
        }
        service._constraint_repo.list_by_user = AsyncMock(return_value=[blocked_constraint])

        # Time that overlaps with blocked period
        start_time = datetime(2026, 3, 20, 10, 30, tzinfo=timezone.utc)
        end_time = start_time + timedelta(hours=1)

        result = await service.check_constraints(1, "user_1", start_time, end_time)

        assert result.is_valid is False  # Hard constraint violated
        assert len(result.violations) == 1
        assert result.violations[0].constraint_type == "blocked_time"
        assert result.violations[0].severity == "hard"

    @pytest.mark.asyncio
    async def test_validate_constraints_multiple_users(self, service):
        """Test validating constraints for multiple users."""
        mock_prefs = MagicMock()
        mock_prefs.working_hours_start = time(9, 0)
        mock_prefs.working_hours_end = time(17, 0)
        service._preference_repo.get_by_user = AsyncMock(return_value=mock_prefs)
        service._constraint_repo.list_by_user = AsyncMock(return_value=[])

        start_time = datetime(2026, 3, 20, 14, 0, tzinfo=timezone.utc)
        end_time = start_time + timedelta(hours=1)

        results = await service.validate_constraints(1, ["user_1", "user_2"], start_time, end_time)

        assert "user_1" in results
        assert "user_2" in results
        assert results["user_1"]["is_valid"] is True
        assert results["user_2"]["is_valid"] is True

    def test_calculate_constraint_score_no_violations(self, service):
        """Test score calculation with no violations."""
        score = service.calculate_constraint_score([])
        assert score == 1.0

    def test_calculate_constraint_score_with_violations(self, service):
        """Test score calculation with violations."""
        violations = [
            ConstraintViolation(
                constraint_type="test",
                message="Test violation",
                severity="soft",
                penalty=0.3,
            ),
            ConstraintViolation(
                constraint_type="test2",
                message="Test violation 2",
                severity="soft",
                penalty=0.2,
            ),
        ]
        score = service.calculate_constraint_score(violations)
        assert score == 0.5  # 1.0 - 0.3 - 0.2

    def test_calculate_constraint_score_max_penalty(self, service):
        """Test score calculation caps at 0.0."""
        violations = [
            ConstraintViolation(
                constraint_type="test",
                message="Test",
                severity="hard",
                penalty=1.5,  # Exceeds 1.0
            ),
        ]
        score = service.calculate_constraint_score(violations)
        assert score >= 0.0

    @pytest.mark.asyncio
    async def test_check_constraints_max_duration(self, service):
        """Test max duration constraint violation."""
        mock_prefs = MagicMock()
        mock_prefs.working_hours_start = None
        mock_prefs.working_hours_end = None
        service._preference_repo.get_by_user = AsyncMock(return_value=mock_prefs)

        duration_constraint = MagicMock(spec=SchedulingConstraint)
        duration_constraint.constraint_type = "max_duration"
        duration_constraint.is_hard = False
        duration_constraint.parameters = {"max_minutes": 60}
        service._constraint_repo.list_by_user = AsyncMock(return_value=[duration_constraint])

        # 2 hour meeting (exceeds 60 min)
        start_time = datetime(2026, 3, 20, 10, 0, tzinfo=timezone.utc)
        end_time = start_time + timedelta(hours=2)

        result = await service.check_constraints(1, "user_1", start_time, end_time)

        assert result.is_valid is True  # Soft constraint
        assert any(v.constraint_type == "max_duration" for v in result.violations)

    @pytest.mark.asyncio
    async def test_check_constraints_min_duration(self, service):
        """Test min duration constraint violation."""
        mock_prefs = MagicMock()
        mock_prefs.working_hours_start = None
        mock_prefs.working_hours_end = None
        service._preference_repo.get_by_user = AsyncMock(return_value=mock_prefs)

        duration_constraint = MagicMock(spec=SchedulingConstraint)
        duration_constraint.constraint_type = "min_duration"
        duration_constraint.is_hard = False
        duration_constraint.parameters = {"min_minutes": 30}
        service._constraint_repo.list_by_user = AsyncMock(return_value=[duration_constraint])

        # 15 minute meeting (below 30 min)
        start_time = datetime(2026, 3, 20, 10, 0, tzinfo=timezone.utc)
        end_time = start_time + timedelta(minutes=15)

        result = await service.check_constraints(1, "user_1", start_time, end_time)

        assert result.is_valid is True  # Soft constraint
        assert any(v.constraint_type == "min_duration" for v in result.violations)
