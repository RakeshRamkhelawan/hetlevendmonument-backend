"""Thread-safe configuration registry."""

import asyncio
import logging
from typing import Any, Dict, Optional

from .loader import ConfigLoader, get_config_loader
from .models import AgentConfig

logger = logging.getLogger(__name__)


class AgentConfigRegistry:
    """
    Central registry for agent configurations.

    Features:
    - Asyncio Lock for thread safety
    - Lazy initialization
    - Singleton pattern
    """

    _instance: Optional["AgentConfigRegistry"] = None
    _initialized: bool = False

    def __new__(cls) -> "AgentConfigRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return

        self._initialized = True
        self.loader = get_config_loader()
        self._lock = asyncio.Lock()
        self._configs: dict[str, AgentConfig] = {}
        self._initialized_flag = False

    async def initialize(self, force: bool = False) -> None:
        """
        Initialize the registry with all configs.

        Args:
            force: Force re-initialization even if already initialized
        """
        async with self._lock:
            if self._initialized_flag and not force:
                return

            try:
                self._configs = self.loader.load_all()
                self._initialized_flag = True
                logger.info(f"Registry initialized with {len(self._configs)} configs")
            except Exception as e:
                logger.exception("Failed to initialize registry")
                raise

    async def get(self, agent_name: str) -> AgentConfig | None:
        """
        Get configuration for an agent.

        Args:
            agent_name: Name of the agent

        Returns:
            AgentConfig or None if not found
        """
        if not self._initialized_flag:
            await self.initialize()

        async with self._lock:
            return self._configs.get(agent_name)

    async def get_all(self) -> dict[str, AgentConfig]:
        """Get all configurations."""
        if not self._initialized_flag:
            await self.initialize()

        async with self._lock:
            return self._configs.copy()

    async def reload(self, agent_name: str) -> bool:
        """
        Reload a specific agent configuration.

        Args:
            agent_name: Name of the agent to reload

        Returns:
            True if successful, False otherwise
        """
        async with self._lock:
            config = self.loader.reload(agent_name)
            if config:
                self._configs[agent_name] = config
                logger.info(f"Reloaded config for {agent_name}")
                return True
            return False

    async def reload_all(self) -> int:
        """
        Reload all configurations.

        Returns:
            Number of configs reloaded
        """
        async with self._lock:
            try:
                self._configs = self.loader.load_all()
                count = len(self._configs)
                logger.info(f"Reloaded all configs: {count} agents")
                return count
            except Exception as e:
                logger.exception("Failed to reload all configs")
                return 0

    def get_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get registry statistics."""
        return {
            "initialized": self._initialized_flag,
            "config_count": len(self._configs),
            "loader_stats": self.loader.get_stats(),
        }

    def reset(self) -> None:
        """Reset registry state (for testing)."""
        self._initialized_flag = False
        self._configs.clear()


def get_registry() -> AgentConfigRegistry:
    """Get singleton registry instance."""
    return AgentConfigRegistry()
