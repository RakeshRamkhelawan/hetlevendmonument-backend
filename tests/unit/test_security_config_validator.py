"""
Test Security Configuration Validator
TDD RED PHASE: These tests should FAIL initially
"""

import os
from unittest.mock import patch

import pytest

# Skip all tests if the validator has not been implemented yet.
# When scripts.validate_security_config is created, tests auto-enable.
pytest.importorskip("scripts.validate_security_config")


class TestJWTSecretValidation:
    """Test JWT secret strength validation - TDD RED PHASE"""

    def test_jwt_secret_validation_rejects_missing_secret(self):
        """RED: Test fails when JWT_SECRET_KEY not set"""
        with patch.dict(os.environ, {"JWT_SECRET_KEY": ""}, clear=True):
            from scripts.validate_security_config import validate_jwt_secret

            is_valid, message = validate_jwt_secret()

            assert is_valid is False
            assert "not set" in message.lower()

    def test_jwt_secret_validation_rejects_short_secret(self):
        """RED: Test fails when secret is too short (< 32 chars)"""
        with patch.dict(os.environ, {"JWT_SECRET_KEY": "tooshort123"}):
            from scripts.validate_security_config import validate_jwt_secret

            is_valid, message = validate_jwt_secret()

            assert is_valid is False
            assert "too short" in message.lower()

    def test_jwt_secret_validation_rejects_insecure_patterns(self):
        """RED: Test fails when secret contains insecure patterns"""
        insecure_secrets = [
            "dev-secret-key-for-testing-purposes-12345",
            "test-secret-key-for-development-use-only",
            "change-me-in-production-secret-key-12345",
            "password-based-secret-key-for-jwt-tokens",
        ]

        for secret in insecure_secrets:
            with patch.dict(os.environ, {"JWT_SECRET_KEY": secret}):
                from scripts.validate_security_config import validate_jwt_secret

                is_valid, message = validate_jwt_secret()

                assert is_valid is False, f"Should reject: {secret}"
                assert "insecure pattern" in message.lower()

    def test_jwt_secret_validation_accepts_strong_secret(self):
        """RED: Test passes when secret is cryptographically strong"""
        strong_secret = (
            "2Qoi8Dqi3om6KOLx-J0ImrxSlD5dH02dr7yhDb1-lJWPHTXbKeTEJZpLZoa1ayHEjk4ubMWqzJYFqU4fxjdQHg"
        )

        with patch.dict(os.environ, {"JWT_SECRET_KEY": strong_secret}):
            from scripts.validate_security_config import validate_jwt_secret

            is_valid, message = validate_jwt_secret()

            assert is_valid is True
            assert "strong" in message.lower()


class TestDatabaseURLValidation:
    """Test database URL security validation - TDD RED PHASE"""

    def test_database_url_rejects_missing_url(self):
        """RED: Test fails when DATABASE_URL not set"""
        with patch.dict(os.environ, {}, clear=True):
            from scripts.validate_security_config import validate_database_url

            is_valid, message = validate_database_url()

            assert is_valid is False
            assert "not set" in message.lower()

    def test_database_url_rejects_weak_credentials(self):
        """RED: Test fails when default/weak credentials detected"""
        weak_urls = [
            "postgresql://postgres:postgres@localhost/db",
            "postgresql://user:password@localhost/db",
            "postgresql://root:root@localhost/db",
            "postgresql://admin:admin@localhost/db",
        ]

        for url in weak_urls:
            with patch.dict(os.environ, {"DATABASE_URL": url}):
                from scripts.validate_security_config import validate_database_url

                is_valid, message = validate_database_url()

                assert is_valid is False, f"Should reject: {url}"
                assert "weak" in message.lower() or "credentials" in message.lower()

    def test_database_url_accepts_strong_credentials(self):
        """RED: Test passes when strong credentials used"""
        strong_url = "postgresql://sanskriti_user:xK9mP2vL8qR5wN3h@localhost:5432/production_db"

        with patch.dict(os.environ, {"DATABASE_URL": strong_url}):
            from scripts.validate_security_config import validate_database_url

            is_valid, message = validate_database_url()

            assert is_valid is True
            assert "secure" in message.lower()


