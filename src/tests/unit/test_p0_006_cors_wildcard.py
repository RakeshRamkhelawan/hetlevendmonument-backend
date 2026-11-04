"""
Unit tests for P0-6: SECURITY-001 - CORS Wildcard
Tests that CORS wildcard ["*"] is removed and specific origins are configured
"""

# mypy: disable-error-code="no-untyped-def,union-attr,call-arg"

import os
from unittest.mock import patch

import pytest

from src.core.config.production_config import ProductionConfigManager, SecurityConfig


class TestCORSWildcardRemoval:
    """Tests for CORS wildcard removal"""

    def test_default_allowed_origins_empty(self):
        """Test that default allowed_origins is empty list, not wildcard"""
        security = SecurityConfig(secret_key="test-key")

        assert security.allowed_origins == [], "Default must be empty list, not ['*']"
        assert "*" not in security.allowed_origins, "Wildcard must not be in default"

    def test_wildcard_not_in_defaults(self):
        """CRITICAL: Test that wildcard is NOT in default configuration"""
        security = SecurityConfig(secret_key="test-key")

        # This is the core P0-6 fix
        assert security.allowed_origins != ["*"], "CRITICAL P0-6: Default cannot be wildcard"


class TestProductionCORSConfiguration:
    """Tests for production CORS configuration"""

    def test_production_with_wildcard_fails_validation(self):
        """Test that production with wildcard fails validation"""
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "production",
                "SECRET_KEY": "a" * 64,
                "DATABASE_URL": "postgresql://user:pass@host:5432/db",
                "ALLOWED_ORIGINS": "*",  # INVALID in production
            },
            clear=True,
        ):
            with pytest.raises(ValueError, match="CORS wildcard"):
                ProductionConfigManager()

    def test_production_with_wildcard_in_list_fails(self):
        """Test that production with wildcard in list fails"""
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "production",
                "SECRET_KEY": "a" * 64,
                "DATABASE_URL": "postgresql://user:pass@host:5432/db",
                "ALLOWED_ORIGINS": "https://app.com,*,https://www.app.com",  # Wildcard in list
            },
            clear=True,
        ):
            with pytest.raises(ValueError, match="CORS wildcard"):
                ProductionConfigManager()

    def test_production_without_allowed_origins_fails(self):
        """Test that production without allowed_origins fails"""
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "production",
                "SECRET_KEY": "a" * 64,
                "DATABASE_URL": "postgresql://user:pass@host:5432/db",
                # No ALLOWED_ORIGINS or FRONTEND_URL
            },
            clear=True,
        ):
            with pytest.raises(ValueError, match="allowed_origins must be configured"):
                ProductionConfigManager()

    def test_production_with_specific_origins_passes(self):
        """Test that production with specific origins passes validation"""
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "production",
                "SECRET_KEY": "a" * 64,
                "DATABASE_URL": "postgresql://user:pass@host:5432/db",
                "ALLOWED_ORIGINS": "https://app.sanskritisetu.org,https://www.sanskritisetu.org",
                "SERENA_API_URL": "https://serena.example.com",
                "SEQ_THINKING_API_URL": "https://seq.example.com",
                "ENABLE_REAL_LLM": "true",  # Suppress LLM warning
            },
            clear=True,
        ):
            config = ProductionConfigManager()

            assert config.security is not None
            assert "https://app.sanskritisetu.org" in config.security.allowed_origins
            assert "https://www.sanskritisetu.org" in config.security.allowed_origins
            assert "*" not in config.security.allowed_origins

    def test_production_with_frontend_url_fallback(self):
        """Test that production uses FRONTEND_URL if ALLOWED_ORIGINS not set"""
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "production",
                "SECRET_KEY": "a" * 64,
                "DATABASE_URL": "postgresql://user:pass@host:5432/db",
                "FRONTEND_URL": "https://app.sanskritisetu.org",
                "SERENA_API_URL": "https://serena.example.com",
                "SEQ_THINKING_API_URL": "https://seq.example.com",
                "ENABLE_REAL_LLM": "true",
            },
            clear=True,
        ):
            config = ProductionConfigManager()

            assert config.security is not None
            assert config.security.allowed_origins == ["https://app.sanskritisetu.org"]
            assert "*" not in config.security.allowed_origins


