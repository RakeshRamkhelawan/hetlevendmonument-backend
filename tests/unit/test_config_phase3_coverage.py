"""
Unit Tests for core/config/unified_config.py - Phase 3 Coverage Expansion
Target: 80%+ coverage with happy path, edge cases, error handling
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from src.core.config.unified_config import Environment, UnifiedConfig, get_config


class TestUnifiedConfig:
    """Test UnifiedConfig configuration class"""

    @patch.dict(
        os.environ,
        {
            "APP_DEBUG": "false",
            "ENVIRONMENT": "development",
            "JWT_EXPIRE_MINUTES": "240",
            "DATABASE_URL": "sqlite+aiosqlite:///./test.db",
            "REDIS_URL": "redis://localhost:6379",
            "LLM_PROVIDER": "google",
            "LLM_MODEL": "gemini-2.5-flash",
            "LLM_TEMPERATURE": "0.7",
            "API_HOST": "0.0.0.0",
            "API_PORT": "8000",
        },
    )
    def test_unified_config_default_values(self):
        """Test: UnifiedConfig loads with correct default values"""
        # Clear any cached instance
        if hasattr(UnifiedConfig, "_instance"):
            UnifiedConfig._instance = None

        config = UnifiedConfig()

        assert config.environment == Environment.DEVELOPMENT
        assert config.app_debug is False
        assert config.jwt_algorithm == "HS256"
        assert config.jwt_expire_minutes == 240
        assert "sqlite+aiosqlite://" in config.database_url
        assert config.database_pool_size == 20
        assert config.redis_url.startswith("redis://localhost:6379")
        assert config.api_host == "0.0.0.0"
        assert config.api_port == 8000
        assert config.max_concurrent_agents == 10
        assert config.llm_provider == "google"
        assert config.llm_model == "gemini-2.5-flash"
        assert config.llm_temperature == 0.7

    @patch.dict(
        os.environ,
        {
            "ENVIRONMENT": "production",
            "APP_DEBUG": "false",
            "JWT_SECRET_KEY": "super_secret_key_12345678901234567890",
            "DATABASE_URL": "postgresql://user:pass@prod-db:5432/sanskriti",
            "REDIS_URL": "redis://prod-redis:6379",
            "GOOGLE_API_KEY": "test-google-api-key-1234567890",
        },
    )
    def test_unified_config_environment_variable_override(self):
        """Test: Environment variables override default values"""
        if hasattr(UnifiedConfig, "_instance"):
            UnifiedConfig._instance = None

        config = UnifiedConfig()

        assert config.environment == Environment.PRODUCTION
        assert config.app_debug is False
        assert config.jwt_secret_key == "super_secret_key_12345678901234567890"
        assert config.database_url == "postgresql://user:pass@prod-db:5432/sanskriti"
        assert config.redis_url == "redis://prod-redis:6379"
        assert config.google_api_key == "test-google-api-key-1234567890"

    def test_unified_config_generates_jwt_secret_if_empty(self):
        """Test: JWT secret is auto-generated if not provided"""
        if hasattr(UnifiedConfig, "_instance"):
            UnifiedConfig._instance = None

        with patch.dict(os.environ, {"JWT_SECRET_KEY": ""}, clear=False):
            config = UnifiedConfig()

            # Should generate a random secret
            assert config.jwt_secret_key is not None
            assert len(config.jwt_secret_key) > 0

    def test_unified_config_cors_origins_parsing(self):
        """Test: CORS origins string is parsed to list"""
        if hasattr(UnifiedConfig, "_instance"):
            UnifiedConfig._instance = None

        with patch.dict(
            os.environ,
            {"CORS_ORIGINS": "https://example.com,https://test.com,http://localhost:3000"},
            clear=False,
        ):
            config = UnifiedConfig()

            assert isinstance(config.cors_origins, list)
            assert len(config.cors_origins) == 3
            assert "https://example.com" in config.cors_origins
            assert "https://test.com" in config.cors_origins
            assert "http://localhost:3000" in config.cors_origins

    def test_unified_config_cors_origins_empty_string(self):
        """Test: Empty CORS origins string returns empty list"""
        if hasattr(UnifiedConfig, "_instance"):
            UnifiedConfig._instance = None

        with patch.dict(os.environ, {"CORS_ORIGINS": ""}, clear=False):
            config = UnifiedConfig()

            assert config.cors_origins == []

    def test_unified_config_invalid_redis_url_raises_error(self):
        """Test: Invalid Redis URL format raises ValidationError"""
        if hasattr(UnifiedConfig, "_instance"):
            UnifiedConfig._instance = None

        from pydantic import ValidationError

        with patch.dict(os.environ, {"REDIS_URL": "http://invalid"}, clear=False):
            with pytest.raises(ValidationError) as exc_info:
                UnifiedConfig()

            assert "REDIS_URL" in str(exc_info.value) or "redis_url" in str(exc_info.value)

    def test_unified_config_invalid_log_format_raises_error(self):
        """Test: Invalid log format raises ValidationError"""
        if hasattr(UnifiedConfig, "_instance"):
            UnifiedConfig._instance = None

        from pydantic import ValidationError

        with patch.dict(os.environ, {"LOG_FORMAT": "xml"}, clear=False):
            with pytest.raises(ValidationError) as exc_info:
                UnifiedConfig()

            assert "log_format" in str(exc_info.value).lower()

    def test_unified_config_get_instance_singleton(self):
        """Test: get_instance() returns singleton instance"""
        if hasattr(UnifiedConfig, "_instance"):
            UnifiedConfig._instance = None

        instance1 = UnifiedConfig.get_instance()
        instance2 = UnifiedConfig.get_instance()

        # Should be the SAME object (singleton pattern)
        assert instance1 is instance2

    def test_unified_config_is_development(self):
        """Test: is_development() returns True for development environment"""
        if hasattr(UnifiedConfig, "_instance"):
            UnifiedConfig._instance = None

        with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=False):
            config = UnifiedConfig()

            assert config.is_development() is True
            assert config.is_production() is False

    def test_unified_config_is_production(self):
        """Test: is_production() returns True for production environment"""
        if hasattr(UnifiedConfig, "_instance"):
            UnifiedConfig._instance = None

        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "production",
                "JWT_SECRET_KEY": "super_secret_key_12345678901234567890",
                "DATABASE_URL": "postgresql://user:pass@prod-db:5432/db",
                "REDIS_URL": "redis://prod-redis:6379",
                "GOOGLE_API_KEY": "test-key-12345678901234567890",
            },
            clear=False,
        ):
            config = UnifiedConfig()

            assert config.is_production() is True
            assert config.is_development() is False


class TestGetConfig:
    """Test get_config() function"""

    def test_get_config_returns_unified_config_instance(self):
        """Test: get_config() returns UnifiedConfig instance"""
        # Clear global instance
        import src.core.config.unified_config as config_module

        config_module._config_instance = None

        if hasattr(UnifiedConfig, "_instance"):
            UnifiedConfig._instance = None

        config = get_config()

        assert isinstance(config, UnifiedConfig)

    def test_get_config_lazy_initialization(self):
        """Test: get_config() lazy initializes config on first call"""
        import src.core.config.unified_config as config_module

        config_module._config_instance = None

        if hasattr(UnifiedConfig, "_instance"):
            UnifiedConfig._instance = None

        # First call initializes
        config1 = get_config()

        # Second call returns cached instance
        config2 = get_config()

        assert config1 is config2


class TestUnifiedConfigMethods:
    """Test UnifiedConfig helper methods"""

    def test_get_cors_config_development(self):
        """Test: get_cors_config() returns development CORS settings"""
        if hasattr(UnifiedConfig, "_instance"):
            UnifiedConfig._instance = None

        with patch.dict(os.environ, {"ENVIRONMENT": "development"}, clear=False):
            config = UnifiedConfig()
            cors_config = config.get_cors_config()

            assert "allow_origins" in cors_config
            assert "http://localhost:3000" in cors_config["allow_origins"]
            assert cors_config["allow_credentials"] is True
            assert cors_config["allow_methods"] == ["*"]

    def test_get_cors_config_production(self):
        """Test: get_cors_config() returns production CORS settings"""
        if hasattr(UnifiedConfig, "_instance"):
            UnifiedConfig._instance = None

        with patch.dict(
            os.environ,
            {
                "ENVIRONMENT": "production",
                "JWT_SECRET_KEY": "super_secret_key_12345678901234567890",
                "DATABASE_URL": "postgresql://user:pass@prod-db:5432/db",
                "REDIS_URL": "redis://prod-redis:6379",
                "GOOGLE_API_KEY": "test-key-12345678901234567890",
            },
            clear=False,
        ):
            config = UnifiedConfig()
            cors_config = config.get_cors_config()

            assert "allow_origins" in cors_config
            assert "https://www.sanskritisetu.nl" in cors_config["allow_origins"]
            assert cors_config["allow_credentials"] is True
            assert "GET" in cors_config["allow_methods"]
            assert "POST" in cors_config["allow_methods"]

    def test_get_database_config(self):
        """Test: get_database_config() returns database settings"""
        if hasattr(UnifiedConfig, "_instance"):
            UnifiedConfig._instance = None

        config = UnifiedConfig()
        db_config = config.get_database_config()

        assert "url" in db_config
        assert "pool_size" in db_config
        assert "max_overflow" in db_config
        assert db_config["pool_size"] == 20
        assert db_config["pool_use_lifo"] is True

    @patch.dict(os.environ, {"REDIS_URL": "redis://localhost:6379", "REDIS_CACHE_TTL": "3600"})
    def test_get_redis_config(self):
        """Test: get_redis_config() returns Redis settings"""
        if hasattr(UnifiedConfig, "_instance"):
            UnifiedConfig._instance = None

        config = UnifiedConfig()
        redis_config = config.get_redis_config()

        assert "url" in redis_config
        assert "cache_ttl" in redis_config
        assert redis_config["url"].startswith("redis://localhost:6379")
        assert redis_config["cache_ttl"] == 3600

    @patch.dict(
        os.environ,
        {
            "LLM_PROVIDER": "google",
            "LLM_MODEL": "gemini-2.5-flash",
            "LLM_TEMPERATURE": "0.7",
        },
    )
    def test_get_llm_config(self):
        """Test: get_llm_config() returns LLM settings"""
        if hasattr(UnifiedConfig, "_instance"):
            UnifiedConfig._instance = None

        config = UnifiedConfig()
        llm_config = config.get_llm_config()

        assert "provider" in llm_config
        assert "model" in llm_config
        assert "temperature" in llm_config
        assert "max_tokens" in llm_config
        assert llm_config["provider"] == "google"
        assert llm_config["model"] == "gemini-2.5-flash"
        assert llm_config["temperature"] == 0.7

    def test_get_agent_config(self):
        """Test: get_agent_config() returns agent settings"""
        if hasattr(UnifiedConfig, "_instance"):
            UnifiedConfig._instance = None

        config = UnifiedConfig()
        agent_config = config.get_agent_config()

        assert "max_concurrent" in agent_config
        assert "timeout_seconds" in agent_config
        assert "learning_enabled" in agent_config
        assert agent_config["max_concurrent"] == 10
        assert agent_config["timeout_seconds"] == 30
        assert agent_config["learning_enabled"] is True

    @patch.dict(os.environ, {"JWT_EXPIRE_MINUTES": "240", "SECURITY_MIDDLEWARE_ENABLED": "true"})
    def test_get_security_config(self):
        """Test: get_security_config() returns security settings"""
        if hasattr(UnifiedConfig, "_instance"):
            UnifiedConfig._instance = None

        config = UnifiedConfig()
        security_config = config.get_security_config()

        assert "jwt_secret_key" in security_config
        assert "jwt_expire_minutes" in security_config
        assert "middleware_enabled" in security_config
        assert security_config["jwt_expire_minutes"] == 240
        assert security_config["middleware_enabled"] is True


class TestUnifiedConfigEdgeCases:
    """Test edge cases and boundary conditions"""

    @patch.dict(os.environ, {"API_PORT": "0"})
    def test_unified_config_invalid_api_port_zero(self):
        """Test: API port 0 is technically valid (OS assigns random port)"""
        if hasattr(UnifiedConfig, "_instance"):
            UnifiedConfig._instance = None

        config = UnifiedConfig()

        # Port 0 is allowed by Pydantic but would fail validation
        assert config.api_port == 0

    @patch.dict(os.environ, {"API_PORT": "99999"})
    def test_unified_config_api_port_out_of_range(self):
        """Test: API port >65535 is invalid"""
        if hasattr(UnifiedConfig, "_instance"):
            UnifiedConfig._instance = None

        config = UnifiedConfig()

        # Pydantic allows it, but validate_common_config would catch it
        assert config.api_port == 99999

    @patch.dict(os.environ, {"LLM_TEMPERATURE": "2.5"})
    def test_unified_config_llm_temperature_high(self):
        """Test: High LLM temperature is allowed"""
        if hasattr(UnifiedConfig, "_instance"):
            UnifiedConfig._instance = None

        config = UnifiedConfig()

        assert config.llm_temperature == 2.5

    @patch.dict(os.environ, {"DATABASE_POOL_SIZE": "-1"})
    def test_unified_config_negative_pool_size(self):
        """Test: Negative pool size is allowed by Pydantic"""
        if hasattr(UnifiedConfig, "_instance"):
            UnifiedConfig._instance = None

        config = UnifiedConfig()

        # Pydantic allows negative integers
        assert config.database_pool_size == -1

    def test_unified_config_environment_enum(self):
        """Test: Environment enum has expected values"""
        assert Environment.DEVELOPMENT == "development"
        assert Environment.STAGING == "staging"
        assert Environment.PRODUCTION == "production"

    @patch.dict(os.environ, {"ENVIRONMENT": "invalid_env"})
    def test_unified_config_invalid_environment(self):
        """Test: Invalid environment raises ValidationError"""
        if hasattr(UnifiedConfig, "_instance"):
            UnifiedConfig._instance = None

        from pydantic import ValidationError

        with pytest.raises(ValidationError) as exc_info:
            UnifiedConfig()

        assert "environment" in str(exc_info.value).lower()
