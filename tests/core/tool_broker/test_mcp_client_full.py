from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.tool_broker.mcp_client import (
    MCPClient,
    MCPClientPool,
    MCPConnectionError,
    MCPInitializationError,
    MCPProtocolError,
    MCPResponseInvalidError,
    MCPServerConfig,
    MCPSubprocessError,
    MCPToolNotAvailableError,
    shutdown_mcp_pool,
)


@pytest.fixture
def mock_config():
    return MCPServerConfig(name="test-server", command="test-cmd", args=["arg1"], env={"TEST": "1"})


@pytest.fixture
def mcp_client(mock_config):
    return MCPClient(mock_config)


@pytest.mark.asyncio
class TestMCPClient:
    async def test_connect_success(self, mcp_client):
        with (
            patch("src.core.tool_broker.mcp_client.stdio_client") as mock_stdio,
            patch("src.core.tool_broker.mcp_client.ClientSession") as mock_session_cls,
        ):
            # Setup context manager mock
            mock_context = AsyncMock()
            mock_stdio.return_value = mock_context
            mock_context.__aenter__.return_value = (MagicMock(), MagicMock())  # streams

            # Setup session mock
            mock_session = AsyncMock()
            mock_session_cls.return_value = mock_session

            await mcp_client.connect()

            assert mcp_client._connected is True
            mock_stdio.assert_called_once()
            mock_session.initialize.assert_called_once()

    async def test_connect_already_connected(self, mcp_client):
        mcp_client._connected = True
        with patch("src.core.tool_broker.mcp_client.stdio_client") as mock_stdio:
            await mcp_client.connect()
            mock_stdio.assert_not_called()

    async def test_connect_failure_subprocess(self, mcp_client):
        with patch(
            "src.core.tool_broker.mcp_client.stdio_client",
            side_effect=Exception("Subprocess failed"),
        ):
            with pytest.raises(MCPSubprocessError):
                await mcp_client.connect()

    async def test_connect_failure_init(self, mcp_client):
        with (
            patch("src.core.tool_broker.mcp_client.stdio_client") as mock_stdio,
            patch("src.core.tool_broker.mcp_client.ClientSession") as mock_session_cls,
        ):
            mock_context = AsyncMock()
            mock_stdio.return_value = mock_context
            mock_context.__aenter__.return_value = (MagicMock(), MagicMock())

            mock_session = AsyncMock()
            mock_session_cls.return_value = mock_session
            mock_session.initialize.side_effect = Exception("Initialize failed")

            with pytest.raises(MCPInitializationError):
                await mcp_client.connect()

    async def test_connect_failure_generic(self, mcp_client):
        with patch("src.core.tool_broker.mcp_client.stdio_client") as mock_stdio:
            mock_stdio.side_effect = Exception("Generic Connection Error")
            with pytest.raises(MCPConnectionError):
                await mcp_client.connect()

    async def test_disconnect(self, mcp_client):
        mcp_client._connected = True
        mock_context = AsyncMock()
        mock_context.__aexit__.return_value = None
        mcp_client._stdio_context = mock_context

        await mcp_client.disconnect()

        assert mcp_client._connected is False
        mock_context.__aexit__.assert_called_once()

    async def test_disconnect_already_disconnected(self, mcp_client):
        mcp_client._connected = False
        await mcp_client.disconnect()  # Should do nothing

    async def test_call_tool_success_text(self, mcp_client):
        mcp_client._connected = True
        mcp_client.session = AsyncMock()

        # Mock result structure
        mock_result = MagicMock()
        mock_content = MagicMock()
        mock_content.text = "Success Result"
        mock_result.content = [mock_content]

        mcp_client.session.call_tool.return_value = mock_result

        result = await mcp_client.call_tool("my-tool", {"arg": 1})
        assert result == {"result": "Success Result"}

    async def test_call_tool_success_data(self, mcp_client):
        mcp_client._connected = True
        mcp_client.session = AsyncMock()

        mock_result = MagicMock()
        mock_content = MagicMock()
        del mock_content.text  # Ensure no text attr
        mock_content.data = {"key": "value"}
        mock_result.content = [mock_content]

        mcp_client.session.call_tool.return_value = mock_result

        result = await mcp_client.call_tool("my-tool", {})
        assert result == {"result": {"key": "value"}}

    async def test_call_tool_auto_connect(self, mcp_client):
        mcp_client._connected = False
        mcp_client.session = None  # Ensure session is None so connect is called

        async def mock_connect_impl():
            mcp_client.session = AsyncMock()
            mcp_client.session.call_tool.return_value = MagicMock(content=[])

        with patch.object(mcp_client, "connect", side_effect=mock_connect_impl) as mock_connect:
            await mcp_client.call_tool("tool", {})
            mock_connect.assert_called_once()

    async def test_call_tool_unavailable(self, mcp_client):
        mcp_client._connected = True
        mcp_client.session = AsyncMock()
        mcp_client.session.call_tool.side_effect = Exception("Tool not found")

        with pytest.raises(MCPToolNotAvailableError):
            await mcp_client.call_tool("missing", {})

    async def test_call_tool_protocol_error(self, mcp_client):
        mcp_client._connected = True
        mcp_client.session = AsyncMock()
        mcp_client.session.call_tool.side_effect = Exception("Protocol fail")

        with pytest.raises(MCPProtocolError):
            await mcp_client.call_tool("broken", {})

    async def test_call_tool_response_error(self, mcp_client):
        mcp_client._connected = True
        mcp_client.session = AsyncMock()
        # Force AttributeError to hit the except block
        mcp_client.session.call_tool.side_effect = AttributeError("Forced Error")

        with pytest.raises(MCPResponseInvalidError):
            await mcp_client.call_tool("bad-response", {})

    async def test_list_tools(self, mcp_client):
        mcp_client._connected = True
        mcp_client.session = AsyncMock()

        mock_tools_resp = MagicMock()
        mock_tool = MagicMock()
        mock_tool.name = "tool1"
        mock_tool.description = "desc"
        mock_tool.inputSchema = {}
        mock_tools_resp.tools = [mock_tool]

        mcp_client.session.list_tools.return_value = mock_tools_resp

        tools = await mcp_client.list_tools()
        assert len(tools) == 1
        assert tools[0]["name"] == "tool1"

    async def test_list_tools_error(self, mcp_client):
        mcp_client._connected = True
        mcp_client.session = AsyncMock()
        mcp_client.session.list_tools.side_effect = Exception("List fail")

        tools = await mcp_client.list_tools()
        assert tools == []


