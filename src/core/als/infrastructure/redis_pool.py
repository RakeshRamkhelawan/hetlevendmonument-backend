"""Redis Pool Manager - Shared connection pool for ALS.

CRITICAL FIX #11: Uses ONE shared pool, NOT per-tenant pools.
40 tenants x 50 connections = 2000 connections (too many!)

Tenant isolation is handled via channel naming (organism:{tenant_id}:*).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional, cast

from src.core.typing import AsyncRedisClient, create_async_redis_client

from src.core.config import get_config

settings = get_config()

logger = logging.getLogger(__name__)


class RedisPoolManager:
    """
    Manages Redis connection pool for the ALS nervous system.

    This class implements a SINGLE shared connection pool that is used
    by all tenants. Tenant isolation is achieved through channel naming
    conventions, NOT separate connections per tenant.

    Attributes:
        _client: Shared Redis client instance
        _lock: Async lock for thread-safe initialization

    Example:
        pool = RedisPoolManager()
        client = await pool.get_client()
        await client.publish(f"organism:123:cognitive", message)
    """

    def __init__(self) -> None:
        self._client: AsyncRedisClient | None = None
        self._lock = asyncio.Lock()

    async def get_client(self) -> AsyncRedisClient:
        """
        Get shared Redis client.

        FIX #11: Returns the same shared client for all tenants.
        Previous implementation created a new pool per tenant_id,
        causing connection explosion (2000+ connections).

        Returns:
            Shared Redis client
        """
        if not self._client:
            async with self._lock:
                if not self._client:
                    self._client = await self._create_client()
        return self._client

    def get_channel_name(self, tenant_id: int, tier: str) -> str:
        """
        Generate tenant-isolated channel name.

        FIX #11: Tenant isolation via naming convention, NOT separate pools.

        Args:
            tenant_id: The tenant ID
            tier: Signal tier (reflex, cognitive, etc.)

        Returns:
            Channel name like "organism:123:cognitive"
        """
        return f"organism:{tenant_id}:{tier}"

    async def _create_client(self) -> AsyncRedisClient:
        """
        Create Redis client with optimized settings.

        Configuration:
        - max_connections: 50 (shared across all tenants)
        - socket_keepalive: True (prevents connection drops)
        - socket_connect_timeout: 5s (fail fast on network issues)
        - retry_on_timeout: True (auto-recovery)
        """
        try:
            client = await create_async_redis_client(
                settings.redis_url,
                decode_responses=True,
            )

            # Verify connection
            await client.ping()

            logger.info(
                "Redis connection established",
                extra={
                    "event": "redis_connected",
                    "max_connections": 50,
                    "pool_type": "shared",
                },
            )

            return client

        except Exception as e:
            logger.error(
                f"Failed to connect to Redis: {e}",
                extra={"event": "redis_connection_failed", "error": str(e)},
            )
            raise

    async def close(self) -> None:
        """Close Redis connection gracefully."""
        if self._client:
            await self._client.close()
            self._client = None
            logger.info("Redis connection closed")

    async def health_check(self) -> bool:
        """Check if Redis connection is healthy."""
        try:
            client = await self.get_client()
            await client.ping()
            return True
        except Exception as e:
            logger.warning(f"Redis health check failed: {e}")
            return False


# Global instance (singleton)
_redis_pool: RedisPoolManager | None = None


def get_redis_pool() -> RedisPoolManager:
    """Get global RedisPoolManager instance."""
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = RedisPoolManager()
    return _redis_pool


async def close_redis_pool() -> None:
    """Close global Redis pool (for shutdown)."""
    global _redis_pool
    if _redis_pool:
        await _redis_pool.close()
        _redis_pool = None
