"""Unit tests for RFC 5545 recurrence expansion.

Written RED-first: verifies that expand_recurrence() correctly expands
RRULE strings into concrete datetime occurrences using python-dateutil.
"""

from datetime import datetime, timedelta, timezone

import pytest

from src.core.scheduling.services.recurrence import expand_recurrence


class TestExpandRecurrence:
    """expand_recurrence(rrule, start, end) returns occurrences within [start, end]."""

    def test_weekly_on_mondays_count(self):
        # July 7 2025 is a Monday
        start = datetime(2025, 7, 7, 9, 0, tzinfo=timezone.utc)
        end = datetime(2025, 7, 28, 23, 59, tzinfo=timezone.utc)
        result = expand_recurrence("FREQ=WEEKLY;BYDAY=MO", start, end)
        # Mondays: 7, 14, 21, 28 → 4
        assert len(result) == 4

    def test_daily_with_count_limit(self):
        start = datetime(2025, 8, 1, 9, 0, tzinfo=timezone.utc)
        end = datetime(2025, 8, 31, 23, 59, tzinfo=timezone.utc)
        result = expand_recurrence("FREQ=DAILY;COUNT=5", start, end)
        assert len(result) == 5

    def test_every_two_weeks(self):
        start = datetime(2025, 7, 7, 9, 0, tzinfo=timezone.utc)
        end = datetime(2025, 8, 4, 23, 59, tzinfo=timezone.utc)
        result = expand_recurrence("FREQ=WEEKLY;INTERVAL=2", start, end)
        # July 7, July 21, Aug 4 → 3
        assert len(result) == 3

    def test_monthly_first_of_month(self):
        start = datetime(2025, 1, 1, 9, 0, tzinfo=timezone.utc)
        end = datetime(2025, 6, 30, 23, 59, tzinfo=timezone.utc)
        result = expand_recurrence("FREQ=MONTHLY;BYMONTHDAY=1", start, end)
        assert len(result) == 6  # Jan–Jun

    def test_no_occurrences_before_start(self):
        """All returned datetimes must be >= start."""
        start = datetime(2025, 7, 14, 9, 0, tzinfo=timezone.utc)
        end = datetime(2025, 7, 28, 9, 0, tzinfo=timezone.utc)
        result = expand_recurrence("FREQ=WEEKLY;BYDAY=MO", start, end)
        assert all(dt >= start for dt in result)

    def test_no_occurrences_after_end(self):
        """All returned datetimes must be <= end."""
        start = datetime(2025, 7, 7, 9, 0, tzinfo=timezone.utc)
        end = datetime(2025, 7, 21, 9, 0, tzinfo=timezone.utc)
        result = expand_recurrence("FREQ=WEEKLY;BYDAY=MO", start, end)
        assert all(dt <= end for dt in result)

    def test_empty_range_returns_empty(self):
        """If end < start, return empty list."""
        start = datetime(2025, 7, 14, 9, 0, tzinfo=timezone.utc)
        end = datetime(2025, 7, 7, 9, 0, tzinfo=timezone.utc)
        result = expand_recurrence("FREQ=WEEKLY", start, end)
        assert result == []

    def test_returns_list_of_datetimes(self):
        start = datetime(2025, 7, 7, 9, 0, tzinfo=timezone.utc)
        end = datetime(2025, 7, 21, 23, 59, tzinfo=timezone.utc)
        result = expand_recurrence("FREQ=WEEKLY", start, end)
        assert isinstance(result, list)
        for dt in result:
            assert isinstance(dt, datetime)