@pytest.mark.asyncio
class TestMCPClientPool:
    async def test_register_and_get_client(self):
        pool = MCPClientPool()
        config = MCPServerConfig(name="s1", command="cmd", args=[])
        pool.register(config)

        with patch("src.core.tool_broker.mcp_client.MCPClient") as MockClient:
            mock_instance = MockClient.return_value
            mock_instance.connect = AsyncMock()

            client = await pool.get_client("s1")

            assert client == mock_instance
            mock_instance.connect.assert_called_once()

            # Second call should return cached client
            client2 = await pool.get_client("s1")
            assert client2 == client
            assert mock_instance.connect.call_count == 1  # No re-connect

    async def test_get_client_not_found(self):
        pool = MCPClientPool()
        with pytest.raises(ValueError):
            await pool.get_client("unknown")

    async def test_close_all(self):
        pool = MCPClientPool()
        # Manually inject a mock client
        mock_client = AsyncMock()
        pool._clients["s1"] = mock_client

        await pool.close_all()

        mock_client.disconnect.assert_called_once()
        assert len(pool._clients) == 0

    async def test_shutdown_global(self):
        with patch("src.core.tool_broker.mcp_client._mcp_pool") as mock_pool:
            # Only if it's not None
            if mock_pool:
                mock_pool.close_all = AsyncMock()
                await shutdown_mcp_pool()
                mock_pool.close_all.assert_called_once()
