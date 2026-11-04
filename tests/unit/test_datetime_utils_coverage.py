"""
Comprehensive tests for src/core/shared/datetime_utils.py
Coverage target: 100% of datetime utilities
"""

from datetime import datetime, timedelta, timezone

import pytest

from src.core.shared.datetime_utils import (
    get_utc_now,
    to_utc,
    utc_isoformat,
    utc_now,
    utc_timestamp,
)


class TestUtcNow:
    """Test utc_now function"""

    def test_utc_now_returns_datetime(self):
        """Test utc_now returns datetime object"""
        # Act
        result = utc_now()

        # Assert
        assert isinstance(result, datetime)

    def test_utc_now_has_utc_timezone(self):
        """Test utc_now returns UTC timezone-aware datetime"""
        # Act
        result = utc_now()

        # Assert
        assert result.tzinfo == timezone.utc

    def test_utc_now_is_current_time(self):
        """Test utc_now returns current time"""
        # Arrange
        before = datetime.now(timezone.utc)

        # Act
        result = utc_now()
        after = datetime.now(timezone.utc)

        # Assert
        assert before <= result <= after

    def test_utc_now_multiple_calls_increase(self):
        """Test successive calls to utc_now return increasing times"""
        # Act
        time1 = utc_now()
        time2 = utc_now()

        # Assert
        assert time2 >= time1


class TestUtcTimestamp:
    """Test utc_timestamp function"""

    def test_utc_timestamp_returns_float(self):
        """Test utc_timestamp returns float"""
        # Act
        result = utc_timestamp()

        # Assert
        assert isinstance(result, float)

    def test_utc_timestamp_is_positive(self):
        """Test utc_timestamp returns positive number"""
        # Act
        result = utc_timestamp()

        # Assert
        assert result > 0

    def test_utc_timestamp_matches_datetime(self):
        """Test utc_timestamp matches current UTC datetime"""
        # Arrange
        dt = utc_now()

        # Act
        timestamp = utc_timestamp()

        # Assert - Should be within 1 second of each other
        assert abs(dt.timestamp() - timestamp) < 1.0

    def test_utc_timestamp_increases(self):
        """Test successive calls to utc_timestamp increase"""
        # Act
        ts1 = utc_timestamp()
        ts2 = utc_timestamp()

        # Assert
        assert ts2 >= ts1

    def test_utc_timestamp_can_be_used_for_ids(self):
        """Test utc_timestamp can be used to generate unique IDs"""
        # Act
        task_id = f"task_{int(utc_timestamp())}"

        # Assert
        assert task_id.startswith("task_")
        assert len(task_id) > 5  # "task_" + timestamp digits


class TestUtcIsoformat:
    """Test utc_isoformat function"""

    def test_utc_isoformat_returns_string(self):
        """Test utc_isoformat returns string"""
        # Act
        result = utc_isoformat()

        # Assert
        assert isinstance(result, str)

    def test_utc_isoformat_is_valid_iso(self):
        """Test utc_isoformat returns valid ISO 8601 format"""
        # Act
        result = utc_isoformat()

        # Assert - Should be parseable as ISO datetime
        parsed = datetime.fromisoformat(result)
        assert isinstance(parsed, datetime)

    def test_utc_isoformat_includes_timezone(self):
        """Test utc_isoformat includes timezone info"""
        # Act
        result = utc_isoformat()

        # Assert
        assert "+00:00" in result or "Z" in result or "+0000" in result

    def test_utc_isoformat_matches_current_time(self):
        """Test utc_isoformat represents current time"""
        # Arrange
        before = utc_now()

        # Act
        iso_str = utc_isoformat()
        after = utc_now()

        # Assert
        parsed = datetime.fromisoformat(iso_str)
        assert before <= parsed <= after

    def test_utc_isoformat_contains_date_components(self):
        """Test utc_isoformat contains year-month-day"""
        # Act
        result = utc_isoformat()

        # Assert - Should contain date separators
        assert "-" in result
        assert "T" in result or " " in result  # Date/time separator


