"""
Unit tests for P0-5: MOCK-017 - Debug Mode Set to True
Tests that debug mode defaults to False and production validation enforces debug=False
"""

import os
from unittest.mock import patch

import pytest

from src.core.shared.config import (
    ENVIRONMENTS,
    Settings,
    apply_environment_config,
    get_settings,
    reload_settings,
    validate_configuration,
)


class TestDebugModeDefault:
    """Tests for debug mode default value"""

    def test_debug_defaults_to_false(self):
        """Test that debug mode defaults to False (P0-5 fix)"""
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()

            assert settings.debug is False, "Debug mode must default to False for production safety"

    def test_debug_can_be_enabled_via_env(self):
        """Test that debug can be enabled via DEBUG environment variable"""
        with patch.dict(os.environ, {"DEBUG": "true"}, clear=True):
            settings = Settings()

            assert settings.debug is True

    def test_debug_false_via_env(self):
        """Test that debug can be explicitly set to False via environment"""
        with patch.dict(os.environ, {"DEBUG": "false"}, clear=True):
            settings = Settings()

            assert settings.debug is False

    def test_debug_with_various_true_values(self):
        """Test that various 'true' values enable debug mode"""
        true_values = ["true", "True", "TRUE", "1", "yes", "Yes", "YES"]

        for value in true_values:
            with patch.dict(os.environ, {"DEBUG": value}, clear=True):
                settings = Settings()
                # Note: Pydantic handles "true", "1" but not "yes" by default
                # This test documents expected behavior
                if value.lower() in ["true", "1"]:
                    assert settings.debug is True, f"DEBUG={value} should enable debug mode"


class TestProductionDebugValidation:
    """Tests for production environment debug validation"""

    def test_production_with_debug_true_fails_validation(self):
        """Test that production environment with debug=True fails validation"""
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "production",
                "DEBUG": "true",
                "SECRET_KEY": "a" * 64,  # Valid secret key
                "DATABASE_URL": "postgresql://user:pass@remote-host:5432/db",
                "GOOGLE_API_KEY": "test-api-key",
            },
            clear=True,
        ):
            reload_settings()
            settings = get_settings()

            assert settings.environment == "production"
            assert settings.debug is True

            validation = validate_configuration()
            errors = validation["errors"]

            # Must have error about debug mode in production
            assert any(
                "DEBUG mode must be disabled" in error for error in errors
            ), "Production validation must reject debug=True"

    def test_production_with_debug_false_passes_validation(self):
        """Test that production environment with debug=False passes debug validation"""
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "production",
                "DEBUG": "false",
                "SECRET_KEY": "a" * 64,
                "DATABASE_URL": "postgresql://user:securepass@remote-host:5432/db",
                "GOOGLE_API_KEY": "test-api-key",
            },
            clear=True,
        ):
            # Mock Docker availability
            with patch("core.shared.docker_utils.check_docker_availability", return_value=True):
                reload_settings()
                settings = get_settings()

                assert settings.environment == "production"
                assert settings.debug is False

                validation = validate_configuration()
                errors = validation["errors"]

                # Should not have error about debug mode
                assert not any(
                    "DEBUG mode" in error for error in errors
                ), "Production with debug=False should pass validation"

    def test_development_with_debug_true_allowed(self):
        """Test that development environment can have debug=True"""
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "development",
                "DEBUG": "true",
                "SECRET_KEY": "dev-secret-key",
                "DATABASE_URL": "sqlite:///./dev.db",
            },
            clear=True,
        ):
            reload_settings()
            settings = get_settings()

            assert settings.environment == "development"
            assert settings.debug is True

            # Development doesn't enforce strict debug=False validation
            validate_configuration()
            # Development may have other warnings, but debug=True is OK


