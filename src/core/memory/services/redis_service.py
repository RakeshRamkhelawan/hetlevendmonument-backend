from __future__ import annotations

"""Redis[Any] Service for memory persistence."""

import json
import logging
from typing import Any, Optional

import redis.asyncio as redis

from src.core.typing import AsyncRedisClient

logger = logging.getLogger(__name__)


class RedisService:
    """Service for Redis[Any] persistence operations with tenant scoping."""

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        tenant_id: int | None = None,
    ) -> None:
        self.redis_url = redis_url
        self.tenant_id = tenant_id
        self._client: AsyncRedisClient | None = None

    async def initialize(self) -> None:
        """Initialize Redis[Any] connection."""
        if self._client is None:
            from src.core.typing import create_async_redis_client

            self._client = await create_async_redis_client(self.redis_url)
            logger.debug("Redis client initialized")

    async def close(self) -> None:
        """Close Redis[Any] connection."""
        if self._client:
            await self._client.close()
            self._client = None

    def _make_key(self, key_type: str) -> str:
        """Create a tenant-scoped Redis[Any] key.

        When tenant_id is set, the key becomes ``memory:{tenant_id}:{type}``
        which guarantees data isolation between tenants.
        """
        if self.tenant_id is not None:
            return f"memory:{self.tenant_id}:{key_type}"
        return f"memory:{key_type}"

    async def get(self, key_type: str) -> str | None:
        """Get data from Redis[Any]."""
        await self._ensure_initialized()
        if self._client is None:
            return None
        try:
            data = await self._client.get(self._make_key(key_type))
            return data if data else None
        except Exception as exc:
            logger.error("Failed to get %s from Redis[Any]: %s", key_type, exc)  # TODO(TYPE): replace Any with concrete type
            return None

    async def set(self, key_type: str, data: str, expire: int | None = None) -> bool:
        """Set data in Redis[Any]."""
        await self._ensure_initialized()
        if self._client is None:
            return False
        try:
            await self._client.set(self._make_key(key_type), data, ex=expire)
            return True
        except Exception as exc:
            logger.error("Failed to set %s in Redis[Any]: %s", key_type, exc)  # TODO(TYPE): replace Any with concrete type
            return False

    async def delete(self, key_type: str) -> bool:
        """Delete data from Redis[Any]."""
        await self._ensure_initialized()
        if self._client is None:
            return False
        try:
            await self._client.delete(self._make_key(key_type))
            return True
        except Exception as exc:
            logger.error("Failed to delete %s from Redis[Any]: %s", key_type, exc)  # TODO(TYPE): replace Any with concrete type
            return False

    async def exists(self, key_type: str) -> bool:
        """Check if key exists in Redis[Any]."""
        await self._ensure_initialized()
        if self._client is None:
            return False
        try:
            return bool(await self._client.exists(self._make_key(key_type)) > 0)
        except Exception as exc:
            logger.error("Failed to check existence of %s: %s", key_type, exc)
            return False

    async def get_json(self, key_type: str) -> Any | None:  # TODO(TYPE): replace Any with concrete type
        """Get JSON data from Redis[Any]."""
        data = await self.get(key_type)
        if data:
            try:
                return json.loads(data)
            except json.JSONDecodeError as exc:
                logger.error("Failed to parse JSON for %s: %s", key_type, exc)
        return None

    async def set_json(self, key_type: str, data: Any, expire: int | None = None) -> bool:  # TODO(TYPE): replace Any with concrete type
        """Set JSON data in Redis[Any]."""
        try:
            json_str = json.dumps(data, default=str)
            return await self.set(key_type, json_str, expire)
        except Exception as exc:
            logger.error("Failed to serialize JSON for %s: %s", key_type, exc)
            return False

    async def _ensure_initialized(self) -> None:
        """Ensure Redis client is initialized."""
        if self._client is None:
            await self.initialize()
