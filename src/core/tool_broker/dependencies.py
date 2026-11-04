# core/tool_broker/dependencies.py
"""
Dependency Injection Container for Tool Broker Service

Implements singleton pattern for clients and service initialization.
Ensures clients are properly configured before service instantiation.
MCP Integration: Initializes MCP pool for Serena and Sequential Thinking servers.
"""

import asyncio
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

from fastapi import Depends
from loguru import logger

from src.core.database.database import db_manager, get_db
from src.core.tool_broker.clients import SequentialThinkingClient, SerenaClient
from src.core.tool_broker.hitl_store import HITLStore
from src.core.tool_broker.local_registry import LocalToolRegistry
from src.core.tool_broker.mcp_client import initialize_mcp_pool, shutdown_mcp_pool
from src.core.tool_broker.service import ToolBrokerService


class ToolBrokerDependencies:
    """Singleton container for Tool Broker dependencies"""

    _instance: Optional["ToolBrokerDependencies"] = None
    _serena_client: SerenaClient | None = None
    _seq_thinking_client: SequentialThinkingClient | None = None
    _local_registry: LocalToolRegistry | None = None
    _service: ToolBrokerService | None = None
    _mcp_initialized: bool = False

    def __new__(cls) -> "ToolBrokerDependencies":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            logger.info("Initializing ToolBrokerDependencies singleton")
        return cls._instance

    @classmethod
    async def initialize_async(cls) -> "ToolBrokerDependencies":
        """
        Async initialization for Tool Broker dependencies
        Initializes MCP pool before creating clients
        """
        instance = cls()

        # Initialize MCP pool first
        if not instance._mcp_initialized:
            logger.info("Initializing MCP client pool")
            await initialize_mcp_pool()
            instance._mcp_initialized = True
            logger.info("MCP client pool initialized")

        if instance._serena_client is None:
            logger.info("Creating SerenaClient")
            instance._serena_client = SerenaClient()

        if instance._seq_thinking_client is None:
            logger.info("Creating SequentialThinkingClient")
            instance._seq_thinking_client = SequentialThinkingClient()

        if instance._local_registry is None:
            logger.info("Creating LocalToolRegistry")
            instance._local_registry = LocalToolRegistry()

        if instance._service is None:
            logger.info("Creating ToolBrokerService")
            instance._service = ToolBrokerService(
                serena_client=instance._serena_client,
                seq_thinking_client=instance._seq_thinking_client,
                local_registry=instance._local_registry,
                hitl_store=HITLStore(),
                audit_session_factory=db_manager.get_session,
            )

        logger.info("ToolBrokerDependencies initialization complete")
        return instance

    @classmethod
    def initialize(cls) -> "ToolBrokerDependencies":
        """
        Synchronous initialization wrapper
        Creates event loop if needed for async initialization
        """
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        return loop.run_until_complete(cls.initialize_async())

    @classmethod
    def get_serena_client(cls) -> SerenaClient:
        """Get or create SerenaClient"""
        instance = cls()
        if instance._serena_client is None:
            logger.warning("SerenaClient not initialized, creating now")
            instance._serena_client = SerenaClient()
        return instance._serena_client

    @classmethod
    def get_seq_thinking_client(cls) -> SequentialThinkingClient:
        """Get or create SequentialThinkingClient"""
        instance = cls()
        if instance._seq_thinking_client is None:
            logger.warning("SequentialThinkingClient not initialized, creating now")
            instance._seq_thinking_client = SequentialThinkingClient()
        return instance._seq_thinking_client

    @classmethod
    def get_service(cls, db: Optional["AsyncSession"] = None) -> ToolBrokerService:
        """Get or create ToolBrokerService.

        If db is provided, returns a per-request instance with HITL support.
        Otherwise returns the singleton instance (which also has a HITLStore
        configured to create sessions on demand).
        """
        instance = cls()

        # Singleton path (standard)
        if db is None:
            if instance._service is None:
                logger.warning("ToolBrokerService not initialized, initializing now")
                instance.initialize()
            if instance._service is None:
                raise RuntimeError("ToolBrokerService failed to initialize")
            return instance._service

        # Per-request path (with HITL support)
        from src.core.tool_broker.hitl_repository import HITLTicketRepository

        repo = HITLTicketRepository(db)
        hitl_store = HITLStore(repository=repo)

        return ToolBrokerService(
            serena_client=instance.get_serena_client(),
            seq_thinking_client=instance.get_seq_thinking_client(),
            local_registry=instance._local_registry,
            db_session=db,
            hitl_store=hitl_store,
            # Een EIGEN sessie per auditregel, niet de sessie van dit verzoek: de repository commit, en de
            # regel wordt als losse taak geschreven terwijl het verzoek de sessie nog gebruikt.
            audit_session_factory=db_manager.get_session,
        )

    @classmethod
    async def shutdown_async(cls) -> None:
        """
        Async shutdown for Tool Broker dependencies
        Shuts down MCP pool and cleans up resources
        """
        instance = cls()

        # Shutdown MCP pool
        if instance._mcp_initialized:
            logger.info("Shutting down MCP client pool")
            await shutdown_mcp_pool()
            instance._mcp_initialized = False
            logger.info("MCP client pool shut down")

        # Clear instances
        instance._serena_client = None
        instance._seq_thinking_client = None
        instance._service = None
        logger.info("ToolBrokerDependencies shut down")

    @classmethod
    def reset(cls) -> None:
        """Reset singleton (useful for testing)"""
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        loop.run_until_complete(cls.shutdown_async())
        logger.info("ToolBrokerDependencies reset")


# Global dependency functions for FastAPI Depends()
def get_tool_broker_service(db: "AsyncSession" = Depends(get_db)) -> ToolBrokerService:
    """FastAPI dependency for ToolBrokerService.

    The injected database session is used to build a request-scoped HITLStore,
    ensuring HIGH-risk tools can be approved via the HITL flow.
    """
    return ToolBrokerDependencies.get_service(db=db)