class TestEnvironmentConfigurations:
    """Tests for environment-specific configurations"""

    def test_development_environment_config(self):
        """Test that development environment has correct debug setting"""
        dev_config = ENVIRONMENTS["development"]

        assert dev_config["debug"] is True, "Development allows debug=True"

    def test_testing_environment_config(self):
        """Test that testing environment has correct debug setting"""
        test_config = ENVIRONMENTS["testing"]

        assert test_config["debug"] is True, "Testing allows debug=True"

    def test_staging_environment_config(self):
        """Test that staging environment has debug=False"""
        staging_config = ENVIRONMENTS["staging"]

        assert staging_config["debug"] is False, "Staging must have debug=False"

    def test_production_environment_config(self):
        """Test that production environment has debug=False"""
        prod_config = ENVIRONMENTS["production"]

        assert prod_config["debug"] is False, "Production must have debug=False (P0-5)"

    def test_apply_production_environment_config(self):
        """Test applying production environment configuration"""
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "production",
                "SECRET_KEY": "a" * 64,
                "DATABASE_URL": "postgresql://user:pass@host:5432/db",
            },
            clear=True,
        ):
            reload_settings()
            settings = get_settings()

            # Apply production config
            apply_environment_config("production")

            assert settings.debug is False, "Production config must set debug=False"
            assert settings.log_level == "WARNING", "Production should use WARNING log level"

    def test_apply_staging_environment_config(self):
        """Test applying staging environment configuration"""
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "staging",
                "SECRET_KEY": "a" * 64,
                "DATABASE_URL": "postgresql://user:pass@host:5432/db",
            },
            clear=True,
        ):
            reload_settings()
            settings = get_settings()

            # Apply staging config
            apply_environment_config("staging")

            assert settings.debug is False, "Staging config must set debug=False"
            assert settings.log_level == "INFO"


class TestDebugModeImpact:
    """Tests for debug mode impact on system behavior"""

    def test_debug_false_does_not_expose_internals(self):
        """Test that debug=False setting is correct (detailed behavior testing in integration)"""
        with patch.dict(os.environ, {"DEBUG": "false"}, clear=True):
            settings = Settings()

            assert settings.debug is False

            # This is a unit test - integration tests should verify:
            # - No stack traces exposed in API responses
            # - No internal paths in error messages
            # - No sensitive error details logged

    def test_debug_true_in_development_acceptable(self):
        """Test that debug=True is acceptable in development"""
        with patch.dict(os.environ, {"ENVIRONMENT": "development", "DEBUG": "true"}, clear=True):
            settings = Settings()

            assert settings.environment == "development"
            assert settings.debug is True

            # Development can have debug=True for easier debugging


class TestConfigurationValidationFlow:
    """Tests for complete configuration validation flow"""

    def test_full_production_config_with_debug_true_invalid(self):
        """Test complete production configuration with debug=True is invalid"""
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "production",
                "DEBUG": "true",  # INVALID
                "SECRET_KEY": "a" * 64,
                "DATABASE_URL": "postgresql://user:strongpass@prod-host:5432/db",
                "GOOGLE_API_KEY": "real-api-key",
                "DEFAULT_ISOLATION_LEVEL": "docker",
            },
            clear=True,
        ):
            with patch("core.shared.docker_utils.check_docker_availability", return_value=True):
                reload_settings()

                validation = validate_configuration()
                errors = validation["errors"]

                # Must reject debug=True in production
                assert len(errors) > 0
                assert any("DEBUG mode must be disabled" in error for error in errors)

    def test_full_production_config_with_debug_false_valid(self):
        """Test complete production configuration with debug=False is valid"""
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "production",
                "DEBUG": "false",  # VALID
                "SECRET_KEY": "a" * 64,
                "DATABASE_URL": "postgresql://user:strongpass@prod-host:5432/db",
                "GOOGLE_API_KEY": "real-api-key",
                "DEFAULT_ISOLATION_LEVEL": "docker",
            },
            clear=True,
        ):
            with patch("core.shared.docker_utils.check_docker_availability", return_value=True):
                reload_settings()

                validation = validate_configuration()
                errors = validation["errors"]

                # Should pass validation (no debug-related errors)
                debug_errors = [e for e in errors if "DEBUG" in e]
                assert len(debug_errors) == 0, "debug=False should pass validation"


class TestRegressionPrevention:
    """Tests to prevent regression of P0-5 fix"""

    def test_default_value_is_false_not_true(self):
        """Critical test: Ensure default is False, not True"""
        # This is the core P0-5 fix - must never regress
        with patch.dict(os.environ, {}, clear=True):
            settings = Settings()

            assert settings.debug is False, "CRITICAL P0-5: debug must default to False, not True"

    def test_production_validation_exists(self):
        """Test that production debug validation exists"""
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "production",
                "DEBUG": "true",
                "SECRET_KEY": "a" * 64,
                "DATABASE_URL": "postgresql://user:pass@host:5432/db",
                "GOOGLE_API_KEY": "key",
            },
            clear=True,
        ):
            reload_settings()
            validation = validate_configuration()

            # Validation must check debug mode in production
            assert "errors" in validation
            assert isinstance(validation["errors"], list)

            # Must have specific error about debug mode
            debug_errors = [e for e in validation["errors"] if "DEBUG" in e.upper()]
            assert len(debug_errors) > 0, "Production validation must check DEBUG mode"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
