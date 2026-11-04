"""
Unit Tests for Feature Flags (SC-12.1)

Tests feature flag service functionality.
"""

from unittest.mock import patch

import pytest

from src.core.services.feature_flags import (
    DEFAULT_FLAGS,
    FeatureFlagService,
    get_feature_flags,
    is_feature_enabled,
)


class TestFeatureFlagService:
    """Tests for FeatureFlagService class."""

    def test_default_flags_loaded(self):
        """Test default flags are loaded on initialization."""
        service = FeatureFlagService()
        assert "enable_rate_limiting" in service.all_flags()

    def test_is_enabled_returns_default(self):
        """Test is_enabled returns default value."""
        service = FeatureFlagService({"test_flag": True})
        assert service.is_enabled("test_flag") is True

    def test_is_enabled_unknown_flag_returns_false(self):
        """Test unknown flag returns False."""
        service = FeatureFlagService()
        assert service.is_enabled("nonexistent_flag") is False

    def test_enable_flag(self):
        """Test enabling a flag at runtime."""
        service = FeatureFlagService({"my_flag": False})
        service.enable("my_flag")
        assert service.is_enabled("my_flag") is True

    def test_disable_flag(self):
        """Test disabling a flag at runtime."""
        service = FeatureFlagService({"my_flag": True})
        service.disable("my_flag")
        assert service.is_enabled("my_flag") is False

    def test_all_flags_returns_copy(self):
        """Test all_flags returns a copy, not original."""
        service = FeatureFlagService({"flag": True})
        flags = service.all_flags()
        flags["flag"] = False
        assert service.is_enabled("flag") is True


class TestDefaultFlags:
    """Tests for default flag configuration."""

    def test_default_flags_exist(self):
        """Test expected default flags exist."""
        assert "enable_2fa" in DEFAULT_FLAGS
        assert "enable_websockets" in DEFAULT_FLAGS
        assert "maintenance_mode" in DEFAULT_FLAGS

    def test_maintenance_mode_default_off(self):
        """Test maintenance mode is off by default."""
        assert DEFAULT_FLAGS["maintenance_mode"] is False

    def test_rate_limiting_default_on(self):
        """Test rate limiting is on by default."""
        assert DEFAULT_FLAGS["enable_rate_limiting"] is True
