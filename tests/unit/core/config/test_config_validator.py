"""Tests for src.core.config.config_validator placeholder secret detection."""

from unittest.mock import MagicMock, patch

import pytest

from src.core.config.config_validator import (
    ConfigSeverity,
    ConfigValidator,
)


class TestPydanticPlaceholderDefaults:
    """Test that Pydantic Settings placeholder secrets are detected."""

    def test_placeholder_secret_in_production_is_error(self):
        """Production with placeholder SECRET_KEY returns ERROR."""
        with patch.dict("os.environ", {"ENVIRONMENT": "production"}, clear=False):
            mock_settings_v1 = MagicMock()
            with patch("src.core.config.settings", mock_settings_v1):
                mock_settings_v1.SECRET_KEY = (
                    "a_default_secret_key_that_must_be_overridden_in_production"
                )
                mock_settings_v1.JWT_SECRET_KEY = (
                    "a_default_secret_key_that_must_be_overridden_in_production"
                )

                with patch("src.core.config.config.Settings") as mock_settings_v2_cls:
                    mock_settings_v2 = MagicMock()
                    mock_settings_v2.SECRET_KEY = (
                        "a_default_secret_key_that_must_be_overridden_in_production"
                    )
                    mock_settings_v2.JWT_SECRET_KEY = (
                        "a_default_secret_key_that_must_be_overridden_in_production"
                    )
                    mock_settings_v2_cls.return_value = mock_settings_v2

                    validator = ConfigValidator()
                    result = validator.validate()

        placeholder_issues = [
            i for i in result.issues if "Placeholder secret detected" in i.message
        ]
        assert len(placeholder_issues) > 0
        assert all(i.severity == ConfigSeverity.ERROR for i in placeholder_issues)

    def test_placeholder_secret_in_development_is_warning(self):
        """Development with placeholder SECRET_KEY returns WARNING."""
        with patch.dict("os.environ", {"ENVIRONMENT": "development"}, clear=False):
            mock_settings_v1 = MagicMock()
            with patch("src.core.config.settings", mock_settings_v1):
                mock_settings_v1.SECRET_KEY = (
                    "a_default_secret_key_that_must_be_overridden_in_production"
                )
                mock_settings_v1.JWT_SECRET_KEY = "dev-static-secret-key-for-stability-12345"

                with patch("src.core.config.config.Settings") as mock_settings_v2_cls:
                    mock_settings_v2 = MagicMock()
                    mock_settings_v2.SECRET_KEY = "your-secret-key-change-in-production"
                    mock_settings_v2.JWT_SECRET_KEY = "your-secret-key-change-in-production"
                    mock_settings_v2_cls.return_value = mock_settings_v2

                    validator = ConfigValidator()
                    result = validator.validate()

        placeholder_issues = [
            i for i in result.issues if "Placeholder secret detected" in i.message
        ]
        assert len(placeholder_issues) > 0
        assert all(i.severity == ConfigSeverity.WARNING for i in placeholder_issues)

    def test_real_secret_has_no_placeholder_issue(self):
        """Real secret values do not trigger placeholder issues."""
        with patch.dict("os.environ", {"ENVIRONMENT": "production"}, clear=False):
            mock_settings_v1 = MagicMock()
            with patch("src.core.config.settings", mock_settings_v1):
                mock_settings_v1.SECRET_KEY = (
                    "a_real_secret_key_that_is_long_enough_for_production_12345"
                )
                mock_settings_v1.JWT_SECRET_KEY = (
                    "another_real_secret_key_that_is_long_enough_for_production_12345"
                )

                with patch("src.core.config.config.Settings") as mock_settings_v2_cls:
                    mock_settings_v2 = MagicMock()
                    mock_settings_v2.SECRET_KEY = (
                        "yet_another_real_secret_key_long_enough_for_production"
                    )
                    mock_settings_v2.JWT_SECRET_KEY = (
                        "yet_another_real_secret_key_long_enough_for_production"
                    )
                    mock_settings_v2_cls.return_value = mock_settings_v2

                    validator = ConfigValidator()
                    result = validator.validate()

        placeholder_issues = [
            i for i in result.issues if "Placeholder secret detected" in i.message
        ]
        assert len(placeholder_issues) == 0

    def test_insecure_defaults_catches_explicit_placeholder(self):
        """Explicitly setting env var to placeholder is caught by INSECURE_DEFAULTS."""
        with patch.dict(
            "os.environ",
            {
                "ENVIRONMENT": "production",
                "SECRET_KEY": "your-secret-key-change-in-production",
                "JWT_SECRET_KEY": ("real-jwt-secret-key-that-is-long-enough-1234"),
            },
            clear=False,
        ):
            mock_settings_v1 = MagicMock()
            with patch("src.core.config.settings", mock_settings_v1):
                mock_settings_v1.SECRET_KEY = "your-secret-key-change-in-production"
                mock_settings_v1.JWT_SECRET_KEY = "real-jwt-secret-key-that-is-long-enough-1234"

                with patch("src.core.config.config.Settings") as mock_settings_v2_cls:
                    mock_settings_v2 = MagicMock()
                    mock_settings_v2.SECRET_KEY = "real-secret-key-that-is-long-enough-12345"
                    mock_settings_v2.JWT_SECRET_KEY = "real-jwt-secret-key-that-is-long-enough-1234"
                    mock_settings_v2_cls.return_value = mock_settings_v2

                    validator = ConfigValidator()
                    result = validator.validate()

        insecure_issues = [i for i in result.issues if "Insecure default value" in i.message]
        assert len(insecure_issues) > 0
        assert any(i.key == "SECRET_KEY" for i in insecure_issues)

    def test_user_behavioral_placeholder_blocks_startup(self):
        """App startup with placeholder secret fails with clear message."""
        with patch.dict("os.environ", {"ENVIRONMENT": "production"}, clear=False):
            mock_settings_v1 = MagicMock()
            with patch("src.core.config.settings", mock_settings_v1):
                mock_settings_v1.SECRET_KEY = (
                    "a_default_secret_key_that_must_be_overridden_in_production"
                )
                mock_settings_v1.JWT_SECRET_KEY = (
                    "a_default_secret_key_that_must_be_overridden_in_production"
                )

                with patch("src.core.config.config.Settings") as mock_settings_v2_cls:
                    mock_settings_v2 = MagicMock()
                    mock_settings_v2.SECRET_KEY = (
                        "a_default_secret_key_that_must_be_overridden_in_production"
                    )
                    mock_settings_v2.JWT_SECRET_KEY = (
                        "a_default_secret_key_that_must_be_overridden_in_production"
                    )
                    mock_settings_v2_cls.return_value = mock_settings_v2

                    validator = ConfigValidator()
                    result = validator.validate()

        assert result.valid is False
        assert len(result.errors) > 0
        placeholder_errors = [
            i for i in result.errors if "Placeholder secret detected" in i.message
        ]
        assert len(placeholder_errors) > 0
        assert all("must be overridden" in i.message for i in placeholder_errors)
