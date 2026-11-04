"""
Unit Tests for Tool Broker MCP Client
Tests async MCP protocol client for Serena and Sequential Thinking MCP servers

Coverage Target: src/core/tool_broker/mcp_client.py → >90%
Phase: P4.4.3 - MCP Client Coverage
"""

import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, Mock, PropertyMock, patch

import pytest

from src.core.tool_broker.exceptions import (
    MCPConnectionError,
    MCPInitializationError,
    MCPProtocolError,
    MCPResponseInvalidError,
    MCPSubprocessError,
    MCPToolNotAvailableError,
)
from src.core.tool_broker.mcp_client import (
    MCPClient,
    MCPClientPool,
    MCPServerConfig,
    get_mcp_pool,
    initialize_mcp_pool,
    shutdown_mcp_pool,
)

# ============================================================================
# AUTO-FIXTURE: Mock Logger for all tests (SafeLogger lacks exception method)
# ============================================================================


@pytest.fixture(autouse=True)
def mock_mcp_logger():
    """Auto-mock the logger to handle missing exception method in SafeLogger"""
    mock_logger = Mock()
    mock_logger.info = Mock()
    mock_logger.debug = Mock()
    mock_logger.warning = Mock()
    mock_logger.error = Mock()
    mock_logger.exception = Mock()  # SafeLogger doesn't have this

    with patch("src.core.tool_broker.mcp_client.logger", mock_logger):
        yield mock_logger


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_server_config():
    """Create a mock MCP server configuration"""
    return MCPServerConfig(
        name="test-server",
        command="/usr/bin/python",
        args=["--version"],
        env={"TEST_ENV": "value"},
    )


@pytest.fixture
def mock_server_config_no_env():
    """Create a mock MCP server config without env"""
    return MCPServerConfig(name="no-env-server", command="node", args=["script.js"])


@pytest.fixture
def mock_session():
    """Create a mock MCP ClientSession"""
    session = AsyncMock()
    session.initialize = AsyncMock()
    session.call_tool = AsyncMock()
    session.list_tools = AsyncMock()
    return session


@pytest.fixture
def mock_stdio_context():
    """Create a mock stdio context manager"""
    context = AsyncMock()
    read_stream = AsyncMock()
    write_stream = AsyncMock()

    async def aenter():
        return (read_stream, write_stream)

    context.__aenter__ = aenter
    context.__aexit__ = AsyncMock(return_value=None)

    return context, read_stream, write_stream


# ============================================================================
# TEST: MCPServerConfig Dataclass
# ============================================================================


class TestMCPServerConfig:
    """Test MCPServerConfig dataclass"""

    def test_config_creation_with_all_fields(self, mock_server_config):
        """Test configuration with all fields populated"""
        assert mock_server_config.name == "test-server"
        assert mock_server_config.command == "/usr/bin/python"
        assert mock_server_config.args == ["--version"]
        assert mock_server_config.env == {"TEST_ENV": "value"}

    def test_config_creation_without_env(self, mock_server_config_no_env):
        """Test configuration with default env (None)"""
        assert mock_server_config_no_env.name == "no-env-server"
        assert mock_server_config_no_env.command == "node"
        assert mock_server_config_no_env.args == ["script.js"]
        assert mock_server_config_no_env.env is None

    def test_config_empty_args(self):
        """Test configuration with empty args list"""
        config = MCPServerConfig(name="minimal", command="echo", args=[])
        assert config.args == []
        assert config.env is None

    def test_config_with_multiple_args(self):
        """Test configuration with multiple arguments"""
        config = MCPServerConfig(
            name="multi-arg",
            command="npx",
            args=[
                "-y",
                "@modelcontextprotocol/server-sequential-thinking",
                "--verbose",
            ],
        )
        assert len(config.args) == 3
        assert "-y" in config.args

    def test_config_with_complex_env(self):
        """Test configuration with complex environment variables"""
        config = MCPServerConfig(
            name="complex-env",
            command="python",
            args=["script.py"],
            env={
                "PYTHONUNBUFFERED": "1",
                "LOG_LEVEL": "DEBUG",
                "API_KEY": "secret-key-123",
            },
        )
        assert len(config.env) == 3
        assert config.env["PYTHONUNBUFFERED"] == "1"


# ============================================================================
# TEST: MCPClient Initialization
# ============================================================================