class TestStagingCORSConfiguration:
    """Tests for staging CORS configuration"""

    def test_staging_with_wildcard_fails(self):
        """Test that staging with wildcard fails validation"""
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "staging",
                "SECRET_KEY": "a" * 64,
                "DATABASE_URL": "postgresql://user:pass@host:5432/db",
                "ALLOWED_ORIGINS": "*",
            },
            clear=True,
        ):
            with pytest.raises(ValueError, match="CORS wildcard"):
                ProductionConfigManager()

    def test_staging_with_specific_origins_passes(self):
        """Test that staging with specific origins passes"""
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "staging",
                "SECRET_KEY": "a" * 64,
                "DATABASE_URL": "postgresql://user:pass@host:5432/db",
                "ALLOWED_ORIGINS": "https://staging.sanskritisetu.org",
                "ENABLE_REAL_LLM": "true",
            },
            clear=True,
        ):
            config = ProductionConfigManager()

            assert config.security.allowed_origins == ["https://staging.sanskritisetu.org"]
            assert "*" not in config.security.allowed_origins


class TestDevelopmentCORSConfiguration:
    """Tests for development CORS configuration"""

    def test_development_allows_localhost(self):
        """Test that development automatically configures localhost origins"""
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "development",
                "SECRET_KEY": "dev-key",
                "DATABASE_URL": "sqlite:///./dev.db",
            },
            clear=True,
        ):
            config = ProductionConfigManager()

            assert config.security is not None
            assert "http://localhost:3000" in config.security.allowed_origins
            assert "http://localhost:8501" in config.security.allowed_origins
            assert "http://127.0.0.1:3000" in config.security.allowed_origins
            assert "http://127.0.0.1:8501" in config.security.allowed_origins

    def test_development_can_override_origins(self):
        """Test that development can override default localhost origins"""
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "development",
                "SECRET_KEY": "dev-key",
                "DATABASE_URL": "sqlite:///./dev.db",
                "ALLOWED_ORIGINS": "http://custom-dev-server:3000",
            },
            clear=True,
        ):
            config = ProductionConfigManager()

            assert config.security.allowed_origins == ["http://custom-dev-server:3000"]

    def test_development_wildcard_allowed(self):
        """Test that development CAN use wildcard (for local testing convenience)"""
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "development",
                "SECRET_KEY": "dev-key",
                "DATABASE_URL": "sqlite:///./dev.db",
                "ALLOWED_ORIGINS": "*",
            },
            clear=True,
        ):
            # Should not raise error in development
            config = ProductionConfigManager()

            assert config.security.allowed_origins == ["*"]
            # This is OK in development, but NOT in production/staging


class TestCORSOriginFormatValidation:
    """Tests for CORS origin format validation"""

    def test_http_origin_accepted(self):
        """Test that http:// origins are accepted"""
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "development",
                "SECRET_KEY": "dev-key",
                "DATABASE_URL": "sqlite:///./dev.db",
                "ALLOWED_ORIGINS": "http://localhost:3000",
            },
            clear=True,
        ):
            config = ProductionConfigManager()

            assert "http://localhost:3000" in config.security.allowed_origins

    def test_https_origin_accepted(self):
        """Test that https:// origins are accepted"""
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "development",
                "SECRET_KEY": "dev-key",
                "DATABASE_URL": "sqlite:///./dev.db",
                "ALLOWED_ORIGINS": "https://app.sanskritisetu.org",
            },
            clear=True,
        ):
            config = ProductionConfigManager()

            assert "https://app.sanskritisetu.org" in config.security.allowed_origins

    def test_invalid_origin_format_warning(self, caplog):
        """Test that invalid origin format logs warning"""
        import logging

        caplog.set_level(logging.WARNING)

        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "development",
                "SECRET_KEY": "dev-key",
                "DATABASE_URL": "sqlite:///./dev.db",
                "ALLOWED_ORIGINS": "invalid-origin-without-protocol",
            },
            clear=True,
        ):
            ProductionConfigManager()

            # Should log warning but not fail
            assert any("does not start with http://" in record.message for record in caplog.records)


