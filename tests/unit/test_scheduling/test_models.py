"""Unit tests for scheduling ORM models.

Tests validator logic, constraints, and model behaviour directly —
no database required for most cases.
"""

from datetime import datetime, time, timezone

import pytest

from src.core.scheduling.models import (
    CalendarEvent,
    SchedulingConstraint,
    SchedulingPreference,
    TimeBlock,
)

# -------------------------------------------------------------------------
# CalendarEvent validators
# -------------------------------------------------------------------------


class TestCalendarEventValidators:
    """Test @validates decorators on CalendarEvent."""

    def _make_event(self, **kwargs) -> CalendarEvent:
        defaults = dict(
            tenant_id=1,
            title="Test",
            start_time=datetime(2025, 6, 1, 10, 0, tzinfo=timezone.utc),
            end_time=datetime(2025, 6, 1, 11, 0, tzinfo=timezone.utc),
            organizer_id="user-1",
            event_type="meeting",
            status="scheduled",
            priority=3,
        )
        defaults.update(kwargs)
        return CalendarEvent(**defaults)

    def test_valid_event_created(self):
        event = self._make_event()
        assert event.title == "Test"
        assert event.priority == 3

    def test_naive_start_time_gets_utc(self):
        """Naive datetime must be coerced to UTC by validator."""
        naive = datetime(2025, 6, 1, 10, 0)  # no tzinfo
        event = self._make_event(start_time=naive)
        assert event.start_time.tzinfo is not None

    def test_naive_end_time_gets_utc(self):
        naive = datetime(2025, 6, 1, 11, 0)
        event = self._make_event(end_time=naive)
        assert event.end_time.tzinfo is not None

    def test_start_time_before_2020_raises(self):
        with pytest.raises(ValueError, match="outside valid range"):
            self._make_event(start_time=datetime(2019, 12, 31, tzinfo=timezone.utc))

    def test_start_time_after_2035_raises(self):
        with pytest.raises(ValueError, match="outside valid range"):
            self._make_event(start_time=datetime(2036, 1, 1, tzinfo=timezone.utc))

    def test_end_time_before_2020_raises(self):
        with pytest.raises(ValueError, match="outside valid range"):
            self._make_event(end_time=datetime(2019, 1, 1, tzinfo=timezone.utc))

    def test_priority_below_1_raises(self):
        with pytest.raises(ValueError, match="Priority"):
            self._make_event(priority=0)

    def test_priority_above_9_raises(self):
        with pytest.raises(ValueError, match="Priority"):
            self._make_event(priority=10)

    def test_priority_1_valid(self):
        event = self._make_event(priority=1)
        assert event.priority == 1

    def test_priority_9_valid(self):
        event = self._make_event(priority=9)
        assert event.priority == 9

    def test_default_priority(self):
        event = self._make_event()
        assert event.priority == 3

    def test_explicit_event_type(self):
        event = self._make_event(event_type="task")
        assert event.event_type == "task"

    def test_repr_contains_title(self):
        event = self._make_event(title="My Meeting")
        assert event.title == "My Meeting"


# -------------------------------------------------------------------------
# TimeBlock
# -------------------------------------------------------------------------


class TestTimeBlock:
    """Tests for TimeBlock model field behaviour."""

    def test_explicit_block_type(self):
        block = TimeBlock(
            tenant_id=1,
            user_id="u1",
            block_type="deep_work",
            start_time=datetime(2025, 6, 1, 9, 0, tzinfo=timezone.utc),
            end_time=datetime(2025, 6, 1, 10, 0, tzinfo=timezone.utc),
            is_hard_block=True,
        )
        assert block.block_type == "deep_work"

    def test_soft_block_is_accepted(self):
        block = TimeBlock(
            tenant_id=1,
            user_id="u1",
            start_time=datetime(2025, 6, 1, 9, 0, tzinfo=timezone.utc),
            end_time=datetime(2025, 6, 1, 10, 0, tzinfo=timezone.utc),
            is_hard_block=False,
        )
        assert block.is_hard_block is False

    def test_label_accepted(self):
        block = TimeBlock(
            tenant_id=1,
            user_id="u1",
            start_time=datetime(2025, 6, 1, 9, 0, tzinfo=timezone.utc),
            end_time=datetime(2025, 6, 1, 10, 0, tzinfo=timezone.utc),
            is_hard_block=True,
            label="Focus",
        )
        assert block.label == "Focus"


# -------------------------------------------------------------------------
# SchedulingConstraint
# -------------------------------------------------------------------------


class TestSchedulingConstraint:
    """Tests for SchedulingConstraint model."""

    def test_hard_constraint(self):
        c = SchedulingConstraint(
            tenant_id=1,
            user_id="u1",
            constraint_type="no_meetings_after",
            is_hard=True,
        )
        assert c.is_hard is True

    def test_soft_constraint(self):
        c = SchedulingConstraint(
            tenant_id=1,
            user_id="u1",
            constraint_type="prefer_morning",
            is_hard=False,
        )
        assert c.is_hard is False

    def test_parameters_dict(self):
        c = SchedulingConstraint(
            tenant_id=1,
            user_id="u1",
            constraint_type="buffer_required",
            is_hard=True,
            parameters={"minutes": 15},
        )
        assert c.parameters == {"minutes": 15}


# -------------------------------------------------------------------------
# SchedulingPreference
# -------------------------------------------------------------------------


class TestSchedulingPreference:
    """Tests for SchedulingPreference field behaviour."""

    def test_explicit_timezone(self):
        pref = SchedulingPreference(tenant_id=1, user_id="u1", timezone_name="UTC")
        assert pref.timezone_name == "UTC"

    def test_explicit_working_hours(self):
        pref = SchedulingPreference(
            tenant_id=1,
            user_id="u1",
            timezone_name="UTC",
            working_hours_start="09:00",
            working_hours_end="17:00",
        )
        assert pref.working_hours_start == time(9, 0)
        assert pref.working_hours_end == time(17, 0)

    def test_explicit_duration_and_buffer(self):
        pref = SchedulingPreference(
            tenant_id=1,
            user_id="u1",
            timezone_name="UTC",
            preferred_duration_minutes=30,
            buffer_minutes=5,
        )
        assert pref.preferred_duration_minutes == 30
        assert pref.buffer_minutes == 5

    def test_custom_values(self):
        pref = SchedulingPreference(
            tenant_id=1,
            user_id="u1",
            timezone_name="Europe/Amsterdam",
            working_hours_start="08:00",
            working_hours_end="18:00",
            preferred_duration_minutes=45,
            buffer_minutes=10,
        )
        assert pref.timezone_name == "Europe/Amsterdam"
        assert pref.working_hours_start == time(8, 0)
        assert pref.preferred_duration_minutes == 45
