"""Shared Redis client helper for async Redis access."""

from __future__ import annotations

import os
from typing import Optional

from src.core.typing import AsyncRedisClient, create_async_redis_client

_redis_client: AsyncRedisClient | None = None


async def get_redis() -> AsyncRedisClient:
    """Return a shared async Redis client instance."""
    global _redis_client
    if _redis_client is None:
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        _redis_client = await create_async_redis_client(redis_url, decode_responses=True)
    return _redis_client
