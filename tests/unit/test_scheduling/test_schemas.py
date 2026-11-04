"""Unit tests for scheduling Pydantic schemas."""

from datetime import datetime, timedelta, timezone

import pytest

from src.core.scheduling.schemas import (
    CalendarEventCreate,
    CalendarEventResponse,
    CalendarEventUpdate,
    ConflictInfo,
    PreferenceUpdate,
    RecurrencePattern,
    SchedulingOption,
    SchedulingRequest,
    SchedulingResult,
    TimeBlockCreate,
)

# ---------------------------------------------------------------------------
# RecurrencePattern — from_rrule_string (RED — requires implementation)
# ---------------------------------------------------------------------------


class TestRecurrencePatternParsing:
    """RecurrencePattern.from_rrule_string() must parse RFC 5545 RRULE strings."""

    def test_from_rrule_string_simple_weekly(self):
        rp = RecurrencePattern.from_rrule_string("FREQ=WEEKLY")
        assert rp.freq == "WEEKLY"
        assert rp.interval == 1

    def test_from_rrule_string_with_interval(self):
        rp = RecurrencePattern.from_rrule_string("FREQ=DAILY;INTERVAL=3")
        assert rp.freq == "DAILY"
        assert rp.interval == 3

    def test_from_rrule_string_with_count(self):
        rp = RecurrencePattern.from_rrule_string("FREQ=MONTHLY;COUNT=5")
        assert rp.freq == "MONTHLY"
        assert rp.count == 5

    def test_from_rrule_string_with_byday(self):
        rp = RecurrencePattern.from_rrule_string("FREQ=WEEKLY;BYDAY=MO,WE,FR")
        assert rp.byday == ["MO", "WE", "FR"]

    def test_from_rrule_string_with_bymonthday(self):
        rp = RecurrencePattern.from_rrule_string("FREQ=MONTHLY;BYMONTHDAY=1,15")
        assert rp.bymonthday == [1, 15]

    def test_from_rrule_string_round_trip(self):
        """to_rrule_string() output must be parseable back to an equivalent object."""
        original = RecurrencePattern(freq="WEEKLY", interval=2, byday=["TU", "TH"])
        parsed = RecurrencePattern.from_rrule_string(original.to_rrule_string())
        assert parsed.freq == original.freq
        assert parsed.interval == original.interval
        assert parsed.byday == original.byday

    def test_from_rrule_string_missing_freq_raises(self):
        with pytest.raises(ValueError, match="FREQ"):
            RecurrencePattern.from_rrule_string("INTERVAL=2;COUNT=5")

    def test_from_rrule_string_invalid_freq_raises(self):
        """HOURLY is not in the supported subset."""
        with pytest.raises(Exception):
            RecurrencePattern.from_rrule_string("FREQ=HOURLY")

    def test_from_rrule_string_accepts_rrule_prefix(self):
        """Some iCal exports include the 'RRULE:' property prefix."""
        rp = RecurrencePattern.from_rrule_string("RRULE:FREQ=DAILY;COUNT=3")
        assert rp.freq == "DAILY"
        assert rp.count == 3


# ---------------------------------------------------------------------------
# RecurrencePattern — BYDAY validation (RED)
# ---------------------------------------------------------------------------


class TestRecurrencePatternBydayValidation:
    """BYDAY values must be valid RFC 5545 weekday codes."""

    def test_valid_byday_all_days(self):
        rp = RecurrencePattern(freq="WEEKLY", byday=["MO", "TU", "WE", "TH", "FR", "SA", "SU"])
        assert len(rp.byday) == 7  # type: ignore[arg-type]

    def test_invalid_byday_full_name_raises(self):
        with pytest.raises(Exception):
            RecurrencePattern(freq="WEEKLY", byday=["MONDAY"])

    def test_invalid_byday_lowercase_raises(self):
        with pytest.raises(Exception):
            RecurrencePattern(freq="WEEKLY", byday=["mo"])

    def test_ordinal_byday_positive(self):
        """'2MO' = second Monday of month — valid in MONTHLY context."""
        rp = RecurrencePattern(freq="MONTHLY", byday=["2MO"])
        assert rp.byday == ["2MO"]

    def test_ordinal_byday_negative(self):
        """-1FR = last Friday of month."""
        rp = RecurrencePattern(freq="MONTHLY", byday=["-1FR"])
        assert rp.byday == ["-1FR"]

    def test_invalid_ordinal_byday_raises(self):
        with pytest.raises(Exception):
            RecurrencePattern(freq="MONTHLY", byday=["6MO"])  # ordinal > 5 invalid


# ---------------------------------------------------------------------------
# CalendarEventCreate — recurrence field (RED)
# ---------------------------------------------------------------------------


