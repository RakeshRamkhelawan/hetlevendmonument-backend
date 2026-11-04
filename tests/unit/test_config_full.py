import os
from unittest.mock import MagicMock, patch

import pytest

from src import config as config_module
from src.config import Config, initialize_config


class TestConfigFull:
    """Comprehensive tests for Config class"""

    @pytest.fixture
    def config_instance(self):
        # Patch load_dotenv to prevent .env from polluting os.environ for other tests
        with patch("src.config.load_dotenv"):
            return Config()

    def test_init_loads_env(self, config_instance):
        assert config_instance._config_data is not None

    @patch.dict(os.environ, {"DATABASE_URL": "postgres://test"})
    def test_load_dotenv_files(self):
        # Config now reads directly from os.environ; load_dotenv is a legacy re-export
        cfg = Config()
        assert cfg.get("DATABASE_URL") == "postgres://test"

    def test_get_methods(self, config_instance):
        # Mock the internal data
        config_instance._config_data = {
            "DATABASE_URL": "postgres://user:pass@host:5432/db",
            "REDIS_URL": "redis://localhost:6380  # Redis port updated from 6379 to 6380",
            "ENVIRONMENT": "development",
            "DEBUG": True,
            "API_HOST": "127.0.0.1",
            "API_PORT": 8000,
            "API_BASE_URL": "http://test-api",
            "SECRET_KEY": "secret",
            "LLM_PROVIDER": "google",
            "ENABLE_SERENA_MCP": True,
            "SERENA_SERVICE_PATH": "services/serena",
        }

        assert config_instance.get_database_url() == "postgres://user:pass@host:5432/db"
        assert (
            config_instance.get_redis_url()
            == "redis://localhost:6380  # Redis port updated from 6379 to 6380"
        )
        assert config_instance.is_development() is True
        assert config_instance.is_debug() is True
        assert config_instance.is_serena_mcp_enabled() is True
        assert config_instance.get_serena_service_path() == "services/serena"

        # Test defaults/fallback in get()
        assert config_instance.get("NON_EXISTENT", "default") == "default"

    def test_production_config_getters(self, config_instance):
        # Mock production config
        mock_prod = MagicMock()
        mock_prod.tool_broker.serena_api_url = "http://prod-serena"
        mock_prod.tool_broker.serena_api_key = "prod-key"
        mock_prod.tool_broker.seq_thinking_api_url = "http://prod-seq"
        mock_prod.tool_broker.seq_thinking_api_key = "prod-seq-key"
        mock_prod.tool_broker.tool_broker_service_timeout = 60
        mock_prod.security.jwt_algorithm = "RS256"
        mock_prod.security.jwt_expiry_hours = 1

        config_instance.production_config = mock_prod

        assert config_instance.get_serena_api_url() == "http://prod-serena"
        assert config_instance.get_serena_api_key() == "prod-key"
        assert config_instance.get_seq_thinking_api_url() == "http://prod-seq"
        assert config_instance.get_seq_thinking_api_key() == "prod-seq-key"
        assert config_instance.get_tool_broker_service_timeout() == 60
        assert config_instance.get_jwt_algorithm() == "RS256"
        assert config_instance.get_access_token_expire_minutes() == 60

    def test_fallback_getters_no_prod_config(self, config_instance):
        config_instance.production_config = None

        with patch.dict(
            os.environ,
            {
                "SERENA_API_URL": "http://env-serena",
                "SERENA_API_KEY": "env-key",
                "SEQ_THINKING_API_URL": "http://env-seq",
                "SEQ_THINKING_API_KEY": "env-seq-key",
                "TOOL_BROKER_SERVICE_TIMEOUT": "45",
                "JWT_ALGORITHM": "HS512",
                "ACCESS_TOKEN_EXPIRE_MINUTES": "120",
            },
        ):
            assert config_instance.get_serena_api_url() == "http://env-serena"
            assert config_instance.get_serena_api_key() == "env-key"
            assert config_instance.get_seq_thinking_api_url() == "http://env-seq"
            assert config_instance.get_seq_thinking_api_key() == "env-seq-key"
            assert config_instance.get_tool_broker_service_timeout() == 45
            assert config_instance.get_jwt_algorithm() == "HS512"
            assert config_instance.get_access_token_expire_minutes() == 120

    @patch("src.config.ProductionConfigManager")
    def test_initialize_production_config_success(self, MockProdConfig, config_instance):
        mock_manager = MockProdConfig.return_value
        mock_manager._load_configuration = MagicMock()

        assert config_instance.initialize_production_config() is True
        mock_manager._load_configuration.assert_called_once()
        assert config_instance.production_config is not None

    @patch("src.config.ProductionConfigManager")
    def test_initialize_production_config_no_method(self, MockProdConfig, config_instance):
        mock_manager = MockProdConfig.return_value
        del mock_manager._load_configuration  # Simulate method missing

        # Should still return True but print warning
        assert config_instance.initialize_production_config() is True

    @patch("src.config.ProductionConfigManager")
    def test_initialize_production_config_failure(self, MockProdConfig, config_instance):
        MockProdConfig.side_effect = Exception("Config Error")

        assert config_instance.initialize_production_config() is False
        assert config_instance.production_config is None

    @patch("src.config.config.initialize_production_config")
    def test_initialize_config_global(self, mock_init_prod):
        mock_init_prod.return_value = True
        assert initialize_config() is True
        mock_init_prod.assert_called_once()

    @patch("src.config.config.initialize_production_config")
    def test_initialize_config_global_failure(self, mock_init_prod):
        mock_init_prod.side_effect = Exception("Init Fail")
        assert initialize_config() is False

    def test_serena_check_is_skipped_when_mcp_disabled(self):
        """OP-112: production boot no longer requires SERENA_API_URL when Serena is off.

        The check used to run unconditionally, so a production worker that never calls
        Serena still had to fake a non-localhost SERENA_API_URL to boot at all.
        """
        env = {
            "ENVIRONMENT": "production",
            "REDIS_URL": "redis://prod-redis:6379",
            "API_BASE_URL": "https://api.example.com",
            "ENABLE_SERENA_MCP": "false",
        }
        with patch("src.config.load_dotenv"), patch.dict(os.environ, env, clear=True):
            Config()  # must not raise

    def test_serena_check_still_enforced_when_mcp_enabled(self):
        """OP-112 counter-proof: enabling Serena MCP keeps the fail-fast guard live."""
        env = {
            "ENVIRONMENT": "production",
            "REDIS_URL": "redis://prod-redis:6379",
            "API_BASE_URL": "https://api.example.com",
            "ENABLE_SERENA_MCP": "true",
        }
        with patch("src.config.load_dotenv"), patch.dict(os.environ, env, clear=True):
            with pytest.raises(ValueError, match="SERENA_API_URL"):
                Config()