class TestCORSMultipleOrigins:
    """Tests for multiple CORS origins"""

    def test_multiple_origins_comma_separated(self):
        """Test that multiple origins can be configured with commas"""
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "production",
                "SECRET_KEY": "a" * 64,
                "DATABASE_URL": "postgresql://user:pass@host:5432/db",
                "ALLOWED_ORIGINS": "https://app.sanskritisetu.org,https://www.sanskritisetu.org,https://admin.sanskritisetu.org",
                "SERENA_API_URL": "https://serena.example.com",
                "SEQ_THINKING_API_URL": "https://seq.example.com",
                "ENABLE_REAL_LLM": "true",
            },
            clear=True,
        ):
            config = ProductionConfigManager()

            assert len(config.security.allowed_origins) == 3
            assert "https://app.sanskritisetu.org" in config.security.allowed_origins
            assert "https://www.sanskritisetu.org" in config.security.allowed_origins
            assert "https://admin.sanskritisetu.org" in config.security.allowed_origins

    def test_multiple_origins_with_whitespace(self):
        """Test that whitespace in ALLOWED_ORIGINS is handled correctly"""
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "production",
                "SECRET_KEY": "a" * 64,
                "DATABASE_URL": "postgresql://user:pass@host:5432/db",
                "ALLOWED_ORIGINS": " https://app.com , https://www.app.com , https://admin.app.com ",
                "SERENA_API_URL": "https://serena.example.com",
                "SEQ_THINKING_API_URL": "https://seq.example.com",
                "ENABLE_REAL_LLM": "true",
            },
            clear=True,
        ):
            config = ProductionConfigManager()

            # Whitespace should be stripped
            assert "https://app.com" in config.security.allowed_origins
            assert "https://www.app.com" in config.security.allowed_origins
            assert "https://admin.app.com" in config.security.allowed_origins
            assert len(config.security.allowed_origins) == 3

    def test_empty_origin_entries_ignored(self):
        """Test that empty entries in ALLOWED_ORIGINS are ignored"""
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "production",
                "SECRET_KEY": "a" * 64,
                "DATABASE_URL": "postgresql://user:pass@host:5432/db",
                "ALLOWED_ORIGINS": "https://app.com,,https://www.app.com,,",
                "SERENA_API_URL": "https://serena.example.com",
                "SEQ_THINKING_API_URL": "https://seq.example.com",
                "ENABLE_REAL_LLM": "true",
            },
            clear=True,
        ):
            config = ProductionConfigManager()

            # Empty entries should be filtered out
            assert len(config.security.allowed_origins) == 2
            assert "https://app.com" in config.security.allowed_origins
            assert "https://www.app.com" in config.security.allowed_origins


class TestSecurityConfigDefaults:
    """Tests for SecurityConfig dataclass defaults"""

    def test_security_config_required_secret_key(self):
        """Test that SecurityConfig requires secret_key"""
        with pytest.raises(TypeError):
            # Should raise TypeError because secret_key is required
            SecurityConfig()

    def test_security_config_with_secret_key(self):
        """Test SecurityConfig with secret_key"""
        security = SecurityConfig(secret_key="test-secret-key")

        assert security.secret_key == "test-secret-key"
        assert security.jwt_algorithm == "HS256"
        assert security.jwt_expiry_hours == 24
        assert security.bcrypt_rounds == 12
        assert security.rate_limit_per_minute == 60
        assert security.enable_cors is True
        assert security.allowed_origins == []  # P0-6: Empty by default

    def test_security_config_custom_origins(self):
        """Test SecurityConfig with custom allowed_origins"""
        security = SecurityConfig(
            secret_key="test-key",
            allowed_origins=["https://app.com", "https://www.app.com"],
        )

        assert len(security.allowed_origins) == 2
        assert "https://app.com" in security.allowed_origins
        assert "*" not in security.allowed_origins