class TestToUtc:
    """Test to_utc function"""

    def test_to_utc_with_none_returns_none(self):
        """Test to_utc returns None when input is None"""
        # Act
        result = to_utc(None)

        # Assert
        assert result is None

    def test_to_utc_with_naive_datetime(self):
        """Test to_utc converts naive datetime to UTC"""
        # Arrange
        naive = datetime(2025, 1, 1, 12, 0, 0)

        # Act
        result = to_utc(naive)

        # Assert
        assert result.tzinfo == timezone.utc
        assert result.year == 2025
        assert result.month == 1
        assert result.day == 1
        assert result.hour == 12

    def test_to_utc_naive_assumes_utc(self):
        """Test to_utc assumes naive datetime is already UTC"""
        # Arrange
        naive = datetime(2025, 6, 15, 14, 30, 45)

        # Act
        result = to_utc(naive)

        # Assert
        assert result.hour == 14  # No conversion, just adds tzinfo
        assert result.minute == 30
        assert result.second == 45

    def test_to_utc_with_utc_aware_datetime(self):
        """Test to_utc with already UTC datetime"""
        # Arrange
        utc_aware = datetime(2025, 3, 10, 10, 0, 0, tzinfo=timezone.utc)

        # Act
        result = to_utc(utc_aware)

        # Assert
        assert result.tzinfo == timezone.utc
        assert result == utc_aware

    def test_to_utc_converts_from_other_timezone(self):
        """Test to_utc converts from non-UTC timezone to UTC"""
        # Arrange
        # UTC+5 timezone
        utc_plus_5 = timezone(timedelta(hours=5))
        aware = datetime(2025, 1, 1, 10, 0, 0, tzinfo=utc_plus_5)

        # Act
        result = to_utc(aware)

        # Assert
        assert result.tzinfo == timezone.utc
        # 10:00 UTC+5 = 05:00 UTC
        assert result.hour == 5

    def test_to_utc_converts_from_negative_timezone(self):
        """Test to_utc converts from negative UTC offset"""
        # Arrange
        # UTC-3 timezone
        utc_minus_3 = timezone(timedelta(hours=-3))
        aware = datetime(2025, 1, 1, 10, 0, 0, tzinfo=utc_minus_3)

        # Act
        result = to_utc(aware)

        # Assert
        assert result.tzinfo == timezone.utc
        # 10:00 UTC-3 = 13:00 UTC
        assert result.hour == 13

    def test_to_utc_preserves_microseconds(self):
        """Test to_utc preserves microsecond precision"""
        # Arrange
        naive = datetime(2025, 1, 1, 12, 0, 0, 123456)

        # Act
        result = to_utc(naive)

        # Assert
        assert result.microsecond == 123456

    def test_to_utc_handles_day_boundary(self):
        """Test to_utc correctly handles date changes across timezones"""
        # Arrange
        # 23:00 UTC+2 should become 21:00 UTC (same day)
        utc_plus_2 = timezone(timedelta(hours=2))
        aware = datetime(2025, 6, 15, 23, 0, 0, tzinfo=utc_plus_2)

        # Act
        result = to_utc(aware)

        # Assert
        assert result.day == 15
        assert result.hour == 21


class TestGetUtcNow:
    """Test get_utc_now function (backwards compatibility)"""

    def test_get_utc_now_is_alias_for_utc_now(self):
        """Test get_utc_now is an alias for utc_now"""
        # Assert
        assert get_utc_now is utc_now

    def test_get_utc_now_returns_datetime(self):
        """Test get_utc_now returns datetime object"""
        # Act
        result = get_utc_now()

        # Assert
        assert isinstance(result, datetime)

    def test_get_utc_now_has_utc_timezone(self):
        """Test get_utc_now returns UTC timezone-aware datetime"""
        # Act
        result = get_utc_now()

        # Assert
        assert result.tzinfo == timezone.utc


class TestModuleExports:
    """Test module exports all expected functions"""

    def test_module_exports(self):
        """Test module exports expected functions"""
        # Act
        import src.core.shared.datetime_utils as module

        # Assert
        assert hasattr(module, "utc_now")
        assert hasattr(module, "utc_timestamp")
        assert hasattr(module, "utc_isoformat")
        assert hasattr(module, "to_utc")
        assert hasattr(module, "get_utc_now")

    def test_all_functions_callable(self):
        """Test all exported functions are callable"""
        # Arrange
        import src.core.shared.datetime_utils as module

        # Assert
        assert callable(module.utc_now)
        assert callable(module.utc_timestamp)
        assert callable(module.utc_isoformat)
        assert callable(module.to_utc)
        assert callable(module.get_utc_now)
