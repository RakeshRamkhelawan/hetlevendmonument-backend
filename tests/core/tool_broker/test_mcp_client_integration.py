import os
from pathlib import Path
from unittest.mock import ANY, MagicMock, patch

import pytest

pytestmark = pytest.mark.integration

# We need to import the module under test
from src.core.tool_broker import mcp_client
from src.core.tool_broker.mcp_client import MCPServerConfig, initialize_mcp_pool


@pytest.mark.asyncio
class TestMCPClientIntegration:
    async def test_initialize_mcp_pool_disabled_serena(self):
        """Test initialization when Serena is disabled"""
        mock_pool = MagicMock()

        with (
            patch("src.core.tool_broker.mcp_client.get_mcp_pool", return_value=mock_pool),
            patch("src.config.is_serena_mcp_enabled", return_value=False),
        ):
            await initialize_mcp_pool()

            # Check that register was called (for sequential thinking)
            assert mock_pool.register.called

            # Verify Serena was NOT registered
            # Iterate through calls to register
            registered_configs = [args[0] for args, _ in mock_pool.register.call_args_list]
            serena_configs = [c for c in registered_configs if c.name == "serena"]
            assert len(serena_configs) == 0

            # Verify Sequential Thinking WAS registered
            seq_configs = [c for c in registered_configs if c.name == "sequential-thinking"]
            assert len(seq_configs) == 1

    async def test_initialize_mcp_pool_enabled_serena(self):
        """Test initialization when Serena is enabled"""
        mock_pool = MagicMock()
        fake_cwd = Path("/fake/cwd")
        fake_service_path = "services/serena"
        expected_abs_path = str(fake_cwd / fake_service_path)

        with (
            patch("src.core.tool_broker.mcp_client.get_mcp_pool", return_value=mock_pool),
            patch("src.config.is_serena_mcp_enabled", return_value=True),
            patch("src.config.get_serena_service_path", return_value=fake_service_path),
            patch("os.getcwd", return_value=str(fake_cwd)),
        ):
            await initialize_mcp_pool()

            # Verify Serena WAS registered
            registered_configs = [args[0] for args, _ in mock_pool.register.call_args_list]
            serena_configs = [c for c in registered_configs if c.name == "serena"]
            assert len(serena_configs) == 1

            config = serena_configs[0]
            assert config.command == "uv"
            assert "--directory" in config.args
            # Find the index of --directory and check the next arg
            dir_index = config.args.index("--directory")
            assert config.args[dir_index + 1] == expected_abs_path

    async def test_initialize_mcp_pool_custom_path(self):
        """Test initialization with a custom path"""
        mock_pool = MagicMock()
        fake_cwd = Path("C:/Project")
        custom_path = "custom/serena"
        expected_abs_path = str(fake_cwd / custom_path)

        with (
            patch("src.core.tool_broker.mcp_client.get_mcp_pool", return_value=mock_pool),
            patch("src.config.is_serena_mcp_enabled", return_value=True),
            patch("src.config.get_serena_service_path", return_value=custom_path),
            patch("os.getcwd", return_value=str(fake_cwd)),
        ):
            await initialize_mcp_pool()

            registered_configs = [args[0] for args, _ in mock_pool.register.call_args_list]
            serena_configs = [c for c in registered_configs if c.name == "serena"]
            assert len(serena_configs) == 1

            config = serena_configs[0]
            dir_index = config.args.index("--directory")
            assert config.args[dir_index + 1] == expected_abs_path
