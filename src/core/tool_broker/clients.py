# core/tool_broker/clients.py
"""
Tool Broker Clients - Real MCP Integration
Updated with native MCP protocol support for Serena and Sequential Thinking
"""

from typing import Any, Protocol

from src.core.shared.production_logging import SafeLogger
from src.core.tool_broker.exceptions import (
    MCPConnectionError,
    MCPProtocolError,
    MCPToolNotAvailableError,
)
from src.core.tool_broker.mcp_client import get_mcp_pool

logger = SafeLogger(__name__)


class ISerenaClient(Protocol):
    """Protocol for Serena client"""

    async def call(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]: ...  # TODO(TYPE): replace Any with concrete type


class ISequentialThinkingClient(Protocol):
    """Protocol for Sequential Thinking client"""

    async def call(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]: ...  # TODO(TYPE): replace Any with concrete type


class SerenaClient:
    """
    Serena MCP Client
    Communicates with Serena via native MCP protocol (stdio)
    """

    def __init__(self) -> None:
        self.server_name = "serena"
        logger.info("SerenaClient initialized with MCP protocol")

    async def call(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Call a Serena tool via MCP protocol

        Args:
            tool_name: Name of the Serena tool (e.g., 'find_symbol', 'read_file')
            payload: Tool arguments

        Returns:
            Tool execution result
        """
        try:
            logger.info(f"SerenaClient calling tool: {tool_name}")

            # Get MCP client from pool
            pool = get_mcp_pool()
            mcp_client = await pool.get_client(self.server_name)

            # Call tool via MCP protocol
            result = await mcp_client.call_tool(tool_name, payload)

            logger.info(f"SerenaClient tool {tool_name} completed")
            return result

        except (MCPConnectionError, MCPProtocolError, MCPToolNotAvailableError):
            # Re-raise MCP-specific exceptions without wrapping
            raise

        except Exception as e:
            # Wrap unexpected errors
            logger.exception(f"SerenaClient unexpected error calling {tool_name}: {e}")
            raise MCPProtocolError(
                server_name=self.server_name,
                protocol_error=f"Unexpected error: {str(e)}",
                original_error=e,
                # ADR-036 OP-27/OP-29: de payload staat hier BEWUST niet meer in. Deze context
                # belandt via ToolBrokerException.detail in `str(exception)`, en dat gaat
                # naar de HTTP-500-body, het applicatielog en de proces-globale
                # uitvoeringsgeschiedenis -- die laatste is API-uitleesbaar. De payload is
                # modeloutput en kan persoonsgegevens bevatten; de toolnaam volstaat om de
                # fout te plaatsen.
                context={"tool_name": tool_name},
            ) from e


class SequentialThinkingClient:
    """
    Sequential Thinking MCP Client
    Communicates with Sequential Thinking via native MCP protocol (stdio)
    """

    def __init__(self) -> None:
        self.server_name = "sequential-thinking"
        logger.info("SequentialThinkingClient initialized with MCP protocol")

    async def call(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Call a Sequential Thinking tool via MCP protocol

        Args:
            tool_name: Name of the tool (typically 'sequentialthinking')
            payload: Tool arguments (thought, thoughtNumber, totalThoughts, etc.)

        Returns:
            Tool execution result
        """
        try:
            logger.info(f"SequentialThinkingClient calling tool: {tool_name}")

            # Get MCP client from pool
            pool = get_mcp_pool()
            mcp_client = await pool.get_client(self.server_name)

            # Call tool via MCP protocol
            result = await mcp_client.call_tool(tool_name, payload)

            logger.info(f"SequentialThinkingClient tool {tool_name} completed")
            return result

        except (MCPConnectionError, MCPProtocolError, MCPToolNotAvailableError):
            # Re-raise MCP-specific exceptions without wrapping
            raise

        except Exception as e:
            # Wrap unexpected errors
            logger.exception(f"SequentialThinkingClient unexpected error calling {tool_name}: {e}")
            raise MCPProtocolError(
                server_name=self.server_name,
                protocol_error=f"Unexpected error: {str(e)}",
                original_error=e,
                # ADR-036 OP-27/OP-29: de payload staat hier BEWUST niet meer in. Deze context
                # belandt via ToolBrokerException.detail in `str(exception)`, en dat gaat
                # naar de HTTP-500-body, het applicatielog en de proces-globale
                # uitvoeringsgeschiedenis -- die laatste is API-uitleesbaar. De payload is
                # modeloutput en kan persoonsgegevens bevatten; de toolnaam volstaat om de
                # fout te plaatsen.
                context={"tool_name": tool_name},
            ) from e
