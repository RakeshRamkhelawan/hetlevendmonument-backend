"""
Comprehensive tests for src/core/config/config.py
Coverage target: 100% of config module
"""

from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError


class TestSettings:
    """Test Settings class configuration loading"""

    def test_settings_initialization_with_env_vars(self, monkeypatch):
        """Test Settings loads from environment variables"""
        # Arrange
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/test")
        # Redis port updated from 6379 to 6380 -- dit commentaar stond eerder IN de
        # string, waardoor de waarde een URL-fragment kreeg en de poort onparsebaar werd
        # ("6380  "). Gevonden 2026-08-01 door
        # tests/architecture/test_env_url_values_are_parseable.py.
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6380")
        monkeypatch.setenv("SECRET_KEY", "test-secret-key-12345")
        monkeypatch.setenv("ENVIRONMENT", "testing")
        monkeypatch.setenv("DEBUG", "true")

        # Act
        from src.core.config.config import Settings

        settings = Settings()

        # Assert
        assert settings.database_url == "postgresql://localhost/test"
        assert settings.redis_url == "redis://localhost:6380"
        assert settings.secret_key == "test-secret-key-12345"
        assert settings.environment == "testing"
        assert settings.debug is True

    def test_settings_default_values(self, monkeypatch):
        """Test Settings applies default values"""
        # Arrange
        monkeypatch.setenv("DATABASE_URL", "sqlite:///test.db")
        monkeypatch.setenv("REDIS_URL", "redis://localhost")
        monkeypatch.setenv("SECRET_KEY", "secret")
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("DEBUG", raising=False)

        # Act
        from src.core.config.config import Settings

        settings = Settings(_env_file=None)

        # Assert
        assert settings.environment == "development"  # Default value
        assert settings.debug is False  # Default value

    def test_settings_case_insensitive(self, monkeypatch):
        """Test Settings is case insensitive for env vars"""
        # Arrange
        monkeypatch.setenv("database_url", "postgresql://test")
        monkeypatch.setenv("REDIS_URL", "redis://test")
        monkeypatch.setenv("secret_key", "key123")

        # Act
        from src.core.config.config import Settings

        settings = Settings()

        # Assert
        assert settings.database_url == "postgresql://test"
        assert settings.redis_url == "redis://test"
        assert settings.secret_key == "key123"

    def test_settings_extra_fields_ignored(self, monkeypatch):
        """Test Settings ignores extra environment variables"""
        # Arrange
        monkeypatch.setenv("DATABASE_URL", "sqlite:///test.db")
        monkeypatch.setenv("REDIS_URL", "redis://localhost")
        monkeypatch.setenv("SECRET_KEY", "secret")
        monkeypatch.setenv("UNKNOWN_FIELD", "should-be-ignored")
        monkeypatch.setenv("RANDOM_VAR", "also-ignored")

        # Act
        from src.core.config.config import Settings

        settings = Settings()

        # Assert - No error raised, extra fields ignored
        assert not hasattr(settings, "unknown_field")
        assert not hasattr(settings, "random_var")

    def test_settings_required_fields_validation(self, monkeypatch):
        """Test Settings uses empty-string defaults when env vars are not set"""
        # Arrange - Clear all env vars
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("REDIS_URL", raising=False)
        monkeypatch.delenv("SECRET_KEY", raising=False)

        # Act — bypass .env file so only env vars (deleted above) and defaults apply
        from src.core.config.config import Settings

        settings = Settings(_env_file=None)

        # Assert - fields default to empty strings (no ValidationError raised)
        assert settings.database_url == ""
        assert settings.redis_url == ""
        assert settings.secret_key == ""


class TestGetSettings:
    """Test get_settings() function"""

    def test_get_settings_returns_settings_instance(self, monkeypatch):
        """Test get_settings() returns Settings instance"""
        # Arrange
        monkeypatch.setenv("DATABASE_URL", "sqlite:///test.db")
        monkeypatch.setenv("REDIS_URL", "redis://localhost")
        monkeypatch.setenv("SECRET_KEY", "test-key")

        # Reset global settings
        import src.core.config.config as config_module

        config_module._settings = None

        # Act
        from src.core.config.config import Settings, get_settings

        settings = get_settings()

        # Assert
        assert isinstance(settings, Settings)
        assert settings.database_url == "sqlite:///test.db"

    def test_get_settings_caches_instance(self, monkeypatch):
        """Test get_settings() returns same instance on multiple calls (singleton)"""
        # Arrange
        monkeypatch.setenv("DATABASE_URL", "sqlite:///test.db")
        monkeypatch.setenv("REDIS_URL", "redis://localhost")
        monkeypatch.setenv("SECRET_KEY", "test-key")

        # Reset global settings
        import src.core.config.config as config_module

        config_module._settings = None

        # Act
        from src.core.config.config import get_settings

        settings1 = get_settings()
        settings2 = get_settings()

        # Assert - Same instance returned (singleton pattern)
        assert settings1 is settings2

    def test_get_settings_lazy_initialization(self, monkeypatch):
        """Test get_settings() initializes settings only when first called"""
        # Arrange
        monkeypatch.setenv("DATABASE_URL", "sqlite:///test.db")
        monkeypatch.setenv("REDIS_URL", "redis://localhost")
        monkeypatch.setenv("SECRET_KEY", "test-key")

        # Reset global settings
        import src.core.config.config as config_module

        config_module._settings = None

        # Act & Assert - Settings not initialized yet
        assert config_module._settings is None

        from src.core.config.config import get_settings

        settings = get_settings()

        # Assert - Settings now initialized
        assert config_module._settings is not None
        assert config_module._settings is settings


class TestConfigModule:
    """Test module-level configuration behavior"""

    def test_module_exports(self):
        """Test module exports expected classes and functions"""
        # Act
        import src.core.config.config as config_module

        # Assert
        assert hasattr(config_module, "Settings")
        assert hasattr(config_module, "get_settings")
        assert hasattr(config_module, "_settings")

    def test_settings_env_file_encoding(self, monkeypatch):
        """Test Settings uses UTF-8 encoding for .env file"""
        # Arrange
        monkeypatch.setenv("DATABASE_URL", "sqlite:///test.db")
        monkeypatch.setenv("REDIS_URL", "redis://localhost")
        monkeypatch.setenv("SECRET_KEY", "test-key-üñíçödé")  # Unicode characters

        # Act
        from src.core.config.config import Settings

        settings = Settings()

        # Assert
        assert "üñíçödé" in settings.secret_key

    def test_settings_model_config(self):
        """Test Settings has correct Pydantic model config"""
        # Act
        from src.core.config.config import Settings

        # Assert
        assert Settings.model_config["env_file"] == ".env"
        assert Settings.model_config["env_file_encoding"] == "utf-8"
        assert Settings.model_config["case_sensitive"] is False
        assert Settings.model_config["extra"] == "ignore"
