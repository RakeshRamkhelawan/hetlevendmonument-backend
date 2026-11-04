"""
Centralized datetime utilities for timezone-aware datetime handling.

This module provides timezone-aware datetime functions to replace deprecated
datetime.now(timezone.utc) usage throughout the codebase.

Python 3.12+ deprecates datetime.now(timezone.utc) in favor of datetime.now(timezone.utc)
for explicit timezone-aware datetime handling.

Usage:
    from src.core.shared.datetime_utils import utc_now, utc_timestamp

    # Instead of datetime.now(timezone.utc)
    now = utc_now()

    # For timestamp-based IDs
    task_id = f"task_{utc_timestamp()}"
"""

from datetime import datetime, timezone
from typing import Optional


def utc_now() -> datetime:
    """
    Get the current UTC datetime with timezone info.

    This is the recommended replacement for datetime.now(timezone.utc) which is
    deprecated in Python 3.12+.

    Returns:
        datetime: Current UTC time with tzinfo=timezone.utc

    Example:
        >>> from core.shared.datetime_utils import utc_now
        >>> now = utc_now()
        >>> now.tzinfo
        datetime.timezone.utc
    """
    return datetime.now(timezone.utc)


def utc_timestamp() -> float:
    """
    Get the current UTC timestamp as a float.

    Useful for generating unique IDs or measuring time intervals.

    Returns:
        float: Current UTC timestamp

    Example:
        >>> from core.shared.datetime_utils import utc_timestamp
        >>> task_id = f"task_{int(utc_timestamp())}"
    """
    return datetime.now(timezone.utc).timestamp()


def utc_isoformat() -> str:
    """
    Get the current UTC datetime as an ISO format string.

    Returns:
        str: Current UTC time in ISO 8601 format

    Example:
        >>> from core.shared.datetime_utils import utc_isoformat
        >>> timestamp = utc_isoformat()
        '2025-11-26T18:30:00.123456+00:00'
    """
    return datetime.now(timezone.utc).isoformat()


def to_utc(dt: datetime | None) -> datetime | None:
    """
    Convert a datetime to UTC timezone-aware datetime.

    If the datetime is naive (no tzinfo), it's assumed to be UTC.
    If the datetime already has timezone info, it's converted to UTC.

    Args:
        dt: The datetime to convert, or None

    Returns:
        datetime with tzinfo=timezone.utc, or None if input is None

    Example:
        >>> from datetime import datetime
        >>> from core.shared.datetime_utils import to_utc
        >>> naive = datetime(2025, 1, 1, 12, 0, 0)
        >>> aware = to_utc(naive)
        >>> aware.tzinfo
        datetime.timezone.utc
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        # Naive datetime - assume UTC
        return dt.replace(tzinfo=timezone.utc)
    # Convert to UTC
    return dt.astimezone(timezone.utc)


# Backwards compatibility alias (matches the deprecated function name pattern)
# Use sparingly - prefer utc_now() for new code
get_utc_now = utc_now
