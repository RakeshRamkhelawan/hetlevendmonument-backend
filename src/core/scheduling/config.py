"""Configuration for scheduling module.

All settings can be overridden via environment variables.
"""

import os
from datetime import datetime, time, timezone


class SchedulingConfig:
    """Configuration for scheduling core capability."""

    # Date/time validation ranges
    MIN_EVENT_DATE: datetime = datetime(2020, 1, 1, tzinfo=timezone.utc)
    MAX_EVENT_DATE: datetime = datetime(2035, 12, 31, 23, 59, 59, tzinfo=timezone.utc)

    # Default working hours
    DEFAULT_WORKING_HOURS_START: time = time(9, 0)
    DEFAULT_WORKING_HOURS_END: time = time(17, 0)

    # Sync settings
    DEFAULT_SYNC_WINDOW_DAYS: int = 30
    MAX_SYNC_WINDOW_DAYS: int = 365

    # Rate limiting
    OAUTH_RATE_LIMIT_PER_MINUTE: int = 5
    SYNC_RATE_LIMIT_PER_MINUTE: int = 10

    # Retry settings
    MAX_RETRY_ATTEMPTS: int = 3
    RETRY_MIN_WAIT_SECONDS: int = 1
    RETRY_MAX_WAIT_SECONDS: int = 10

    @classmethod
    def from_env(cls) -> "SchedulingConfig":
        """Load configuration from environment variables."""
        config = cls()

        # Override date ranges if specified
        min_date_str = os.getenv("SCHEDULING_MIN_EVENT_DATE")
        if min_date_str:
            config.MIN_EVENT_DATE = datetime.fromisoformat(min_date_str).replace(
                tzinfo=timezone.utc
            )

        max_date_str = os.getenv("SCHEDULING_MAX_EVENT_DATE")
        if max_date_str:
            config.MAX_EVENT_DATE = datetime.fromisoformat(max_date_str).replace(
                tzinfo=timezone.utc
            )

        # Override working hours
        wh_start_str = os.getenv("SCHEDULING_DEFAULT_WORKING_HOURS_START")
        if wh_start_str:
            config.DEFAULT_WORKING_HOURS_START = time.fromisoformat(wh_start_str)

        wh_end_str = os.getenv("SCHEDULING_DEFAULT_WORKING_HOURS_END")
        if wh_end_str:
            config.DEFAULT_WORKING_HOURS_END = time.fromisoformat(wh_end_str)

        # Override sync settings
        sync_window = os.getenv("SCHEDULING_DEFAULT_SYNC_WINDOW_DAYS")
        if sync_window:
            config.DEFAULT_SYNC_WINDOW_DAYS = int(sync_window)

        max_sync_window = os.getenv("SCHEDULING_MAX_SYNC_WINDOW_DAYS")
        if max_sync_window:
            config.MAX_SYNC_WINDOW_DAYS = int(max_sync_window)

        # Override rate limits
        oauth_limit = os.getenv("SCHEDULING_OAUTH_RATE_LIMIT_PER_MINUTE")
        if oauth_limit:
            config.OAUTH_RATE_LIMIT_PER_MINUTE = int(oauth_limit)

        sync_limit = os.getenv("SCHEDULING_SYNC_RATE_LIMIT_PER_MINUTE")
        if sync_limit:
            config.SYNC_RATE_LIMIT_PER_MINUTE = int(sync_limit)

        # Override retry settings
        max_retries = os.getenv("SCHEDULING_MAX_RETRY_ATTEMPTS")
        if max_retries:
            config.MAX_RETRY_ATTEMPTS = int(max_retries)

        retry_min = os.getenv("SCHEDULING_RETRY_MIN_WAIT_SECONDS")
        if retry_min:
            config.RETRY_MIN_WAIT_SECONDS = int(retry_min)

        retry_max = os.getenv("SCHEDULING_RETRY_MAX_WAIT_SECONDS")
        if retry_max:
            config.RETRY_MAX_WAIT_SECONDS = int(retry_max)

        return config


# Global config instance
scheduling_config = SchedulingConfig.from_env()
