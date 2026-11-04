"""
Feature Flag System

Simple feature flag implementation using environment/config.

Part of SC-12.1 implementation.
"""

import os
from functools import lru_cache
from typing import Optional

# Default feature flags
DEFAULT_FLAGS: dict[str, bool] = {
    "enable_2fa": False,
    "enable_websockets": True,
    "enable_ai_agents": True,
    "enable_file_uploads": True,
    "enable_email_notifications": False,
    "maintenance_mode": False,
    "enable_profiling": False,
    "enable_rate_limiting": True,
    "twin.enabled": True,
}


class FeatureFlagService:
    """
    Feature flag service for toggling features.

    Supports:
    - Environment variable overrides (FEATURE_<NAME>=true/false)
    - Default values
    - Runtime checks

    Usage:
        flags = FeatureFlagService()
        if flags.is_enabled("enable_2fa"):
            # 2FA logic
    """

    def __init__(self, defaults: dict[str, bool] | None = None) -> None:
        self._flags = defaults or DEFAULT_FLAGS.copy()
        self._load_env_overrides()

    def _load_env_overrides(self) -> None:
        """Load feature flag overrides from environment."""
        for key in self._flags:
            env_key = f"FEATURE_{key.upper()}"
            env_value = os.getenv(env_key)
            if env_value is not None:
                self._flags[key] = env_value.lower() in ("true", "1", "yes")

    def is_enabled(self, flag_name: str) -> bool:
        """
        Check if a feature flag is enabled.

        Args:
            flag_name: Name of the feature flag

        Returns:
            True if enabled, False otherwise
        """
        return self._flags.get(flag_name, False)

    def enable(self, flag_name: str) -> None:
        """Enable a feature flag at runtime."""
        self._flags[flag_name] = True

    def disable(self, flag_name: str) -> None:
        """Disable a feature flag at runtime."""
        self._flags[flag_name] = False

    def all_flags(self) -> dict[str, bool]:
        """Get all feature flags and their current status."""
        return self._flags.copy()


@lru_cache
def get_feature_flags() -> FeatureFlagService:
    """Get cached feature flag service instance."""
    return FeatureFlagService()


def is_feature_enabled(flag_name: str) -> bool:
    """Convenience function to check feature flag."""
    return get_feature_flags().is_enabled(flag_name)