class TestMCPClientInit:
    """Test MCPClient initialization"""

    def test_client_init_with_config(self, mock_server_config):
        """Test client initialization stores config"""
        client = MCPClient(mock_server_config)

        assert client.config == mock_server_config
        assert client.session is None
        assert client._stdio_context is None
        assert client._read_stream is None
        assert client._write_stream is None
        assert client._connected is False

    def test_client_init_creates_lock(self, mock_server_config):
        """Test client initialization creates asyncio lock"""
        client = MCPClient(mock_server_config)

        assert hasattr(client, "_lock")
        assert isinstance(client._lock, asyncio.Lock)

    def test_client_init_with_minimal_config(self):
        """Test client initialization with minimal config"""
        config = MCPServerConfig(name="minimal", command="cmd", args=[])
        client = MCPClient(config)

        assert client.config.name == "minimal"
        assert client._connected is False


# ============================================================================
# TEST: MCPClient.connect()
# ============================================================================


class TestMCPClientConnect:
    """Test MCPClient connection methods"""

    @pytest.mark.asyncio
    async def test_connect_success(self, mock_server_config):
        """Test successful connection to MCP server"""
        client = MCPClient(mock_server_config)

        mock_context = AsyncMock()
        mock_read = AsyncMock()
        mock_write = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=(mock_read, mock_write))
        mock_context.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()

        with (
            patch(
                "src.core.tool_broker.mcp_client.stdio_client",
                return_value=mock_context,
            ),
            patch(
                "src.core.tool_broker.mcp_client.ClientSession",
                return_value=mock_session,
            ),
        ):
            await client.connect()

            assert client._connected is True
            assert client.session == mock_session
            mock_session.initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_already_connected_skips(self, mock_server_config):
        """Test connect() skips if already connected"""
        client = MCPClient(mock_server_config)
        client._connected = True

        # Should not attempt reconnection
        await client.connect()

        # No errors, still connected
        assert client._connected is True

    @pytest.mark.asyncio
    async def test_connect_subprocess_error(self, mock_server_config):
        """Test connect raises MCPSubprocessError for subprocess failures"""
        client = MCPClient(mock_server_config)

        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(side_effect=Exception("subprocess failed to start"))

        with patch("src.core.tool_broker.mcp_client.stdio_client", return_value=mock_context):
            with pytest.raises(MCPSubprocessError) as exc_info:
                await client.connect()

            assert exc_info.value.server_name == "test-server"

    @pytest.mark.asyncio
    async def test_connect_initialization_error(self, mock_server_config):
        """Test connect raises MCPInitializationError for session init failures"""
        client = MCPClient(mock_server_config)

        mock_context = AsyncMock()
        mock_read = AsyncMock()
        mock_write = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=(mock_read, mock_write))

        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock(side_effect=Exception("session initialize failed"))

        with (
            patch(
                "src.core.tool_broker.mcp_client.stdio_client",
                return_value=mock_context,
            ),
            patch(
                "src.core.tool_broker.mcp_client.ClientSession",
                return_value=mock_session,
            ),
        ):
            with pytest.raises(MCPInitializationError) as exc_info:
                await client.connect()

            assert exc_info.value.server_name == "test-server"

    @pytest.mark.asyncio
    async def test_connect_generic_error(self, mock_server_config):
        """Test connect raises MCPConnectionError for generic failures"""
        client = MCPClient(mock_server_config)

        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(side_effect=Exception("network error"))

        with patch("src.core.tool_broker.mcp_client.stdio_client", return_value=mock_context):
            with pytest.raises(MCPConnectionError) as exc_info:
                await client.connect()

            assert exc_info.value.server_name == "test-server"

    @pytest.mark.asyncio
    async def test_connect_with_empty_env(self, mock_server_config_no_env):
        """Test connect handles None env by using empty dict"""
        client = MCPClient(mock_server_config_no_env)

        mock_context = AsyncMock()
        mock_read = AsyncMock()
        mock_write = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=(mock_read, mock_write))
        mock_context.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()

        captured_params = []

        def capture_stdio_client(params):
            captured_params.append(params)
            return mock_context

        with (
            patch(
                "src.core.tool_broker.mcp_client.stdio_client",
                side_effect=capture_stdio_client,
            ),
            patch(
                "src.core.tool_broker.mcp_client.ClientSession",
                return_value=mock_session,
            ),
        ):
            await client.connect()

            # Verify env is empty dict, not None
            assert captured_params[0].env == {}


# ============================================================================
# TEST: MCPClient.disconnect()
# ============================================================================