class TestConfigGlobalFunctions:
    """Test global convenience functions in src.config"""

    @patch("src.config.config")
    def test_global_getters(self, mock_config):
        mock_config.get_database_url.return_value = "db-url"
        mock_config.get_redis_url.return_value = "redis-url"
        mock_config.is_development.return_value = True
        mock_config.get.return_value = "http://api"
        mock_config.is_serena_mcp_enabled.return_value = True
        mock_config.get_serena_service_path.return_value = "path"
        mock_config.get_serena_api_url.return_value = "url"
        mock_config.get_serena_api_key.return_value = "key"
        mock_config.get_seq_thinking_api_url.return_value = "seq-url"
        mock_config.get_seq_thinking_api_key.return_value = "seq-key"
        mock_config.get_tool_broker_service_timeout.return_value = 30
        mock_config.get_jwt_algorithm.return_value = "alg"
        mock_config.get_access_token_expire_minutes.return_value = 60

        assert config_module.get_database_url() == "db-url"
        assert config_module.get_redis_url() == "redis-url"
        assert config_module.is_development() is True
        assert config_module.get_api_base_url() == "http://api"
        assert config_module.is_serena_mcp_enabled() is True
        assert config_module.get_serena_service_path() == "path"
        assert config_module.get_serena_api_url() == "url"
        assert config_module.get_serena_api_key() == "key"
        assert config_module.get_seq_thinking_api_url() == "seq-url"
        assert config_module.get_seq_thinking_api_key() == "seq-key"
        assert config_module.get_tool_broker_service_timeout() == 30
        assert config_module.get_jwt_algorithm() == "alg"
        assert config_module.get_access_token_expire_minutes() == 60