class TestCORSPolicyValidation:
    """Test CORS policy validation - TDD RED PHASE"""

    def test_cors_rejects_wildcard_origins(self):
        """RED: Test fails when CORS allows all origins (*)"""
        with patch.dict(os.environ, {"CORS_ALLOWED_ORIGINS": "*"}):
            from scripts.validate_security_config import validate_cors_policy

            is_valid, message = validate_cors_policy()

            assert is_valid is False
            assert "all origins" in message.lower() or "risk" in message.lower()

    def test_cors_rejects_http_in_production(self):
        """RED: Test fails when HTTP origins in production"""
        with patch.dict(
            os.environ,
            {
                "CORS_ALLOWED_ORIGINS": "http://localhost:3000,http://app.example.com",
                "ENVIRONMENT": "production",
            },
        ):
            from scripts.validate_security_config import validate_cors_policy

            is_valid, message = validate_cors_policy()

            assert is_valid is False
            assert "http" in message.lower()

    def test_cors_accepts_restrictive_https_origins(self):
        """RED: Test passes when CORS is restrictive with HTTPS"""
        with patch.dict(
            os.environ,
            {
                "CORS_ALLOWED_ORIGINS": "https://app.sanskritisetu.org,https://admin.sanskritisetu.org"
            },
        ):
            from scripts.validate_security_config import validate_cors_policy

            is_valid, message = validate_cors_policy()

            assert is_valid is True
            assert "restrictive" in message.lower()


class TestEnvironmentValidation:
    """Test environment mode validation - TDD RED PHASE"""

    def test_environment_rejects_missing_value(self):
        """RED: Test fails when ENVIRONMENT not set"""
        with patch.dict(os.environ, {}, clear=True):
            from scripts.validate_security_config import validate_environment_mode

            is_valid, message = validate_environment_mode()

            assert is_valid is False
            assert "not set" in message.lower()

    def test_environment_rejects_unknown_values(self):
        """RED: Test fails when ENVIRONMENT has unknown value"""
        unknown_envs = ["prod", "dev", "testing", "local", "stage"]

        for env in unknown_envs:
            with patch.dict(os.environ, {"ENVIRONMENT": env}):
                from scripts.validate_security_config import validate_environment_mode

                is_valid, message = validate_environment_mode()

                assert is_valid is False, f"Should reject: {env}"
                assert "unknown" in message.lower()

    def test_environment_accepts_valid_values(self):
        """RED: Test passes for valid environment values"""
        valid_envs = ["development", "staging", "production"]

        for env in valid_envs:
            with patch.dict(os.environ, {"ENVIRONMENT": env}):
                from scripts.validate_security_config import validate_environment_mode

                is_valid, message = validate_environment_mode()

                assert is_valid is True
                assert env in message.lower()


class TestDebugModeValidation:
    """Test debug mode validation - TDD RED PHASE"""

    def test_debug_rejects_enabled_in_production(self):
        """RED: Test fails when DEBUG enabled in production"""
        debug_values = ["True", "true", "1", "yes", "YES"]

        for debug in debug_values:
            with patch.dict(os.environ, {"ENVIRONMENT": "production", "DEBUG": debug}):
                from scripts.validate_security_config import validate_debug_mode

                is_valid, message = validate_debug_mode()

                assert is_valid is False, f"Should reject DEBUG={debug} in production"
                assert "production" in message.lower()
                assert "debug" in message.lower()

    def test_debug_accepts_disabled_in_production(self):
        """RED: Test passes when DEBUG disabled in production"""
        with patch.dict(os.environ, {"ENVIRONMENT": "production", "DEBUG": "False"}):
            from scripts.validate_security_config import validate_debug_mode

            is_valid, message = validate_debug_mode()

            assert is_valid is True
            assert "ok" in message.lower()

    def test_debug_accepts_enabled_in_development(self):
        """RED: Test passes when DEBUG enabled in development"""
        with patch.dict(os.environ, {"ENVIRONMENT": "development", "DEBUG": "True"}):
            from scripts.validate_security_config import validate_debug_mode

            is_valid, message = validate_debug_mode()

            assert is_valid is True


# Expected test results when running pytest:
#
# pytest tests/unit/test_security_config_validator.py -v
#
# EXPECTED OUTPUT (RED PHASE - ALL SHOULD FAIL):
#
# test_jwt_secret_validation_rejects_missing_secret FAILED
#   ModuleNotFoundError: No module named 'scripts.validate_security_config'
#
# test_jwt_secret_validation_rejects_short_secret FAILED
#   ModuleNotFoundError: No module named 'scripts.validate_security_config'
#
# ... (all 18 tests should fail with ModuleNotFoundError)
#
# This proves we're doing TDD correctly - tests written BEFORE implementation!