class TestCalendarEventCreateRecurrence:
    """CalendarEventCreate must accept a RecurrencePattern object."""

    def test_create_with_recurrence_object(self):
        now = datetime.now(tz=timezone.utc)
        rp = RecurrencePattern(freq="WEEKLY", byday=["MO"])
        ev = CalendarEventCreate(
            title="Weekly sync",
            start_time=now,
            end_time=now + timedelta(hours=1),
            recurrence=rp,
        )
        assert ev.recurrence is not None
        assert ev.recurrence.freq == "WEEKLY"

    def test_create_without_recurrence_defaults_none(self):
        now = datetime.now(tz=timezone.utc)
        ev = CalendarEventCreate(
            title="One-off",
            start_time=now,
            end_time=now + timedelta(hours=1),
        )
        assert ev.recurrence is None

    def test_recurrence_rrule_string_accessible(self):
        """The RRULE string must be derivable from the recurrence object."""
        now = datetime.now(tz=timezone.utc)
        rp = RecurrencePattern(freq="DAILY", interval=2)
        ev = CalendarEventCreate(
            title="Daily briefing",
            start_time=now,
            end_time=now + timedelta(hours=1),
            recurrence=rp,
        )
        rrule = ev.recurrence.to_rrule_string()  # type: ignore[union-attr]
        assert "FREQ=DAILY" in rrule
        assert "INTERVAL=2" in rrule


# ---------------------------------------------------------------------------
# TimeBlockCreate — recurrence field (RED)
# ---------------------------------------------------------------------------


class TestTimeBlockCreateRecurrence:
    """TimeBlockCreate must accept a RecurrencePattern object."""

    def test_create_with_recurrence(self):
        now = datetime.now(tz=timezone.utc)
        rp = RecurrencePattern(freq="DAILY")
        tb = TimeBlockCreate(
            start_time=now,
            end_time=now + timedelta(hours=2),
            recurrence=rp,
        )
        assert tb.recurrence is not None
        assert tb.recurrence.freq == "DAILY"

    def test_create_without_recurrence(self):
        now = datetime.now(tz=timezone.utc)
        tb = TimeBlockCreate(
            start_time=now,
            end_time=now + timedelta(hours=2),
        )
        assert tb.recurrence is None