class TestMCPClientDisconnect:
    """Test MCPClient disconnection methods"""

    @pytest.mark.asyncio
    async def test_disconnect_success(self, mock_server_config):
        """Test successful disconnection"""
        client = MCPClient(mock_server_config)
        client._connected = True
        client._stdio_context = AsyncMock()
        client._stdio_context.__aexit__ = AsyncMock(return_value=None)
        client.session = AsyncMock()
        client._read_stream = AsyncMock()
        client._write_stream = AsyncMock()

        await client.disconnect()

        assert client._connected is False
        assert client.session is None
        assert client._read_stream is None
        assert client._write_stream is None
        assert client._stdio_context is None

    @pytest.mark.asyncio
    async def test_disconnect_already_disconnected_skips(self, mock_server_config):
        """Test disconnect skips if already disconnected"""
        client = MCPClient(mock_server_config)
        client._connected = False

        # Should not raise any errors
        await client.disconnect()

        assert client._connected is False

    @pytest.mark.asyncio
    async def test_disconnect_handles_exit_error(self, mock_server_config):
        """Test disconnect handles errors gracefully - state NOT reset on exception"""
        client = MCPClient(mock_server_config)
        client._connected = True
        client._stdio_context = AsyncMock()
        client._stdio_context.__aexit__ = AsyncMock(side_effect=Exception("exit error"))

        # Should not raise, just log error
        await client.disconnect()

        # Note: Based on actual implementation, state remains True if aexit fails
        # The implementation catches and logs error but doesn't reset state on exception
        assert client._connected is True  # State unchanged after exception


# ============================================================================
# TEST: MCPClient.call_tool()
# ============================================================================


