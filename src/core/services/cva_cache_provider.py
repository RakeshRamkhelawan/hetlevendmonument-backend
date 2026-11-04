"""CvaAgentCacheProvider - thread-safe cache wrapper voor CVA agents."""

import asyncio
import logging
from typing import Any
from collections.abc import Awaitable, Callable

from cachetools import TTLCache

logger = logging.getLogger(__name__)


class CvaAgentCacheProvider:
    """Thread-safe cache provider for CVA agent instances.

    This provider wraps a TTLCache with async locks for safe concurrent access.
    It supports tenant-scoped agent caching with automatic expiration.
    """

    def __init__(self, maxsize: int = 100, ttl: int = 3600) -> None:
        """Initialize the cache provider.

        Args:
            maxsize: Maximum number of cached agents
            ttl: Time-to-live in seconds for cached entries
        """
        # Sleutel is tenant_id, waarde is de agent-instantie uit de factory.
        # TODO(TYPE): replace Any with concrete type
        self._cache: TTLCache[int, Any] = TTLCache[int, Any](maxsize=maxsize, ttl=ttl)
        self._locks: dict[int, asyncio.Lock] = {}
        self._meta_lock = asyncio.Lock()

    async def get_or_create(
        self,
        tenant_id: int,
        factory: Callable[[int], Awaitable[Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Get cached agent or create new one using factory.

        Args:
            tenant_id: The tenant ID to scope the agent to
            factory: Async factory function to create agent if not cached

        Returns:
            The cached or newly created agent instance
        """
        # Fast path - no lock needed for read
        if tenant_id in self._cache:
            return self._cache[tenant_id]

        # Slow path - need lock for write
        async with self._meta_lock:
            if tenant_id not in self._locks:
                self._locks[tenant_id] = asyncio.Lock()

        async with self._locks[tenant_id]:
            # Double-check after acquiring lock
            # (another coroutine may have created it while we waited)
            if tenant_id in self._cache:
                return self._cache[tenant_id]

            # Create new agent for this tenant
            agent = await factory(tenant_id)
            self._cache[tenant_id] = agent
            return agent

    def invalidate(self, tenant_id: int) -> None:
        """Invalidate cache entry for a tenant.

        Args:
            tenant_id: The tenant ID to invalidate
        """
        self._cache.pop(tenant_id, None)
        self._locks.pop(tenant_id, None)

    def clear(self) -> None:
        """Clear all cached entries."""
        self._cache.clear()
        self._locks.clear()

    def get_all(self) -> dict[int, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get all cached agents (for shutdown operations).

        Returns:
            Dictionary of tenant_id -> agent
        """
        return dict(self._cache)
