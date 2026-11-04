"""Unit tests for scheduling data models."""

from datetime import datetime, timezone

import pytest


class TestCalendarEventModel:
    """CalendarEvent ORM model unit tests."""

    def test_validate_priority_valid(self):
        from src.core.scheduling.models import CalendarEvent

        event = CalendarEvent.__new__(CalendarEvent)
        result = event._validate_priority("priority", 5)
        assert result == 5

    def test_validate_priority_boundaries(self):
        from src.core.scheduling.models import CalendarEvent

        event = CalendarEvent.__new__(CalendarEvent)
        assert event._validate_priority("priority", 1) == 1
        assert event._validate_priority("priority", 9) == 9

    def test_validate_priority_out_of_range(self):
        from src.core.scheduling.models import CalendarEvent

        event = CalendarEvent.__new__(CalendarEvent)
        with pytest.raises(ValueError, match="Priority must be between 1 and 9"):
            event._validate_priority("priority", 0)
        with pytest.raises(ValueError, match="Priority must be between 1 and 9"):
            event._validate_priority("priority", 10)

    def test_validate_time_naive_becomes_utc(self):
        from src.core.scheduling.models import CalendarEvent

        event = CalendarEvent.__new__(CalendarEvent)
        naive = datetime(2024, 6, 15, 10, 0)
        result = event._validate_time_range("start_time", naive)
        assert result.tzinfo is not None

    def test_validate_time_out_of_range(self):
        from src.core.scheduling.models import CalendarEvent

        event = CalendarEvent.__new__(CalendarEvent)
        too_early = datetime(2019, 1, 1, tzinfo=timezone.utc)
        with pytest.raises(ValueError, match="outside valid range"):
            event._validate_time_range("start_time", too_early)

        too_late = datetime(2036, 1, 1, tzinfo=timezone.utc)
        with pytest.raises(ValueError, match="outside valid range"):
            event._validate_time_range("start_time", too_late)

    def test_validate_time_none_passes(self):
        from src.core.scheduling.models import CalendarEvent

        event = CalendarEvent.__new__(CalendarEvent)
        assert event._validate_time_range("start_time", None) is None

    def test_generate_uuid_format(self):
        from src.core.scheduling.models import _generate_uuid

        uid = _generate_uuid()
        assert len(uid) == 36
        assert uid.count("-") == 4


class TestTableNames:
    """Verify table names match the migration."""

    def test_calendar_events_tablename(self):
        from src.core.scheduling.models import CalendarEvent

        assert CalendarEvent.__tablename__ == "scheduling_calendar_events"

    def test_time_blocks_tablename(self):
        from src.core.scheduling.models import TimeBlock

        assert TimeBlock.__tablename__ == "scheduling_time_blocks"

    def test_constraints_tablename(self):
        from src.core.scheduling.models import SchedulingConstraint

        assert SchedulingConstraint.__tablename__ == "scheduling_constraints"

    def test_preferences_tablename(self):
        from src.core.scheduling.models import SchedulingPreference

        assert SchedulingPreference.__tablename__ == "scheduling_preferences"