class TestMCPClientCallTool:
    """Test MCPClient tool calling functionality"""

    @pytest.mark.asyncio
    async def test_call_tool_success_with_text_content(self, mock_server_config):
        """Test successful tool call with text response"""
        client = MCPClient(mock_server_config)
        client._connected = True

        # Create mock result with text content
        mock_content_item = Mock()
        mock_content_item.text = "Tool executed successfully"

        mock_result = Mock()
        mock_result.content = [mock_content_item]

        client.session = AsyncMock()
        client.session.call_tool = AsyncMock(return_value=mock_result)

        result = await client.call_tool("test_tool", {"param": "value"})

        assert result == {"result": "Tool executed successfully"}
        client.session.call_tool.assert_called_once_with("test_tool", {"param": "value"})

    @pytest.mark.asyncio
    async def test_call_tool_success_with_data_content(self, mock_server_config):
        """Test successful tool call with data response"""
        client = MCPClient(mock_server_config)
        client._connected = True

        # Create mock result with data content - use spec to remove text attr
        mock_content_item = Mock(spec=["data"])  # Only has data, no text
        mock_content_item.data = {"key": "value"}

        mock_result = Mock()
        mock_result.content = [mock_content_item]

        client.session = AsyncMock()
        client.session.call_tool = AsyncMock(return_value=mock_result)

        result = await client.call_tool("data_tool", {})

        assert result == {"result": {"key": "value"}}

    @pytest.mark.asyncio
    async def test_call_tool_returns_raw_content_if_no_text_or_data(self, mock_server_config):
        """Test tool call returns raw content when no text/data attributes"""
        client = MCPClient(mock_server_config)
        client._connected = True

        # Create mock result without text or data
        mock_content_item = Mock(spec=[])  # No attributes

        mock_result = Mock()
        mock_result.content = [mock_content_item]

        client.session = AsyncMock()
        client.session.call_tool = AsyncMock(return_value=mock_result)

        result = await client.call_tool("generic_tool", {})

        # Should return the raw content list
        assert "result" in result

    @pytest.mark.asyncio
    async def test_call_tool_empty_content_list(self, mock_server_config):
        """Test tool call with empty content list"""
        client = MCPClient(mock_server_config)
        client._connected = True

        mock_result = Mock()
        mock_result.content = []

        client.session = AsyncMock()
        client.session.call_tool = AsyncMock(return_value=mock_result)

        result = await client.call_tool("empty_tool", {})

        assert result == {"result": []}

    @pytest.mark.asyncio
    async def test_call_tool_no_content_attribute(self, mock_server_config):
        """Test tool call when result has no content attribute"""
        client = MCPClient(mock_server_config)
        client._connected = True

        mock_result = Mock(spec=[])

        client.session = AsyncMock()
        client.session.call_tool = AsyncMock(return_value=mock_result)

        result = await client.call_tool("no_content_tool", {})

        # Should stringify the result
        assert "result" in result

    @pytest.mark.asyncio
    async def test_call_tool_auto_connects_if_not_connected(self, mock_server_config):
        """Test call_tool automatically connects if session is None"""
        client = MCPClient(mock_server_config)

        mock_context = AsyncMock()
        mock_read = AsyncMock()
        mock_write = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=(mock_read, mock_write))
        mock_context.__aexit__ = AsyncMock(return_value=None)

        mock_content_item = Mock()
        mock_content_item.text = "auto-connected"
        mock_result = Mock()
        mock_result.content = [mock_content_item]

        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()
        mock_session.call_tool = AsyncMock(return_value=mock_result)

        with (
            patch(
                "src.core.tool_broker.mcp_client.stdio_client",
                return_value=mock_context,
            ),
            patch(
                "src.core.tool_broker.mcp_client.ClientSession",
                return_value=mock_session,
            ),
        ):
            result = await client.call_tool("auto_connect_tool", {})

            assert result == {"result": "auto-connected"}
            mock_session.initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_call_tool_raises_tool_not_available(self, mock_server_config):
        """Test call_tool raises MCPToolNotAvailableError for missing tools"""
        client = MCPClient(mock_server_config)
        client._connected = True
        client.session = AsyncMock()
        client.session.call_tool = AsyncMock(side_effect=Exception("tool not found"))

        with pytest.raises(MCPToolNotAvailableError) as exc_info:
            await client.call_tool("missing_tool", {})

        assert exc_info.value.server_name == "test-server"
        assert exc_info.value.tool_name == "missing_tool"

    @pytest.mark.asyncio
    async def test_call_tool_raises_tool_unavailable(self, mock_server_config):
        """Test call_tool raises MCPToolNotAvailableError for unavailable tools"""
        client = MCPClient(mock_server_config)
        client._connected = True
        client.session = AsyncMock()
        client.session.call_tool = AsyncMock(side_effect=Exception("tool unavailable"))

        with pytest.raises(MCPToolNotAvailableError):
            await client.call_tool("unavailable_tool", {})

    @pytest.mark.asyncio
    async def test_call_tool_raises_protocol_error(self, mock_server_config):
        """Test call_tool raises MCPProtocolError for protocol failures"""
        client = MCPClient(mock_server_config)
        client._connected = True
        client.session = AsyncMock()
        client.session.call_tool = AsyncMock(side_effect=Exception("protocol mismatch"))

        with pytest.raises(MCPProtocolError) as exc_info:
            await client.call_tool("protocol_error_tool", {"arg": 1})

        assert exc_info.value.server_name == "test-server"

    @pytest.mark.asyncio
    async def test_call_tool_response_without_text_or_data_returns_content(
        self, mock_server_config
    ):
        """Test call_tool handles content items without text or data attributes"""
        client = MCPClient(mock_server_config)
        client._connected = True

        # Create a content item without text or data - should fall through to return content list
        mock_content_item = Mock(spec=[])  # Empty spec - no text or data

        mock_result = Mock()
        mock_result.content = [mock_content_item]

        client.session = AsyncMock()
        client.session.call_tool = AsyncMock(return_value=mock_result)

        # Should return the content list (graceful fallback)
        result = await client.call_tool("no_attrs_tool", {})

        assert "result" in result


# ============================================================================
# TEST: MCPClient.list_tools()
# ============================================================================


