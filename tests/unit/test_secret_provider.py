"""Tests for secret provider."""

import os
import pytest
from unittest.mock import patch

from src.core.config.secret_provider import (
    SecretProvider,
    SecretSource,
    SecretAuditEntry,
    get_secret_provider,
    get_secret,
)


class TestSecretProvider:
    """Test SecretProvider for type safety and functionality."""

    @pytest.mark.unit
    def test_secret_provider_init(self):
        """SecretProvider initialization must set default values."""
        provider = SecretProvider(environment="development")

        assert provider.environment == "development"
        assert provider.cache_ttl == 3600
        assert provider.audit_enabled is True
        assert provider.strict_mode is False

    @pytest.mark.unit
    def test_get_secret_from_env_var(self):
        """get_secret must retrieve value from environment variable."""
        with patch.dict(os.environ, {"TEST_SECRET": "secret_value"}):
            provider = SecretProvider(environment="development")
            result = provider.get_secret("TEST_SECRET")

            assert result == "secret_value"

    @pytest.mark.unit
    def test_get_secret_returns_none_when_not_found(self):
        """get_secret must return None when secret not found."""
        provider = SecretProvider(environment="development")
        result = provider.get_secret("NONEXISTENT_SECRET")

        assert result is None

    @pytest.mark.unit
    def test_get_secret_with_default(self):
        """get_secret must return default when secret not found."""
        provider = SecretProvider(environment="development")
        result = provider.get_secret("NONEXISTENT_SECRET", default="default_value")

        assert result == "default_value"

    @pytest.mark.unit
    def test_is_sensitive_detects_sensitive_keys(self):
        """_is_sensitive must detect sensitive key patterns."""
        provider = SecretProvider(environment="development")

        assert provider._is_sensitive("JWT_SECRET") is True
        assert provider._is_sensitive("DATABASE_PASSWORD") is True
        assert provider._is_sensitive("API_KEY") is True
        assert provider._is_sensitive("REGULAR_CONFIG") is False

    @pytest.mark.unit
    def test_audit_log_entry_model(self):
        """SecretAuditEntry must have correct fields."""
        entry = SecretAuditEntry(
            timestamp="2026-05-08T00:00:00",
            action="RETRIEVED",
            secret_key="TEST_KEY",
            source=SecretSource.ENV_VAR,
            status="success",
        )

        assert entry.timestamp == "2026-05-08T00:00:00"
        assert entry.action == "RETRIEVED"
        assert entry.secret_key == "TEST_KEY"
        assert entry.source == SecretSource.ENV_VAR
        assert entry.status == "success"
        assert entry.user_id is None
        assert entry.environment is None

    @pytest.mark.unit
    def test_validate_production_secrets_returns_tuple(self):
        """validate_production_secrets must return tuple[bool, list[str]]."""
        provider = SecretProvider(environment="development")
        result = provider.validate_production_secrets()

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], bool)
        assert isinstance(result[1], list)

    @pytest.mark.unit
    def test_get_audit_trail_returns_list_of_dicts(self):
        """get_audit_trail must return list[dict[str, Any]]."""
        provider = SecretProvider(environment="development")

        # Add some audit entries
        with patch.dict(os.environ, {"TEST_SECRET": "value"}):
            provider.get_secret("TEST_SECRET")

        result = provider.get_audit_trail()

        assert isinstance(result, list)
        for entry in result:
            assert isinstance(entry, dict)

    @pytest.mark.unit
    def test_get_secret_provider_returns_singleton(self):
        """get_secret_provider must return same instance."""
        provider1 = get_secret_provider(environment="development")
        provider2 = get_secret_provider()

        assert provider1 is provider2

    @pytest.mark.unit
    def test_get_secret_function_uses_provider(self):
        """get_secret convenience function must use the global provider."""
        with patch.dict(os.environ, {"TEST_KEY": "test_value"}):
            result = get_secret("TEST_KEY")

            assert result == "test_value"

    @pytest.mark.unit
    def test_cache_stores_and_retrieves_secrets(self):
        """cache must store secrets and return cached values."""
        provider = SecretProvider(environment="development")

        with patch.dict(os.environ, {"CACHED_SECRET": "cached_value"}):
            # First call - retrieves from env
            result1 = provider.get_secret("CACHED_SECRET")
            # Second call - retrieves from cache
            result2 = provider.get_secret("CACHED_SECRET")

            assert result1 == "cached_value"
            assert result2 == "cached_value"
            assert "CACHED_SECRET" in provider.cache

    @pytest.mark.unit
    def test_get_from_file_secrets_returns_tuple(self):
        """_get_from_file_secrets must return tuple[str | None, SecretSource]."""
        provider = SecretProvider(environment="development")
        result = provider._get_from_file_secrets("NONEXISTENT")

        assert isinstance(result, tuple)
        assert len(result) == 2
        # (value, source)
        assert result[0] is None
        assert isinstance(result[1], SecretSource)
