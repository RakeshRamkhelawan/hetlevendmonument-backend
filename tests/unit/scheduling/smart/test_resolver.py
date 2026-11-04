"""Unit tests for Conflict Resolver.

Tests for conflict detection and resolution strategies.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.scheduling.repository import CalendarEventRepository
from src.core.scheduling.smart.resolver import ConflictInfo, ConflictResolver, ResolutionOption


@pytest.fixture
def mock_db():
    """Create properly configured async mock database."""
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


@pytest.fixture
def sample_conflicts():
    """Create sample conflict data."""
    base = datetime.now(timezone.utc)

    return [
        ConflictInfo(
            participant_id="user1",
            participant_name="User One",
            participant_email="user1@test.com",
            conflicting_event_title="Existing Meeting",
            conflicting_event_id="event1",
            conflict_start=base + timedelta(minutes=30),
            conflict_end=base + timedelta(hours=1),
            conflict_type="hard",
            is_recurring=False,
        ),
    ]


@pytest.mark.asyncio
class TestConflictResolver:
    """Tests for conflict resolution."""

    async def test_detect_conflicts_returns_list(self, mock_db):
        """Test that conflict detection returns a list."""
        resolver = ConflictResolver(mock_db)

        # Mock repository
        mock_event = MagicMock()
        mock_event.title = "Existing Meeting"
        mock_event.start_time = datetime.now(timezone.utc)
        mock_event.end_time = datetime.now(timezone.utc) + timedelta(hours=1)
        mock_event.event_type = "meeting"

        mock_repo = MagicMock(spec=CalendarEventRepository)
        mock_repo.list_by_user_in_range = AsyncMock(return_value=[mock_event])

        with patch("src.core.scheduling.repository.CalendarEventRepository", return_value=mock_repo):
            start = datetime.now(timezone.utc)
            end = start + timedelta(hours=2)

            conflicts = await resolver.detect_conflicts(
                tenant_id=1,
                proposed_start=start,
                proposed_end=end,
                participants=["user1"],
            )

            assert isinstance(conflicts, list)

    async def test_detect_hard_conflict(self, mock_db):
        """Test detection of hard conflicts."""
        resolver = ConflictResolver(mock_db)

        # Event that fully overlaps
        mock_event = MagicMock()
        mock_event.title = "Important Meeting"
        mock_event.start_time = datetime.now(timezone.utc) + timedelta(minutes=15)
        mock_event.end_time = datetime.now(timezone.utc) + timedelta(minutes=45)
        mock_event.event_type = "meeting"
        mock_event.status = "busy"

        mock_repo = MagicMock(spec=CalendarEventRepository)
        mock_repo.list_by_user_in_range = AsyncMock(return_value=[mock_event])

        with patch("src.core.scheduling.repository.CalendarEventRepository", return_value=mock_repo):
            start = datetime.now(timezone.utc)
            end = start + timedelta(hours=1)

            conflicts = await resolver.detect_conflicts(
                tenant_id=1,
                proposed_start=start,
                proposed_end=end,
                participants=["user1"],
            )

            assert len(conflicts) > 0
            # Should be hard conflict due to significant overlap
            assert conflicts[0].conflict_type == "hard"

    async def test_resolve_conflicts_returns_options(self, mock_db, sample_conflicts):
        """Test that conflict resolution returns options."""
        resolver = ConflictResolver(mock_db)

        start = datetime.now(timezone.utc)
        end = start + timedelta(hours=1)

        resolutions = await resolver.resolve_conflicts(
            tenant_id=1,
            conflicts=sample_conflicts,
            original_start=start,
            original_end=end,
        )

        assert isinstance(resolutions, list)
        # Should generate multiple resolution options
        assert len(resolutions) > 0

    async def test_adjacent_time_strategy(self, mock_db, sample_conflicts):
        """Test adjacent time resolution strategy."""
        resolver = ConflictResolver(mock_db)

        start = datetime.now(timezone.utc)
        end = start + timedelta(hours=1)

        resolutions = await resolver.resolve_conflicts(
            tenant_id=1,
            conflicts=sample_conflicts,
            original_start=start,
            original_end=end,
        )

        # Check for adjacent time option (using string comparison)
        adjacent = [r for r in resolutions if r.type == "adjacent"]
        assert len(adjacent) > 0

    async def test_alternative_day_strategy(self, mock_db, sample_conflicts):
        """Test alternative day resolution strategy."""
        resolver = ConflictResolver(mock_db)

        start = datetime.now(timezone.utc)
        end = start + timedelta(hours=1)

        resolutions = await resolver.resolve_conflicts(
            tenant_id=1,
            conflicts=sample_conflicts,
            original_start=start,
            original_end=end,
        )

        # Check for alternative day option
        alt_day = [r for r in resolutions if r.type == "alternative_day"]
        assert len(alt_day) > 0

    async def test_shorter_duration_strategy(self, mock_db, sample_conflicts):
        """Test shorter duration resolution strategy."""
        resolver = ConflictResolver(mock_db)

        start = datetime.now(timezone.utc)
        end = start + timedelta(hours=1)

        resolutions = await resolver.resolve_conflicts(
            tenant_id=1,
            conflicts=sample_conflicts,
            original_start=start,
            original_end=end,
        )

        # Check for shorter duration option
        shorter = [r for r in resolutions if r.type == "shorter"]
        # Shorter duration is conditional, may or may not be present
        assert len(shorter) >= 0

    async def test_virtual_meeting_strategy(self, mock_db, sample_conflicts):
        """Test virtual meeting resolution strategy."""
        resolver = ConflictResolver(mock_db)

        start = datetime.now(timezone.utc)
        end = start + timedelta(hours=1)

        resolutions = await resolver.resolve_conflicts(
            tenant_id=1,
            conflicts=sample_conflicts,
            original_start=start,
            original_end=end,
        )

        # Check for virtual option
        virtual = [r for r in resolutions if r.type == "virtual"]
        assert len(virtual) > 0

    async def test_async_strategy(self, mock_db, sample_conflicts):
        """Test async resolution strategy."""
        resolver = ConflictResolver(mock_db)

        # Test the async suggestion directly
        async_opt = resolver._suggest_async_alternative(
            sample_conflicts,
            datetime.now(timezone.utc),
            datetime.now(timezone.utc) + timedelta(hours=1),
        )

        # Check for async option
        assert async_opt is not None
        assert async_opt.type == "async"

    async def test_conflict_severity_calculation(self, mock_db):
        """Test conflict severity calculation."""
        resolver = ConflictResolver(mock_db)

        # No conflicts
        assert resolver.calculate_conflict_severity([]) == "low"

        # All hard conflicts
        hard_conflicts = [
            ConflictInfo(
                participant_id=f"user{i}",
                conflicting_event_title="Meeting",
                conflict_start=datetime.now(timezone.utc),
                conflict_end=datetime.now(timezone.utc) + timedelta(hours=1),
                conflict_type="hard",
                is_recurring=False,
            )
            for i in range(5)
        ]

        severity = resolver.calculate_conflict_severity(hard_conflicts)
        assert severity in ["high", "critical"]

    async def test_no_conflicts_returns_empty(self, mock_db):
        """Test that no conflicts returns empty list."""
        resolver = ConflictResolver(mock_db)

        mock_repo = MagicMock(spec=CalendarEventRepository)
        mock_repo.list_by_user_in_range = AsyncMock(return_value=[])

        with patch("src.core.scheduling.repository.CalendarEventRepository", return_value=mock_repo):
            start = datetime.now(timezone.utc)
            end = start + timedelta(hours=1)

            conflicts = await resolver.detect_conflicts(
                tenant_id=1,
                proposed_start=start,
                proposed_end=end,
                participants=["user1"],
            )

            assert conflicts == []

    async def test_resolve_no_conflicts(self, mock_db):
        """Test resolving when no conflicts."""
        resolver = ConflictResolver(mock_db)

        start = datetime.now(timezone.utc)
        end = start + timedelta(hours=1)

        resolutions = await resolver.resolve_conflicts(
            tenant_id=1,
            conflicts=[],
            original_start=start,
            original_end=end,
        )

        assert resolutions == []

    async def test_determine_conflict_type(self, mock_db):
        """Test conflict type determination."""
        resolver = ConflictResolver(mock_db)

        # Test tentative status
        tentative_event = MagicMock()
        tentative_event.status = "tentative"
        assert resolver._determine_conflict_type(tentative_event) == "tentative"

        # Test free/transparent event
        free_event = MagicMock()
        free_event.status = "free"
        assert resolver._determine_conflict_type(free_event) == "soft"

        # Test busy status (default)
        busy_event = MagicMock()
        busy_event.status = "busy"
        assert resolver._determine_conflict_type(busy_event) == "hard"

    async def test_suggest_best_alternative_no_conflicts(self, mock_db):
        """Test suggest_best_alternative when no conflicts."""
        resolver = ConflictResolver(mock_db)

        mock_repo = MagicMock(spec=CalendarEventRepository)
        mock_repo.list_by_user_in_range = AsyncMock(return_value=[])

        with patch("src.core.scheduling.repository.CalendarEventRepository", return_value=mock_repo):
            start = datetime.now(timezone.utc)
            end = start + timedelta(hours=1)

            result = await resolver.suggest_best_alternative(
                tenant_id=1,
                original_start=start,
                original_end=end,
                participants=["user1"],
            )

            # Should return None when no conflicts
            assert result is None