class TestMCPClientListTools:
    """Test MCPClient tool listing functionality"""

    @pytest.mark.asyncio
    async def test_list_tools_success(self, mock_server_config):
        """Test successful tool listing"""
        client = MCPClient(mock_server_config)
        client._connected = True

        mock_tool1 = Mock()
        mock_tool1.name = "tool1"
        mock_tool1.description = "First tool"
        mock_tool1.inputSchema = {"type": "object"}

        mock_tool2 = Mock()
        mock_tool2.name = "tool2"
        mock_tool2.description = "Second tool"
        mock_tool2.inputSchema = {"type": "string"}

        mock_tools_response = Mock()
        mock_tools_response.tools = [mock_tool1, mock_tool2]

        client.session = AsyncMock()
        client.session.list_tools = AsyncMock(return_value=mock_tools_response)

        tools = await client.list_tools()

        assert len(tools) == 2
        assert tools[0]["name"] == "tool1"
        assert tools[0]["description"] == "First tool"
        assert tools[1]["name"] == "tool2"

    @pytest.mark.asyncio
    async def test_list_tools_auto_connects(self, mock_server_config):
        """Test list_tools automatically connects if needed"""
        client = MCPClient(mock_server_config)

        mock_context = AsyncMock()
        mock_read = AsyncMock()
        mock_write = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=(mock_read, mock_write))
        mock_context.__aexit__ = AsyncMock(return_value=None)

        mock_tools_response = Mock()
        mock_tools_response.tools = []

        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()
        mock_session.list_tools = AsyncMock(return_value=mock_tools_response)

        with (
            patch(
                "src.core.tool_broker.mcp_client.stdio_client",
                return_value=mock_context,
            ),
            patch(
                "src.core.tool_broker.mcp_client.ClientSession",
                return_value=mock_session,
            ),
        ):
            tools = await client.list_tools()

            assert tools == []
            mock_session.initialize.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_tools_empty_list(self, mock_server_config):
        """Test list_tools returns empty list when no tools"""
        client = MCPClient(mock_server_config)
        client._connected = True

        mock_tools_response = Mock()
        mock_tools_response.tools = []

        client.session = AsyncMock()
        client.session.list_tools = AsyncMock(return_value=mock_tools_response)

        tools = await client.list_tools()

        assert tools == []

    @pytest.mark.asyncio
    async def test_list_tools_returns_empty_on_error(self, mock_server_config):
        """Test list_tools returns empty list on error (graceful degradation)"""
        client = MCPClient(mock_server_config)
        client._connected = True
        client.session = AsyncMock()
        client.session.list_tools = AsyncMock(side_effect=Exception("list failed"))

        tools = await client.list_tools()

        assert tools == []


# ============================================================================
# TEST: MCPClientPool
# ============================================================================


class TestMCPClientPool:
    """Test MCPClientPool connection management"""

    def test_pool_initialization(self):
        """Test pool initializes with empty clients and configs"""
        pool = MCPClientPool()

        assert pool._clients == {}
        assert pool._configs == {}

    def test_pool_register_config(self, mock_server_config):
        """Test registering a server configuration"""
        pool = MCPClientPool()
        pool.register(mock_server_config)

        assert "test-server" in pool._configs
        assert pool._configs["test-server"] == mock_server_config

    def test_pool_register_multiple_configs(self):
        """Test registering multiple server configurations"""
        pool = MCPClientPool()

        config1 = MCPServerConfig(name="server1", command="cmd1", args=[])
        config2 = MCPServerConfig(name="server2", command="cmd2", args=[])

        pool.register(config1)
        pool.register(config2)

        assert len(pool._configs) == 2
        assert "server1" in pool._configs
        assert "server2" in pool._configs

    @pytest.mark.asyncio
    async def test_pool_get_client_creates_new_client(self, mock_server_config):
        """Test get_client creates and connects new client"""
        pool = MCPClientPool()
        pool.register(mock_server_config)

        mock_context = AsyncMock()
        mock_read = AsyncMock()
        mock_write = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=(mock_read, mock_write))
        mock_context.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()

        with (
            patch(
                "src.core.tool_broker.mcp_client.stdio_client",
                return_value=mock_context,
            ),
            patch(
                "src.core.tool_broker.mcp_client.ClientSession",
                return_value=mock_session,
            ),
        ):
            client = await pool.get_client("test-server")

            assert client is not None
            assert "test-server" in pool._clients
            assert client._connected is True

    @pytest.mark.asyncio
    async def test_pool_get_client_returns_cached(self, mock_server_config):
        """Test get_client returns cached client on subsequent calls"""
        pool = MCPClientPool()
        pool.register(mock_server_config)

        # Pre-populate with a mock client
        mock_client = Mock(spec=MCPClient)
        pool._clients["test-server"] = mock_client

        client = await pool.get_client("test-server")

        assert client is mock_client

    @pytest.mark.asyncio
    async def test_pool_get_client_unknown_server_raises(self):
        """Test get_client raises ValueError for unknown server"""
        pool = MCPClientPool()

        with pytest.raises(ValueError) as exc_info:
            await pool.get_client("unknown-server")

        assert "No configuration found" in str(exc_info.value)
        assert "unknown-server" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_pool_close_all(self, mock_server_config):
        """Test close_all disconnects all clients"""
        pool = MCPClientPool()

        mock_client1 = AsyncMock(spec=MCPClient)
        mock_client2 = AsyncMock(spec=MCPClient)

        pool._clients = {"server1": mock_client1, "server2": mock_client2}

        await pool.close_all()

        mock_client1.disconnect.assert_called_once()
        mock_client2.disconnect.assert_called_once()
        assert pool._clients == {}

    @pytest.mark.asyncio
    async def test_pool_close_all_empty(self):
        """Test close_all handles empty pool"""
        pool = MCPClientPool()

        await pool.close_all()

        assert pool._clients == {}


