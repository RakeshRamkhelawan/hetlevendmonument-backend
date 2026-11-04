"""Unit tests for SECRET_KEY hardening in ProductionConfigManager."""

import os
from unittest.mock import patch

import pytest

from src.core.config.production_config import ProductionConfigManager


def _base_env(environment: str, secret_key: str | None) -> dict[str, str]:
    env = {
        "ENVIRONMENT": environment,
        "DATABASE_URL": "postgresql://user:pass@host:5432/db",
        "ALLOWED_ORIGINS": "https://app.sanskritisetu.org",
        "SERENA_API_URL": "https://serena.example.com",
        "SEQ_THINKING_API_URL": "https://seq.example.com",
    }
    if secret_key is not None:
        env["SECRET_KEY"] = secret_key
    return env


class TestProductionSecretKeyValidation:
    """Tests for production and staging SECRET_KEY validation."""

    def test_production_missing_secret_key_fails_fast(self):
        with patch.dict(os.environ, _base_env("production", None), clear=True):
            with pytest.raises(ValueError, match="SECRET_KEY"):
                ProductionConfigManager()

    def test_production_short_secret_key_fails_fast(self):
        with patch.dict(os.environ, _base_env("production", "short-key"), clear=True):
            with pytest.raises(ValueError, match="SECRET_KEY"):
                ProductionConfigManager()

    def test_staging_insecure_default_secret_key_fails_fast(self):
        with patch.dict(os.environ, _base_env("staging", "changeme"), clear=True):
            with pytest.raises(ValueError, match="SECRET_KEY"):
                ProductionConfigManager()

    def test_production_strong_secret_key_passes(self):
        with patch.dict(os.environ, _base_env("production", "a" * 64), clear=True):
            config = ProductionConfigManager()

            assert config.security is not None
            assert config.security.secret_key == "a" * 64


class TestDevelopmentSecretKeyValidation:
    """Tests for development SECRET_KEY behavior."""

    def test_development_short_secret_key_does_not_fail(self):
        with patch.dict(os.environ, _base_env("development", "dev-key"), clear=True):
            config = ProductionConfigManager()

            assert config.security is not None
            assert config.security.secret_key == "dev-key"