class TestRegressionPrevention:
    """Tests to prevent regression of P0-6 fix"""

    def test_wildcard_never_in_default(self):
        """CRITICAL: Test that wildcard is NEVER in default configuration"""
        # This is the core P0-6 fix - must never regress
        security = SecurityConfig(secret_key="test-key")

        assert security.allowed_origins != [
            "*"
        ], "CRITICAL P0-6: Default allowed_origins cannot be wildcard ['*']"
        assert (
            "*" not in security.allowed_origins
        ), "CRITICAL P0-6: Wildcard must not appear in default configuration"

    def test_production_validation_rejects_wildcard(self):
        """Test that production validation exists and rejects wildcard"""
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "production",
                "SECRET_KEY": "a" * 64,
                "DATABASE_URL": "postgresql://user:pass@host:5432/db",
                "ALLOWED_ORIGINS": "*",
            },
            clear=True,
        ):
            with pytest.raises(ValueError) as exc_info:
                ProductionConfigManager()

            # Must have specific error about CORS wildcard
            assert (
                "CORS wildcard" in str(exc_info.value) or "wildcard" in str(exc_info.value).lower()
            )

    def test_production_requires_explicit_origins(self):
        """Test that production requires explicit origin configuration"""
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "production",
                "SECRET_KEY": "a" * 64,
                "DATABASE_URL": "postgresql://user:pass@host:5432/db",
                # No ALLOWED_ORIGINS
            },
            clear=True,
        ):
            with pytest.raises(ValueError) as exc_info:
                ProductionConfigManager()

            # Must require explicit origins
            assert "allowed_origins must be configured" in str(exc_info.value)


class TestConfigurationExamples:
    """Tests showing correct configuration examples"""

    def test_correct_production_config_single_origin(self):
        """Example: Correct production config with single origin"""
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "production",
                "SECRET_KEY": "a" * 64,
                "DATABASE_URL": "postgresql://user:pass@host:5432/db",
                "FRONTEND_URL": "https://sanskritisetu.org",
                "SERENA_API_URL": "https://serena.example.com",
                "SEQ_THINKING_API_URL": "https://seq.example.com",
                "ENABLE_REAL_LLM": "true",
            },
            clear=True,
        ):
            config = ProductionConfigManager()

            assert config.security.allowed_origins == ["https://sanskritisetu.org"]

    def test_correct_production_config_multiple_origins(self):
        """Example: Correct production config with multiple origins"""
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "production",
                "SECRET_KEY": "a" * 64,
                "DATABASE_URL": "postgresql://user:pass@host:5432/db",
                "ALLOWED_ORIGINS": "https://sanskritisetu.org,https://app.sanskritisetu.org,https://admin.sanskritisetu.org",
                "SERENA_API_URL": "https://serena.example.com",
                "SEQ_THINKING_API_URL": "https://seq.example.com",
                "ENABLE_REAL_LLM": "true",
            },
            clear=True,
        ):
            config = ProductionConfigManager()

            assert len(config.security.allowed_origins) == 3
            assert all(origin.startswith("https://") for origin in config.security.allowed_origins)

    def test_correct_staging_config(self):
        """Example: Correct staging configuration"""
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "staging",
                "SECRET_KEY": "a" * 64,
                "DATABASE_URL": "postgresql://user:pass@host:5432/db",
                "ALLOWED_ORIGINS": "https://staging.sanskritisetu.org",
                "ENABLE_REAL_LLM": "true",
            },
            clear=True,
        ):
            config = ProductionConfigManager()

            assert config.security.allowed_origins == ["https://staging.sanskritisetu.org"]

    def test_correct_development_config(self):
        """Example: Correct development configuration"""
        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "development",
                "SECRET_KEY": "dev-key",
                "DATABASE_URL": "sqlite:///./dev.db",
            },
            clear=True,
        ):
            config = ProductionConfigManager()

            # Development automatically gets localhost origins
            assert len(config.security.allowed_origins) > 0
            assert any("localhost" in origin for origin in config.security.allowed_origins)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