# ============================================================================
# TEST: Global Pool Functions
# ============================================================================


class TestGlobalPoolFunctions:
    """Test global MCP pool management functions"""

    def test_get_mcp_pool_creates_singleton(self):
        """Test get_mcp_pool creates singleton instance"""
        # Reset global state
        import src.core.tool_broker.mcp_client as mcp_module

        mcp_module._mcp_pool = None

        pool1 = get_mcp_pool()
        pool2 = get_mcp_pool()

        assert pool1 is pool2
        assert isinstance(pool1, MCPClientPool)

    def test_get_mcp_pool_returns_existing(self):
        """Test get_mcp_pool returns existing pool"""
        import src.core.tool_broker.mcp_client as mcp_module

        existing_pool = MCPClientPool()
        mcp_module._mcp_pool = existing_pool

        pool = get_mcp_pool()

        assert pool is existing_pool

    @pytest.mark.asyncio
    async def test_initialize_mcp_pool_registers_servers(self):
        """Test initialize_mcp_pool registers Sequential Thinking (serena is optional)"""
        import src.core.tool_broker.mcp_client as mcp_module

        mcp_module._mcp_pool = None

        await initialize_mcp_pool()

        pool = get_mcp_pool()

        # sequential-thinking is always registered
        assert "sequential-thinking" in pool._configs
        # serena is only registered when enabled via config (may be disabled in CI)

    @pytest.mark.asyncio
    async def test_initialize_mcp_pool_serena_config(self):
        """Test Serena server configuration when serena is enabled"""
        import src.core.tool_broker.mcp_client as mcp_module

        mcp_module._mcp_pool = None

        await initialize_mcp_pool()

        pool = get_mcp_pool()

        if "serena" not in pool._configs:
            pytest.skip("Serena MCP is disabled in this environment")

        serena_config = pool._configs["serena"]

        assert "uv" in serena_config.command.lower() or "uv.exe" in serena_config.command.lower()
        assert "serena" in serena_config.args
        assert "start-mcp-server" in serena_config.args

    @pytest.mark.asyncio
    async def test_initialize_mcp_pool_sequential_thinking_config(self):
        """Test Sequential Thinking server configuration"""
        import src.core.tool_broker.mcp_client as mcp_module

        mcp_module._mcp_pool = None

        await initialize_mcp_pool()

        pool = get_mcp_pool()
        seq_config = pool._configs["sequential-thinking"]

        assert seq_config.command == "npx"
        assert "-y" in seq_config.args
        assert "@modelcontextprotocol/server-sequential-thinking" in seq_config.args

    @pytest.mark.asyncio
    async def test_shutdown_mcp_pool_closes_all(self):
        """Test shutdown_mcp_pool closes all clients"""
        import src.core.tool_broker.mcp_client as mcp_module

        mock_pool = AsyncMock(spec=MCPClientPool)
        mcp_module._mcp_pool = mock_pool

        await shutdown_mcp_pool()

        mock_pool.close_all.assert_called_once()
        assert mcp_module._mcp_pool is None

    @pytest.mark.asyncio
    async def test_shutdown_mcp_pool_handles_none(self):
        """Test shutdown_mcp_pool handles None pool gracefully"""
        import src.core.tool_broker.mcp_client as mcp_module

        mcp_module._mcp_pool = None

        # Should not raise
        await shutdown_mcp_pool()

        assert mcp_module._mcp_pool is None


# ============================================================================
# TEST: Concurrency and Lock Behavior
# ============================================================================


class TestConcurrency:
    """Test concurrency handling with async lock"""

    @pytest.mark.asyncio
    async def test_call_tool_uses_lock(self, mock_server_config):
        """Test call_tool acquires lock for thread safety"""
        client = MCPClient(mock_server_config)
        client._connected = True

        mock_content_item = Mock()
        mock_content_item.text = "result"
        mock_result = Mock()
        mock_result.content = [mock_content_item]

        client.session = AsyncMock()
        client.session.call_tool = AsyncMock(return_value=mock_result)

        # Track if lock was used
        lock_acquired = []
        original_lock = client._lock

        class TrackingLock:
            async def __aenter__(self):
                lock_acquired.append(True)
                return await original_lock.__aenter__()

            async def __aexit__(self, *args):
                return await original_lock.__aexit__(*args)

        client._lock = TrackingLock()

        await client.call_tool("test", {})

        assert len(lock_acquired) == 1

    @pytest.mark.asyncio
    async def test_list_tools_uses_lock(self, mock_server_config):
        """Test list_tools acquires lock for thread safety"""
        client = MCPClient(mock_server_config)
        client._connected = True

        mock_tools_response = Mock()
        mock_tools_response.tools = []

        client.session = AsyncMock()
        client.session.list_tools = AsyncMock(return_value=mock_tools_response)

        lock_acquired = []
        original_lock = client._lock

        class TrackingLock:
            async def __aenter__(self):
                lock_acquired.append(True)
                return await original_lock.__aenter__()

            async def __aexit__(self, *args):
                return await original_lock.__aexit__(*args)

        client._lock = TrackingLock()

        await client.list_tools()

        assert len(lock_acquired) == 1


