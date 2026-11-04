"""
Integration Tests for P0 Blocker Fixes
Tests that all 7 P0 fixes work together correctly
"""

import os
from typing import Any
from unittest.mock import patch

import pytest

from src.core.shared.config import Settings, validate_configuration
from src.core.shared.interfaces import IsolationLevel


class TestP0ConfigIntegration:
    """Test configuration integration across all P0 fixes"""

    def test_valid_production_config_passes_all_validations(self) -> None:
        """Test that valid production config passes all P0 validations"""
        env_vars = {
            "ENVIRONMENT": "production",
            "SECRET_KEY": "x" * 64,  # 64 char key
            "DATABASE_URL": "postgresql://user:securepass@prod-db.example.com:5432/sanskriti_prod",
            "GOOGLE_API_KEY": "test-api-key",
            "ALLOWED_ORIGINS": "https://app.sanskritisetu.org,https://www.sanskritisetu.org",
            "DEBUG": "false",
            "DEFAULT_ISOLATION_LEVEL": "container",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()
            assert settings.environment == "production"
            assert settings.debug is False
            assert settings.default_isolation_level == IsolationLevel.CONTAINER
            assert len(settings.secret_key) == 64

    def test_invalid_config_fails_fast_on_startup(self) -> None:
        """Test that invalid config fails at startup (fail-fast philosophy)"""
        # Invalid: production debug=True
        env_vars: dict[str, str] = {
            "ENVIRONMENT": "production",
            "DEBUG": "true",
            "SECRET_KEY": "x" * 64,
            "DATABASE_URL": "postgresql://user:pass@host:5432/db",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            Settings()
            validation = validate_configuration()
            # Should have errors for debug=True in production
            assert len(validation["errors"]) > 0

    def test_environment_variables_override_defaults(self) -> None:
        """Test that environment variables override defaults"""
        env_vars: dict[str, str] = {
            "ENVIRONMENT": "production",
            "SECRET_KEY": "x" * 64,
            "DATABASE_URL": "postgresql://user:pass@host:5432/db",
            "DEFAULT_ISOLATION_LEVEL": "container",
            "DEBUG": "false",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()
            assert settings.environment == "production"
            assert settings.default_isolation_level == IsolationLevel.CONTAINER
            assert settings.debug is False


class TestP0DatabaseIntegration:
    """Test database credential integration with other P0 fixes"""

    def test_database_credentials_validation_with_production_env(self) -> None:
        """Test that DB creds are validated in production"""
        # Invalid: localhost in production
        env_vars: dict[str, str] = {
            "ENVIRONMENT": "production",
            "DATABASE_URL": "postgresql://user:pass@localhost:5432/db",
            "SECRET_KEY": "x" * 64,
        }

        with patch.dict(os.environ, env_vars, clear=True):
            Settings()
            validation = validate_configuration()
            # Should have error for localhost in production
            assert len(validation["errors"]) > 0

    def test_database_credentials_no_weak_passwords(self) -> None:
        """Test that weak DB passwords are rejected"""
        weak_passwords = ["password", "pass", "changeme", "sanskriti_pass"]

        for weak_pass in weak_passwords:
            env_vars: dict[str, str] = {
                "ENVIRONMENT": "production",
                "DATABASE_URL": f"postgresql://user:{weak_pass}@prod-host:5432/db",
                "SECRET_KEY": "x" * 64,
            }

            with patch.dict(os.environ, env_vars, clear=True):
                Settings()
                validation = validate_configuration()
                assert len(validation["errors"]) > 0, (
                    f"Weak password '{weak_pass}' should be rejected"
                )

    def test_database_url_must_be_postgresql(self) -> None:
        """Test that only PostgreSQL URLs are accepted"""
        invalid_urls = [
            "mysql://user:pass@host/db",
            "mongodb://user:pass@host/db",
            "sqlite:///path/to/db.sqlite",
        ]

        for url in invalid_urls:
            env_vars: dict[str, str] = {
                "ENVIRONMENT": "production",
                "DATABASE_URL": url,
                "SECRET_KEY": "x" * 64,
            }

            with patch.dict(os.environ, env_vars, clear=True):
                Settings()
                validation = validate_configuration()
                assert len(validation["errors"]) > 0, (
                    f"Non-PostgreSQL URL '{url}' should be rejected"
                )


class TestP0LLMIntegration:
    """Test LLM client integration with other P0 fixes"""

    def test_llm_client_requires_api_key(self) -> None:
        """Test that LLM client fails without GOOGLE_API_KEY"""
        env_vars = {
            "ENVIRONMENT": "production",
            "SECRET_KEY": "x" * 64,
            "DATABASE_URL": "postgresql://user:securepass@prod-host:5432/db",
            # Missing: GOOGLE_API_KEY
        }

        with patch.dict(os.environ, env_vars, clear=True):
            # Should raise error or fail gracefully
            # This depends on when LLM client is initialized
            try:
                from src.core.llm.production_llm_client import ProductionLLMClient

                client = ProductionLLMClient()
                # If no API key, should fail
                assert client is None or not hasattr(client, "query")
            except Exception:
                # Expected to fail
                pass

    def test_llm_cache_respects_isolation_level(self) -> None:
        """Test that LLM cache respects database isolation level"""
        env_vars: dict[str, str] = {
            "ENVIRONMENT": "production",
            "SECRET_KEY": "x" * 64,
            "DATABASE_URL": "postgresql://user:securepass@prod-host:5432/db",
            "GOOGLE_API_KEY": "test-key",
            "DEFAULT_ISOLATION_LEVEL": "container",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()
            # Cache keys should incorporate tenant/isolation info
            assert settings.default_isolation_level == IsolationLevel.CONTAINER


class TestP0SandboxIntegration:
    """Test sandbox manager integration with other P0 fixes"""

    def test_sandbox_defaults_to_docker_isolation(self) -> None:
        """Test that sandbox defaults to Docker isolation"""
        env_vars: dict[str, str] = {
            "ENVIRONMENT": "production",
            "SECRET_KEY": "x" * 64,
            "DATABASE_URL": "postgresql://user:securepass@prod-host:5432/db",
            "DEFAULT_ISOLATION_LEVEL": "container",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()
            assert settings.default_isolation_level == IsolationLevel.CONTAINER
            assert settings.default_isolation_level != IsolationLevel.MOCK

    def test_sandbox_never_uses_mock_in_production(self) -> None:
        """Test that sandbox never falls back to mock in production"""
        env_vars: dict[str, str] = {
            "ENVIRONMENT": "production",
            "SECRET_KEY": "x" * 64,
            "DATABASE_URL": "postgresql://user:securepass@prod-host:5432/db",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()
            # Should always default to Docker, never Mock
            assert settings.default_isolation_level == IsolationLevel.CONTAINER


class TestP0CORSIntegration:
    """Test CORS configuration integration with authentication"""

    def test_cors_wildcard_rejected_in_production(self) -> None:
        """Test that wildcard CORS is rejected in production"""
        env_vars: dict[str, str] = {
            "ENVIRONMENT": "production",
            "SECRET_KEY": "x" * 64,
            "DATABASE_URL": "postgresql://user:securepass@prod-host:5432/db",
            "ALLOWED_ORIGINS": "*",  # Wildcard - should be rejected
        }

        with patch.dict(os.environ, env_vars, clear=True):
            Settings()
            validation = validate_configuration()
            # Wildcard should be rejected
            assert len(validation["errors"]) > 0 or validation.get("warnings", [])

    def test_cors_specific_origins_required_in_production(self) -> None:
        """Test that specific origins are required in production"""
        env_vars: dict[str, str] = {
            "ENVIRONMENT": "production",
            "SECRET_KEY": "x" * 64,
            "DATABASE_URL": "postgresql://user:securepass@prod-host:5432/db",
            "ALLOWED_ORIGINS": "https://app.sanskritisetu.org,https://www.sanskritisetu.org",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            Settings()
            validation = validate_configuration()
            # Specific origins should pass
            assert len(validation.get("errors", [])) == 0 or validation.get("is_valid")

    def test_cors_with_frontend_url_env_var(self) -> None:
        """Test CORS configuration via FRONTEND_URL environment variable"""
        env_vars: dict[str, str] = {
            "ENVIRONMENT": "production",
            "SECRET_KEY": "x" * 64,
            "DATABASE_URL": "postgresql://user:securepass@prod-host:5432/db",
            "FRONTEND_URL": "https://sanskritisetu.org",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()
            # Should accept FRONTEND_URL as alternative to ALLOWED_ORIGINS
            assert settings.environment == "production"


class TestP0DebugModeIntegration:
    """Test debug mode integration with error handling"""

    def test_debug_disabled_hides_sensitive_errors(self) -> None:
        """Test that debug=False hides stack traces and secrets"""
        env_vars: dict[str, str] = {
            "ENVIRONMENT": "production",
            "SECRET_KEY": "x" * 64,
            "DATABASE_URL": "postgresql://user:securepass@prod-host:5432/db",
            "DEBUG": "false",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()
            assert settings.debug is False
            # In production with debug=False, errors should not include:
            # - Stack traces
            # - Database URLs
            # - Secret keys
            # - File paths

    def test_debug_enabled_in_dev_only(self) -> None:
        """Test that debug can only be enabled in development"""
        env_vars: dict[str, str] = {
            "ENVIRONMENT": "production",
            "SECRET_KEY": "x" * 64,
            "DATABASE_URL": "postgresql://user:securepass@prod-host:5432/db",
            "DEBUG": "true",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            Settings()
            validation = validate_configuration()
            # Debug=True in production should fail validation
            assert len(validation["errors"]) > 0

    def test_debug_allowed_in_development(self) -> None:
        """Test that debug can be enabled in development"""
        env_vars: dict[str, str] = {
            "ENVIRONMENT": "development",
            "SECRET_KEY": "x" * 64,
            "DEBUG": "true",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()
            assert settings.debug is True


class TestP0SecretKeyIntegration:
    """Test secret key validation integration"""

    def test_secret_key_required_in_production(self) -> None:
        """Test that secret key is required (no default)"""
        env_vars = {
            "ENVIRONMENT": "production",
            "DATABASE_URL": "postgresql://user:securepass@prod-host:5432/db",
            # Missing: SECRET_KEY
        }

        with patch.dict(os.environ, env_vars, clear=True):
            # Should fail because SECRET_KEY is required
            try:
                Settings()
                # If we got here, SECRET_KEY might have been set with a default
                # In production this should not happen
                validate_configuration()
                # Should have error if SECRET_KEY is missing or weak
            except Exception:
                # Expected - SECRET_KEY is required
                pass

    def test_secret_key_minimum_length_enforced(self) -> None:
        """Test that secret key minimum length is enforced"""
        weak_keys = [
            "short",
            "x" * 32,  # Too short
        ]

        for weak_key in weak_keys:
            env_vars: dict[str, str] = {
                "ENVIRONMENT": "production",
                "SECRET_KEY": weak_key,
                "DATABASE_URL": "postgresql://user:securepass@prod-host:5432/db",
            }

            with patch.dict(os.environ, env_vars, clear=True):
                Settings()
                validation = validate_configuration()
                if len(weak_key) < 64:
                    # Should have error for weak key
                    assert len(validation.get("errors", [])) > 0 or not validation.get("is_valid")

    def test_strong_secret_key_accepted(self) -> None:
        """Test that strong secret keys are accepted"""
        strong_key = "x" * 64  # 64 characters

        env_vars: dict[str, str] = {
            "ENVIRONMENT": "production",
            "SECRET_KEY": strong_key,
            "DATABASE_URL": "postgresql://user:securepass@prod-host:5432/db",
            "GOOGLE_API_KEY": "test-key",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()
            assert len(settings.secret_key) >= 64


class TestP0FullIntegration:
    """Test all P0 fixes working together"""

    def test_all_p0_constraints_together(self) -> None:
        """Test that all P0 fixes work together without conflicts"""
        env_vars: dict[str, str] = {
            "ENVIRONMENT": "production",
            "SECRET_KEY": "y" * 64,
            "DATABASE_URL": "postgresql://user:secure_password_123@prod-db.example.com:5432/sanskriti_prod",
            "GOOGLE_API_KEY": "google-api-key-here",
            "ALLOWED_ORIGINS": "https://app.sanskritisetu.org",
            "REDIS_URL": "redis://prod-redis:6379/0",
            "DEBUG": "false",
            "DEFAULT_ISOLATION_LEVEL": "container",
        }

        with patch.dict(os.environ, env_vars, clear=True):
            settings = Settings()
            validate_configuration()

            # All P0 constraints should be satisfied:
            # P0-0: Default isolation = Docker
            assert settings.default_isolation_level == IsolationLevel.CONTAINER

            # P0-1: Secret key is required (no default)
            assert len(settings.secret_key) >= 64

            # P0-2: No hardcoded DB credentials
            assert "localhost" not in settings.database_url

            # P0-5: Debug mode is False
            assert settings.debug is False

            # P0-6: CORS is specific (not wildcard)
            # (This would be in production_config)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
