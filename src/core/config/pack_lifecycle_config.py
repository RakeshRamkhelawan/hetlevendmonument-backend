"""
Pack Lifecycle Configuration

Configuration settings for pack deactivation and lifecycle management.
Part of Paperclip Pipeline Integration - Plan 4, Task 3.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class PackLifecycleConfig(BaseSettings):
    """
    Configuration for pack lifecycle management.

    Controls thresholds for deactivation warnings and auto-deactivation behavior.
    All settings can be overridden via environment variables.
    """

    # Number of days before a warning is issued
    PACK_DEACTIVATION_WARNING_DAYS: int = 60

    # Number of days before a pack is considered for deactivation
    PACK_DEACTIVATION_CRITICAL_DAYS: int = 90

    # Error rate threshold for warning status (5%)
    PACK_DEACTIVATION_ERROR_THRESHOLD: float = 0.05

    # Error rate threshold for critical status (10%)
    PACK_DEACTIVATION_CRITICAL_ERROR_THRESHOLD: float = 0.10

    # Enable automatic deactivation (False = manual review only)
    PACK_DEACTIVATION_AUTO_ENABLED: bool = False

    # Grace period in days before deactivation after reaching critical
    PACK_DEACTIVATION_GRACE_PERIOD_DAYS: int = 30

    # Enable email notifications for deactivation events
    PACK_DEACTIVATION_EMAIL_NOTIFICATIONS: bool = True

    # Notification recipients (comma-separated email list, or 'owners' for dept owners)
    PACK_DEACTIVATION_NOTIFY_EMAILS: str = "owners"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


# Global config instance
pack_lifecycle_config = PackLifecycleConfig()