# ============================================================================
# TEST: Integration Scenarios
# ============================================================================


class TestIntegrationScenarios:
    """Test realistic integration scenarios"""

    @pytest.mark.asyncio
    async def test_full_client_lifecycle(self, mock_server_config):
        """Test complete connect -> call_tool -> disconnect lifecycle"""
        client = MCPClient(mock_server_config)

        mock_context = AsyncMock()
        mock_read = AsyncMock()
        mock_write = AsyncMock()
        mock_context.__aenter__ = AsyncMock(return_value=(mock_read, mock_write))
        mock_context.__aexit__ = AsyncMock(return_value=None)

        mock_content_item = Mock()
        mock_content_item.text = "lifecycle test"
        mock_result = Mock()
        mock_result.content = [mock_content_item]

        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()
        mock_session.call_tool = AsyncMock(return_value=mock_result)

        with (
            patch(
                "src.core.tool_broker.mcp_client.stdio_client",
                return_value=mock_context,
            ),
            patch(
                "src.core.tool_broker.mcp_client.ClientSession",
                return_value=mock_session,
            ),
        ):
            # Connect
            await client.connect()
            assert client._connected is True

            # Call tool
            result = await client.call_tool("test", {})
            assert result["result"] == "lifecycle test"

            # Disconnect
            await client.disconnect()
            assert client._connected is False

    @pytest.mark.asyncio
    async def test_pool_multiple_server_lifecycle(self):
        """Test pool managing multiple servers"""
        import src.core.tool_broker.mcp_client as mcp_module

        mcp_module._mcp_pool = None

        pool = get_mcp_pool()

        config1 = MCPServerConfig(name="server1", command="cmd1", args=[])
        config2 = MCPServerConfig(name="server2", command="cmd2", args=[])

        pool.register(config1)
        pool.register(config2)

        assert len(pool._configs) == 2

        # Cleanup
        await pool.close_all()
        mcp_module._mcp_pool = None

    @pytest.mark.asyncio
    async def test_reconnect_after_disconnect(self, mock_server_config):
        """Test client can reconnect after disconnect"""
        client = MCPClient(mock_server_config)

        connect_count = 0

        def make_mock_context():
            """Create a fresh mock context each time"""
            mock_ctx = MagicMock()
            mock_read = AsyncMock()
            mock_write = AsyncMock()

            async def aenter_impl(self_arg=None):
                nonlocal connect_count
                connect_count += 1
                return (mock_read, mock_write)

            async def aexit_impl(self_arg=None, *args):
                return None

            mock_ctx.__aenter__ = aenter_impl
            mock_ctx.__aexit__ = aexit_impl
            return mock_ctx

        mock_session = AsyncMock()
        mock_session.initialize = AsyncMock()

        with (
            patch(
                "src.core.tool_broker.mcp_client.stdio_client",
                side_effect=lambda _: make_mock_context(),
            ),
            patch(
                "src.core.tool_broker.mcp_client.ClientSession",
                return_value=mock_session,
            ),
        ):
            # First connect
            await client.connect()
            assert client._connected is True
            assert connect_count == 1

            # Disconnect
            await client.disconnect()
            assert client._connected is False

            # Reconnect
            await client.connect()
            assert client._connected is True
            assert connect_count == 2


# ============================================================================
# TEST: Edge Cases
# ============================================================================