class TestRecurrencePattern:
    """RecurrencePattern schema tests."""

    def test_to_rrule_string_simple(self):
        rp = RecurrencePattern(freq="WEEKLY")
        assert rp.to_rrule_string() == "FREQ=WEEKLY"

    def test_to_rrule_string_with_interval(self):
        rp = RecurrencePattern(freq="DAILY", interval=2)
        assert rp.to_rrule_string() == "FREQ=DAILY;INTERVAL=2"

    def test_to_rrule_string_with_count(self):
        rp = RecurrencePattern(freq="MONTHLY", count=10)
        assert rp.to_rrule_string() == "FREQ=MONTHLY;COUNT=10"

    def test_to_rrule_string_with_byday(self):
        rp = RecurrencePattern(freq="WEEKLY", byday=["MO", "WE", "FR"])
        assert "BYDAY=MO,WE,FR" in rp.to_rrule_string()

    def test_to_rrule_string_with_until(self):
        until = datetime(2025, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        rp = RecurrencePattern(freq="DAILY", until=until)
        result = rp.to_rrule_string()
        assert "UNTIL=20251231T235959Z" in result

    def test_invalid_interval(self):
        with pytest.raises(Exception):
            RecurrencePattern(freq="DAILY", interval=0)


class TestSchedulingRequest:
    """SchedulingRequest schema tests."""

    def _base_data(self):
        now = datetime.now(tz=timezone.utc)
        return {
            "title": "Team Standup",
            "duration_minutes": 30,
            "participants": ["user-1", "user-2"],
            "earliest_start": now,
            "latest_end": now + timedelta(hours=8),
        }

    def test_valid_request(self):
        req = SchedulingRequest(**self._base_data())
        assert req.title == "Team Standup"
        assert req.duration_minutes == 30
        assert req.priority == 3  # default

    def test_end_before_start_raises(self):
        data = self._base_data()
        data["latest_end"] = data["earliest_start"] - timedelta(hours=1)
        with pytest.raises(Exception, match="latest_end must be after earliest_start"):
            SchedulingRequest(**data)

    def test_duration_too_short(self):
        data = self._base_data()
        data["duration_minutes"] = 4
        with pytest.raises(Exception):
            SchedulingRequest(**data)

    def test_duration_too_long(self):
        data = self._base_data()
        data["duration_minutes"] = 481
        with pytest.raises(Exception):
            SchedulingRequest(**data)

    def test_empty_participants_raises(self):
        data = self._base_data()
        data["participants"] = []
        with pytest.raises(Exception):
            SchedulingRequest(**data)

    def test_priority_boundaries(self):
        data = self._base_data()
        data["priority"] = 1
        SchedulingRequest(**data)
        data["priority"] = 9
        SchedulingRequest(**data)

    def test_priority_out_of_range(self):
        data = self._base_data()
        data["priority"] = 0
        with pytest.raises(Exception):
            SchedulingRequest(**data)


class TestCalendarEventCreate:
    """CalendarEventCreate schema tests."""

    def test_valid_create(self):
        now = datetime.now(tz=timezone.utc)
        data = CalendarEventCreate(
            title="Review",
            start_time=now,
            end_time=now + timedelta(hours=1),
        )
        assert data.event_type == "meeting"
        assert data.priority == 3

    def test_end_before_start_raises(self):
        now = datetime.now(tz=timezone.utc)
        with pytest.raises(Exception, match="end_time must be after start_time"):
            CalendarEventCreate(
                title="Bad",
                start_time=now,
                end_time=now - timedelta(hours=1),
            )


class TestCalendarEventUpdate:
    """CalendarEventUpdate schema tests."""

    def test_partial_update(self):
        data = CalendarEventUpdate(title="New title")
        dumped = data.model_dump(exclude_unset=True)
        assert dumped == {"title": "New title"}

    def test_empty_update(self):
        data = CalendarEventUpdate()
        dumped = data.model_dump(exclude_unset=True)
        assert dumped == {}


class TestTimeBlockCreate:
    """TimeBlockCreate schema tests."""

    def test_valid_create(self):
        now = datetime.now(tz=timezone.utc)
        tb = TimeBlockCreate(
            start_time=now,
            end_time=now + timedelta(hours=2),
        )
        assert tb.is_hard_block is True
        assert tb.block_type == "focus_time"

    def test_end_before_start_raises(self):
        now = datetime.now(tz=timezone.utc)
        with pytest.raises(Exception, match="end_time must be after start_time"):
            TimeBlockCreate(
                start_time=now,
                end_time=now - timedelta(hours=1),
            )


class TestSchedulingOption:
    """SchedulingOption schema tests."""

    def test_score_bounds(self):
        now = datetime.now(tz=timezone.utc)
        opt = SchedulingOption(
            start_time=now,
            end_time=now + timedelta(hours=1),
            confidence_score=0.85,
        )
        assert opt.confidence_score == 0.85

    def test_score_out_of_range(self):
        now = datetime.now(tz=timezone.utc)
        with pytest.raises(Exception):
            SchedulingOption(
                start_time=now,
                end_time=now + timedelta(hours=1),
                confidence_score=1.5,
            )


class TestSchedulingResult:
    """SchedulingResult schema tests."""

    def test_failure_result(self):
        result = SchedulingResult(
            success=False,
            message="No slots",
        )
        assert result.event_id is None
        assert result.alternatives == []

    def test_success_result(self):
        now = datetime.now(tz=timezone.utc)
        opt = SchedulingOption(
            start_time=now,
            end_time=now + timedelta(hours=1),
            confidence_score=0.9,
        )
        result = SchedulingResult(
            success=True,
            event_id="abc-123",
            selected_option=opt,
            message="OK",
        )
        assert result.success is True
        assert result.event_id == "abc-123"


class TestConflictInfo:
    """ConflictInfo schema tests."""

    def test_hard_severity(self):
        now = datetime.now(tz=timezone.utc)
        ci = ConflictInfo(
            event_id="ev-1",
            title="Existing",
            start_time=now,
            end_time=now + timedelta(hours=1),
            severity="hard",
        )
        assert ci.severity == "hard"

    def test_invalid_severity(self):
        now = datetime.now(tz=timezone.utc)
        with pytest.raises(Exception):
            ConflictInfo(
                event_id="ev-1",
                title="Bad",
                start_time=now,
                end_time=now + timedelta(hours=1),
                severity="unknown",
            )


class TestPreferenceUpdate:
    """PreferenceUpdate schema tests."""

    def test_valid_preferences(self):
        p = PreferenceUpdate(
            timezone_name="Europe/Amsterdam",
            working_hours_start="09:00",
            working_hours_end="17:30",
            preferred_duration_minutes=45,
            buffer_minutes=10,
        )
        assert p.timezone_name == "Europe/Amsterdam"

    def test_buffer_minutes_bounds(self):
        with pytest.raises(Exception):
            PreferenceUpdate(buffer_minutes=61)

    def test_duration_bounds(self):
        with pytest.raises(Exception):
            PreferenceUpdate(preferred_duration_minutes=4)
