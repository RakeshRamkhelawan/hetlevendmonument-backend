# core/tool_broker/mcp_client.py
"""
MCP Client Implementation for Tool Broker
Direct MCP protocol integration for Serena and Sequential Thinking
"""

import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from src import config
from src.core.shared.production_logging import SafeLogger
from src.core.tool_broker.exceptions import (
    MCPConnectionError,
    MCPInitializationError,
    MCPProtocolError,
    MCPResponseInvalidError,
    MCPSubprocessError,
    MCPToolNotAvailableError,
)

logger = SafeLogger(__name__)


@dataclass
class MCPServerConfig:
    """Configuration for an MCP server"""

    name: str
    command: str
    args: list[str]
    env: dict[str, str] | None = None


class MCPClient:
    """
    Generic MCP Client for stdio-based MCP servers
    Manages subprocess lifecycle and MCP protocol communication
    Uses async context manager pattern for proper resource cleanup
    """

    def __init__(self, config: MCPServerConfig) -> None:
        self.config = config
        self.session: ClientSession | None = None
        self._stdio_context: Any = None
        self._read_stream: Any = None
        self._write_stream: Any = None
        self._lock = asyncio.Lock()
        self._connected = False

    async def connect(self) -> None:
        """Establish connection to MCP server"""
        if self._connected:
            logger.debug(f"MCP client already connected to {self.config.name}")
            return

        try:
            server_params = StdioServerParameters(
                command=self.config.command,
                args=self.config.args,
                env=self.config.env or {},
            )

            # Create stdio context manager
            self._stdio_context = stdio_client(server_params)

            # Enter async context manager
            streams = await self._stdio_context.__aenter__()
            self._read_stream = streams[0]
            self._write_stream = streams[1]

            # Initialize session
            self.session = ClientSession(self._read_stream, self._write_stream)
            await self.session.initialize()

            self._connected = True
            logger.info(f"MCP client connected to {self.config.name}")

        except Exception as e:
            logger.exception(f"Failed to connect to MCP server {self.config.name}: {e}")

            # Categorize the error type
            if "subprocess" in str(e).lower() or "process" in str(e).lower():
                raise MCPSubprocessError(
                    server_name=self.config.name,
                    command=f"{self.config.command} {' '.join(self.config.args)}",
                    original_error=e,
                    context={"env": self.config.env},
                ) from e
            elif "initialize" in str(e).lower() or "session" in str(e).lower():
                raise MCPInitializationError(server_name=self.config.name, original_error=e) from e
            else:
                raise MCPConnectionError(server_name=self.config.name, original_error=e) from e

    async def disconnect(self) -> None:
        """Close connection to MCP server"""
        if not self._connected:
            logger.debug(f"MCP client already disconnected from {self.config.name}")
            return

        try:
            if self._stdio_context:
                # Exit async context manager
                await self._stdio_context.__aexit__(None, None, None)

            self.session = None
            self._read_stream = None
            self._write_stream = None
            self._stdio_context = None
            self._connected = False

            logger.info(f"MCP client disconnected from {self.config.name}")

        except Exception as e:
            logger.exception(f"Error disconnecting from {self.config.name}: {e}")

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Call an MCP tool

        Args:
            tool_name: Name of the tool to call
            arguments: Tool arguments

        Returns:
            Tool execution result
        """
        async with self._lock:
            if not self.session:
                await self.connect()

            # Ensure session is not None after connect
            if self.session is None:
                raise MCPConnectionError(
                    server_name=self.config.name,
                    original_error=Exception("Session is None after connect"),
                )

            result = None
            try:
                logger.info(f"Calling MCP tool {tool_name} on {self.config.name}")

                # Call tool via MCP protocol
                result = await self.session.call_tool(tool_name, arguments)

                logger.info(f"MCP tool {tool_name} completed successfully")

                # Parse result based on MCP protocol
                if hasattr(result, "content"):
                    # Extract content from MCP response
                    content = result.content
                    if isinstance(content, list) and len(content) > 0:
                        first_item = content[0]
                        # Use getattr to safely access attributes that may not exist
                        # on all content types (TextContent, ImageContent, etc.)
                        text_val = getattr(first_item, "text", None)
                        if text_val is not None:
                            return {"result": text_val}
                        data_val = getattr(first_item, "data", None)
                        if data_val is not None:
                            return {"result": data_val}
                    return {"result": content}

                return {"result": str(result)}

            except AttributeError as e:
                # Response format error
                logger.exception(f"Invalid MCP response format for {tool_name}: {e}")
                result_str = str(result) if result is not None else None
                raise MCPResponseInvalidError(
                    server_name=self.config.name,
                    tool_name=tool_name,
                    reason=f"Response format error: {str(e)}",
                    # ADR-036 OP-29: het rauwe resultaat gaat niet mee in de exceptie-context; die
                    # wordt via `str(exception)` in een response-body en in het log
                    # gerenderd. Alleen het TYPE en de lengte, dat plaatst de fout.
                    context={
                        "result_type": type(result).__name__,
                        "result_length": len(result_str) if result_str is not None else 0,
                    },
                ) from e

            except Exception as e:
                # Check if tool is not available
                error_msg = str(e).lower()
                if "not found" in error_msg or "unavailable" in error_msg:
                    logger.warning(f"Tool {tool_name} not available on {self.config.name}")
                    raise MCPToolNotAvailableError(
                        server_name=self.config.name,
                        tool_name=tool_name,
                        context={"error_message": str(e)},
                    ) from e

                # Protocol or communication error
                logger.exception(f"MCP tool call failed for {tool_name}: {e}")
                raise MCPProtocolError(
                    server_name=self.config.name,
                    protocol_error=f"Tool execution failed: {str(e)}",
                    original_error=e,
                    # ADR-036 OP-27: de payload gaat NIET mee. Deze context belandt via
                    # ToolBrokerException.detail in `str(exception)` en daarmee in logs
                    # en response-bodies; de toolnaam volstaat om de fout te plaatsen.
                    context={"tool_name": tool_name},
                ) from e

    async def list_tools(self) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """List available tools from MCP server"""
        async with self._lock:
            if not self.session:
                await self.connect()

            # Ensure session is not None after connect
            if self.session is None:
                raise MCPConnectionError(
                    server_name=self.config.name,
                    original_error=Exception("Session is None after connect"),
                )

            try:
                tools = await self.session.list_tools()
                # mcp 2.0 heeft Tool.inputSchema hernoemd naar input_schema. De pin in
                # requirements-base.txt is `mcp>=0.1.0`, dus welke van de twee je krijgt
                # hangt af van wanneer er geinstalleerd is -- requirements-prod.lock zegt
                # 1.27.1 (inputSchema), maar CI en de Dockerfile installeren het
                # ongepinde bestand en kregen 2.0.0 (input_schema). Beide namen afvangen
                # is hier goedkoper dan een AttributeError in productie.
                return [
                    {
                        "name": tool.name,
                        "description": tool.description,
                        "schema": getattr(tool, "input_schema", None)
                        if hasattr(tool, "input_schema")
                        else getattr(tool, "inputSchema", None),
                    }
                    for tool in tools.tools
                ]
            except Exception as e:
                logger.exception(f"Failed to list tools from {self.config.name}: {e}")
                return []


class MCPClientPool:
    """
    Connection pool for MCP clients
    Manages multiple MCP server connections
    """

    def __init__(self) -> None:
        self._clients: dict[str, MCPClient] = {}
        self._configs: dict[str, MCPServerConfig] = {}

    def register(self, config: MCPServerConfig) -> None:
        """Register an MCP server configuration"""
        self._configs[config.name] = config
        logger.info(f"Registered MCP server config: {config.name}")

    async def get_client(self, server_name: str) -> MCPClient:
        """Get or create MCP client for server"""
        if server_name not in self._clients:
            if server_name not in self._configs:
                raise ValueError(f"No configuration found for MCP server: {server_name}")

            client = MCPClient(self._configs[server_name])
            await client.connect()
            self._clients[server_name] = client

        return self._clients[server_name]

    async def close_all(self) -> None:
        """Close all MCP client connections"""
        for client in self._clients.values():
            await client.disconnect()
        self._clients.clear()
        logger.info("All MCP clients disconnected")


# Global MCP client pool
_mcp_pool: MCPClientPool | None = None


def get_mcp_pool() -> MCPClientPool:
    """Get global MCP client pool"""
    global _mcp_pool
    if _mcp_pool is None:
        _mcp_pool = MCPClientPool()
    return _mcp_pool


async def initialize_mcp_pool() -> None:
    """Initialize MCP client pool with server configurations"""
    pool = get_mcp_pool()

    # Register Serena MCP server (Conditional)
    if config.is_serena_mcp_enabled():
        # Construct absolute path to Serena service
        service_path = config.get_serena_service_path()
        abs_service_path = str(Path(os.getcwd()) / service_path)

        logger.info(f"Registering Serena MCP server from: {abs_service_path}")

        serena_config = MCPServerConfig(
            name="serena",
            command="uv",  # Assume 'uv' is in PATH
            args=[
                "run",
                "--directory",
                abs_service_path,
                "serena",
                "start-mcp-server",
                "--context",
                "ide-assistant",
                "--log-level",
                "INFO",
            ],
            env={"PYTHONUNBUFFERED": "1"},
        )
        pool.register(serena_config)
    else:
        logger.info(
            "Serena MCP server is DISABLED. Run 'python scripts/manage_serena.py enable'"
            " to activate it."
        )

    # Register Sequential Thinking MCP server
    seq_thinking_config = MCPServerConfig(
        name="sequential-thinking",
        command="npx",
        args=["-y", "@modelcontextprotocol/server-sequential-thinking"],
        env={},
    )
    pool.register(seq_thinking_config)

    logger.info("MCP client pool initialized")


async def shutdown_mcp_pool() -> None:
    """Shutdown MCP client pool"""
    global _mcp_pool
    if _mcp_pool:
        await _mcp_pool.close_all()
        _mcp_pool = None