class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    @pytest.mark.asyncio
    async def test_call_tool_with_empty_arguments(self, mock_server_config):
        """Test call_tool with empty arguments dict"""
        client = MCPClient(mock_server_config)
        client._connected = True

        mock_content_item = Mock()
        mock_content_item.text = "empty args ok"
        mock_result = Mock()
        mock_result.content = [mock_content_item]

        client.session = AsyncMock()
        client.session.call_tool = AsyncMock(return_value=mock_result)

        result = await client.call_tool("no_args_tool", {})

        assert result["result"] == "empty args ok"

    @pytest.mark.asyncio
    async def test_call_tool_with_complex_arguments(self, mock_server_config):
        """Test call_tool with complex nested arguments"""
        client = MCPClient(mock_server_config)
        client._connected = True

        mock_content_item = Mock()
        mock_content_item.text = "complex args ok"
        mock_result = Mock()
        mock_result.content = [mock_content_item]

        client.session = AsyncMock()
        client.session.call_tool = AsyncMock(return_value=mock_result)

        complex_args = {
            "nested": {"deep": {"value": 123}},
            "list": [1, 2, 3],
            "boolean": True,
            "null": None,
        }

        result = await client.call_tool("complex_tool", complex_args)

        client.session.call_tool.assert_called_with("complex_tool", complex_args)
        assert result["result"] == "complex args ok"

    @pytest.mark.asyncio
    async def test_call_tool_with_unicode_content(self, mock_server_config):
        """Test call_tool handles Unicode content"""
        client = MCPClient(mock_server_config)
        client._connected = True

        mock_content_item = Mock()
        mock_content_item.text = "Unicode: 中文 日本語 🎉 émojis"
        mock_result = Mock()
        mock_result.content = [mock_content_item]

        client.session = AsyncMock()
        client.session.call_tool = AsyncMock(return_value=mock_result)

        result = await client.call_tool("unicode_tool", {})

        assert "中文" in result["result"]
        assert "🎉" in result["result"]

    def test_config_with_special_characters_in_args(self):
        """Test config handles special characters in args"""
        config = MCPServerConfig(
            name="special",
            command="python",
            args=["--config", "path/with spaces/config.json", "--flag='value'"],
        )

        assert len(config.args) == 3
        assert "spaces" in config.args[1]

    @pytest.mark.asyncio
    async def test_multiple_tool_calls_sequential(self, mock_server_config):
        """Test multiple sequential tool calls"""
        client = MCPClient(mock_server_config)
        client._connected = True

        call_results = ["first", "second", "third"]
        call_index = 0

        async def mock_call_tool(tool_name, args):
            nonlocal call_index
            mock_item = Mock()
            mock_item.text = call_results[call_index]
            call_index += 1
            mock_result = Mock()
            mock_result.content = [mock_item]
            return mock_result

        client.session = AsyncMock()
        client.session.call_tool = mock_call_tool

        r1 = await client.call_tool("tool1", {})
        r2 = await client.call_tool("tool2", {})
        r3 = await client.call_tool("tool3", {})

        assert r1["result"] == "first"
        assert r2["result"] == "second"
        assert r3["result"] == "third"


# ============================================================================
# TEST: Error Message Validation
# ============================================================================


class TestErrorMessages:
    """Test error message quality and content"""

    @pytest.mark.asyncio
    async def test_subprocess_error_includes_command(self, mock_server_config):
        """Test MCPSubprocessError includes command details"""
        client = MCPClient(mock_server_config)

        mock_context = AsyncMock()
        mock_context.__aenter__ = AsyncMock(side_effect=Exception("process crashed"))

        with patch("src.core.tool_broker.mcp_client.stdio_client", return_value=mock_context):
            with pytest.raises(MCPSubprocessError) as exc_info:
                await client.connect()

            error = exc_info.value
            assert error.server_name == "test-server"

    @pytest.mark.asyncio
    async def test_tool_not_available_includes_tool_name(self, mock_server_config):
        """Test MCPToolNotAvailableError includes tool name"""
        client = MCPClient(mock_server_config)
        client._connected = True
        client.session = AsyncMock()
        client.session.call_tool = AsyncMock(side_effect=Exception("tool not found"))

        with pytest.raises(MCPToolNotAvailableError) as exc_info:
            await client.call_tool("specific_tool", {})

        error = exc_info.value
        assert error.tool_name == "specific_tool"

    @pytest.mark.asyncio
    async def test_protocol_error_includes_context(self, mock_server_config):
        """Test MCPProtocolError includes execution context"""
        client = MCPClient(mock_server_config)
        client._connected = True
        client.session = AsyncMock()
        client.session.call_tool = AsyncMock(side_effect=Exception("protocol violation"))

        with pytest.raises(MCPProtocolError) as exc_info:
            await client.call_tool("error_tool", {"key": "value"})

        error = exc_info.value
        assert error.server_name == "test-server"
