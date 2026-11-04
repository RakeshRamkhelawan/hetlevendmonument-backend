import os
from unittest.mock import patch

import pytest

from src.config import Config, get_serena_service_path, is_serena_mcp_enabled


class TestSerenaConfig:
    """Test Serena MCP configuration settings"""

    @patch.dict(os.environ, {"ENABLE_SERENA_MCP": "true", "SERENA_SERVICE_PATH": "custom/path"})
    def test_config_values_from_env(self):
        config = Config()
        assert config.is_serena_mcp_enabled() is True
        assert config.get_serena_service_path() == "custom/path"

    @patch.dict(os.environ, {}, clear=True)
    def test_config_defaults(self):
        config = Config()
        # Default should be False as per our change (though safe fallback)
        assert config.is_serena_mcp_enabled() is False
        assert config.get_serena_service_path() == "services/serena"

    @patch.dict(os.environ, {"ENABLE_SERENA_MCP": "false"})
    def test_global_accessors_disabled(self):
        # Reset the global config instance to pick up new env vars?
        # The global 'config' object is instantiated at module level in src.config.
        # So we might need to patch the 'src.config.config' object or its method.

        with patch(
            "src.config.config.get",
            side_effect=lambda k, d=None: False if k == "ENABLE_SERENA_MCP" else d,
        ):
            assert is_serena_mcp_enabled() is False

    @patch.dict(os.environ, {"ENABLE_SERENA_MCP": "true"})
    def test_global_accessors_enabled(self):
        with patch(
            "src.config.config.get",
            side_effect=lambda k, d=None: True if k == "ENABLE_SERENA_MCP" else "services/serena",
        ):
            assert is_serena_mcp_enabled() is True
            assert get_serena_service_path() == "services/serena"
