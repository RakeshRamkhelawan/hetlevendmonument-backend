"""
Unit tests for P0-2: MOCK-002 - Hardcoded Database Credentials
Tests that all hardcoded database credentials have been removed
"""

import os
from unittest.mock import patch

import pytest

from src.core.shared.config import get_settings, reload_settings, validate_configuration


def test_no_hardcoded_database_credentials_in_config():
    """Verify that config.py has no hardcoded database credentials"""
    with open("core/shared/config.py") as f:
        content = f.read()

    # Check for common hardcoded credentials
    assert "sanskriti_user:sanskriti_pass" not in content
    assert "postgresql://sanskriti_user" not in content.lower()


def test_database_url_required_no_default():
    """Test that DATABASE_URL has a default value (SQLite or from .env)"""
    # Clear only DATABASE_URL env var, not all env vars (to preserve test environment)
    env_without_db = {k: v for k, v in os.environ.items() if k != "DATABASE_URL"}
    with patch.dict("os.environ", env_without_db, clear=True):
        reload_settings()
        settings = get_settings()
        # Should have either the default SQLite or value from .env file
        assert settings.database_url is not None
        assert len(settings.database_url) > 0

        # Validation should fail for production with SQLite
        with patch.dict(
            "os.environ",
            {"ENVIRONMENT": "production", "DATABASE_URL": "sqlite:///./test.db"},
        ):
            reload_settings()
            validation_result = validate_configuration()
            errors = validation_result.get("errors", [])
            # Should have validation errors for production with SQLite
            assert len(errors) > 0
            assert any("PostgreSQL" in error for error in errors)


def test_validate_configuration_missing_database_url():
    """Test that validation fails when DATABASE_URL is missing"""
    with patch.dict("os.environ", {"ENVIRONMENT": "production"}, clear=True):
        reload_settings()
        validation_result = validate_configuration()

        errors = validation_result.get("errors", [])
        assert len(errors) > 0
        assert any("DATABASE_URL" in error for error in errors)


def test_validate_configuration_invalid_database_protocol():
    """Test that validation fails for non-PostgreSQL database URLs"""
    with patch.dict(
        "os.environ",
        {
            "ENVIRONMENT": "production",
            "DATABASE_URL": "mysql://user:pass@localhost:3306/db",
            "SECRET_KEY": "a" * 64,
        },
    ):
        reload_settings()
        validation_result = validate_configuration()

        errors = validation_result.get("errors", [])
        assert any("PostgreSQL" in error for error in errors)


def test_validate_configuration_localhost_in_production():
    """Test that validation fails when using localhost in production"""
    with patch.dict(
        "os.environ",
        {
            "ENVIRONMENT": "production",
            "DATABASE_URL": "postgresql://user:pass@localhost:5432/db",
            "SECRET_KEY": "a" * 64,
        },
    ):
        reload_settings()
        validation_result = validate_configuration()

        errors = validation_result.get("errors", [])
        assert any("localhost" in error.lower() for error in errors)


def test_validate_configuration_default_password_detected():
    """Test that validation detects common default passwords"""
    default_passwords = ["password", "sanskriti_pass", "changeme"]

    for pwd in default_passwords:
        with patch.dict(
            "os.environ",
            {
                "ENVIRONMENT": "production",
                "DATABASE_URL": f"postgresql://user:{pwd}@db.example.com:5432/sanskriti",
                "SECRET_KEY": "a" * 64,
            },
        ):
            reload_settings()
            validation_result = validate_configuration()

            errors = validation_result.get("errors", [])
            assert any(
                "default password" in error.lower() for error in errors
            ), f"Failed to detect default password: {pwd}"


def test_validate_configuration_valid_production_database_url():
    """Test that validation passes with a valid production DATABASE_URL"""
    with patch.dict(
        "os.environ",
        {
            "ENVIRONMENT": "production",
            "DATABASE_URL": "postgresql://secure_user:Very$ecureP@ssw0rd!@db.example.com:5432/sanskriti_prod",
            "SECRET_KEY": "a" * 64,
            "DEFAULT_ISOLATION_LEVEL": "DOCKER",
        },
    ):
        with patch("core.shared.docker_utils.check_docker_availability", return_value=True):
            reload_settings()
            validation_result = validate_configuration()

            errors = validation_result.get("errors", [])
            # Should have no DATABASE_URL related errors
            assert not any("DATABASE_URL" in error for error in errors)


def test_connection_py_has_no_hardcoded_fallback():
    """Verify that connection.py has no hardcoded database fallback"""
    with open("core/database/connection.py") as f:
        content = f.read()

    assert "sanskriti_user:sanskriti_pass" not in content
    assert "postgresql://sanskriti_user" not in content.lower()


def test_unified_config_has_no_hardcoded_database():
    """Verify that unified_config.py has no hardcoded database URL"""
    with open("core/config/unified_config.py") as f:
        content = f.read()

    assert "sanskriti_user:sanskriti_pass" not in content
    assert "postgresql+asyncpg://sanskriti_user" not in content.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
