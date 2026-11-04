from unittest.mock import patch

import pytest

from src.core.shared.config import (
    IsolationLevel,
    get_settings,
    reload_settings,
    validate_configuration,
)


# Mock the check_docker_availability for consistent testing
@pytest.fixture(autouse=True)
def mock_docker_availability():
    with patch("core.shared.config.check_docker_availability") as mock_check:
        yield mock_check


def test_default_isolation_level_is_docker():
    """Verify that the default isolation level is DOCKER"""
    settings = get_settings()
    assert settings.default_isolation_level == IsolationLevel.DOCKER


def test_validate_configuration_docker_unavailable_fails(mock_docker_availability):
    """Test that validation fails if Docker is required but unavailable"""
    mock_docker_availability.return_value = False
    # Temporarily set environment to production to trigger validation
    valid_key = "a" * 64  # 64 char secret key
    prod_db = "postgresql://user:securepassword123@prod-server.example.com:5432/dbname"
    with patch.dict(
        "os.environ",
        {
            "ENVIRONMENT": "production",
            "DEFAULT_ISOLATION_LEVEL": "DOCKER",
            "SECRET_KEY": valid_key,
            "DATABASE_URL": prod_db,
        },
    ):
        reload_settings()  # Reload settings to pick up env vars
        settings = get_settings()
        assert settings.default_isolation_level == IsolationLevel.DOCKER  # Ensure it's set
        validation_result = validate_configuration()
        assert len(validation_result["errors"]) > 0
        assert any(
            "Docker daemon is not running or accessible" in err
            for err in validation_result["errors"]
        )


def test_validate_configuration_docker_available_passes(mock_docker_availability):
    """Test that validation passes if Docker is required and available"""
    mock_docker_availability.return_value = True
    valid_key = "a" * 64  # 64 char secret key
    prod_db = "postgresql://user:securepassword123@prod-server.example.com:5432/dbname"
    with patch.dict(
        "os.environ",
        {
            "ENVIRONMENT": "production",
            "DEFAULT_ISOLATION_LEVEL": "DOCKER",
            "SECRET_KEY": valid_key,
            "GOOGLE_API_KEY": "test",
            "DATABASE_URL": prod_db,
        },
    ):
        reload_settings()
        settings = get_settings()
        assert settings.default_isolation_level == IsolationLevel.DOCKER
        validation_result = validate_configuration()
        assert len(validation_result["errors"]) == 0


def test_secret_key_is_loaded_from_env():
    """Verify that SECRET_KEY is loaded from environment variable."""
    test_key = "a_very_long_and_secure_secret_key_for_testing_purposes_1234567890"
    with patch.dict("os.environ", {"SECRET_KEY": test_key}):
        reload_settings()
        settings = get_settings()
        assert settings.secret_key == test_key


def test_validate_configuration_secret_key_missing_fails():
    """Test that validation fails if SECRET_KEY is missing."""
    with patch.dict("os.environ", {}, clear=True):  # Clear all env vars
        reload_settings()
        # Ensure Docker check passes for this test
        with patch("core.shared.docker_utils.check_docker_availability", return_value=True):
            validation_result = validate_configuration()
            assert len(validation_result["errors"]) > 0
            assert "SECRET_KEY must be set" in validation_result["errors"][0]


def test_validate_configuration_secret_key_too_short_fails():
    """Test that validation fails if SECRET_KEY is too short."""
    short_key = "short_key"  # Less than 64 chars
    with patch.dict("os.environ", {"SECRET_KEY": short_key}):
        reload_settings()
        # Ensure Docker check passes for this test
        with patch("core.shared.docker_utils.check_docker_availability", return_value=True):
            validation_result = validate_configuration()
            assert len(validation_result["errors"]) > 0
            assert (
                "SECRET_KEY must be at least 64 characters long" in validation_result["errors"][0]
            )


def test_validate_configuration_secret_key_valid_passes():
    """Test that validation passes if SECRET_KEY is set and long enough."""
    valid_key = (
        "a_very_long_and_secure_secret_key_for_testing_purposes_1234567890abcdef"  # 64 chars
    )
    with patch.dict("os.environ", {"SECRET_KEY": valid_key}):
        reload_settings()
        # Ensure Docker check passes for this test
        with patch("core.shared.docker_utils.check_docker_availability", return_value=True):
            validation_result = validate_configuration()
            assert len(validation_result["errors"]) == 0
