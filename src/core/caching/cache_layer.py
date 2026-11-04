from __future__ import annotations

"""
Asynchrone Caching Service - Production Implementation
AsyncRedisClient.asyncio-based caching service zoals gespecificeerd in FASE 1 STAP 1.4
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from functools import wraps
from typing import Any, TypeVar, cast
from collections.abc import Awaitable, Callable

T = TypeVar("T")

import redis  # top-level -- needed for redis.ConnectionError exception class
import redis.asyncio as aioredis

from src.core.config.config import get_settings
from src.core.middleware.tenant_context import get_tenant_id
from src.core.typing import AsyncRedisClient

logger = logging.getLogger(__name__)


@dataclass
class CacheConfig:
    """Asynchrone cache configuration settings"""

    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str | None = None
    socket_timeout: int = 5
    socket_connect_timeout: int = 5
    default_ttl: int = 3600  # 1 hour default TTL
    max_connections: int = 10


class AsyncCacheLayer:
    """
    Production-grade asynchrone caching layer zoals gespecificeerd in FASE 1 STAP 1.4
    Gebruik redis.asyncio voor alle operaties
    """

    def __init__(self, config: CacheConfig | None = None) -> None:
        self.config = config or CacheConfig()
        self.redis_client: AsyncRedisClient | None = None
        self.connected = False

    async def connect(self) -> bool:
        """Establish asynchronous AsyncRedisClient connection"""
        try:
            settings = get_settings()

            # Parse AsyncRedisClient URL from settings
            redis_url = settings.redis_url

            from src.core.typing import create_async_redis_client

            self.redis_client = await create_async_redis_client(redis_url, decode_responses=True)

            # Test connection asynchronously
            await self.redis_client.ping()
            self.connected = True
            logger.info("Async cache layer connected to AsyncRedisClient successfully")
            return True

        except redis.ConnectionError as e:
            logger.warning(f"AsyncRedisClient connection failed: {e}")
            self.connected = False
            return False
        except Exception as e:
            logger.error(
                "Cache layer initialization failed: %s: %s", type(e).__name__, e, exc_info=True
            )
            self.connected = False
            return False

    async def disconnect(self) -> None:
        """Close AsyncRedisClient connection asynchronously"""
        if self.redis_client:
            try:
                # redis-py 5.0+ uses aclose(); 4.x uses close()
                if hasattr(self.redis_client, "aclose"):
                    await self.redis_client.aclose()  # pyright: ignore[reportAttributeAccessIssue]
                else:
                    await self.redis_client.close()
                self.connected = False
                logger.info("Async cache layer disconnected")
            except Exception as e:
                logger.error(
                    "Error disconnecting cache: %s: %s", type(e).__name__, e, exc_info=True
                )

    async def set(self, key: str, value: object, ttl: int | None = None) -> bool:
        """
        Store value in cache with optional TTL (ASYNC)
        Zoals gespecificeerd: converteer naar async def en gebruik await voor AsyncRedisClient-operatie

        Args:
            key: Cache key
            value: Value to cache (will be JSON serialized)
            ttl: Time to live in seconds (None for default)
        """
        if not self.connected or self.redis_client is None:
            return False

        try:
            # Serialize value to JSON
            serialized_value = json.dumps(value, ensure_ascii=True)

            # Set TTL
            expire_time = ttl or self.config.default_ttl

            # Store in Redis asynchronously
            result = await self.redis_client.setex(key, expire_time, serialized_value)

            logger.debug(f"Cached key: {key} (TTL: {expire_time}s)")
            return bool(result)

        except (
            TypeError,
            ValueError,
        ) as e:  # Changed from JSONEncodeError (Python 3.13 compatibility)
            logger.error(
                "Value serialization failed for key %s: %s: %s",
                key,
                type(e).__name__,
                e,
                exc_info=True,
            )
            return False
        except Exception as e:
            logger.error(
                "Cache set failed for key %s: %s: %s", key, type(e).__name__, e, exc_info=True
            )
            return False

    async def get(self, key: str) -> object | None:
        """
        Retrieve value from cache (ASYNC)
        Zoals gespecificeerd: converteer naar async def en gebruik await voor AsyncRedisClient-operatie

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        if not self.connected or self.redis_client is None:
            return None

        try:
            # Retrieve from Redis asynchronously
            serialized_value = await self.redis_client.get(key)

            if serialized_value is None:
                logger.debug(f"Cache miss: {key}")
                return None

            # Deserialize JSON
            value = json.loads(serialized_value)
            logger.debug(f"Cache hit: {key}")
            return cast(object, value)

        except json.JSONDecodeError as e:
            logger.error(
                "Value deserialization failed for key %s: %s: %s",
                key,
                type(e).__name__,
                e,
                exc_info=True,
            )
            return None
        except Exception as e:
            logger.error(
                "Cache get failed for key %s: %s: %s", key, type(e).__name__, e, exc_info=True
            )
            return None

    async def delete(self, key: str) -> bool:
        """
        Delete key from cache (ASYNC)
        Zoals gespecificeerd: converteer naar async def en gebruik await voor AsyncRedisClient-operatie
        """
        if not self.connected or self.redis_client is None:
            return False

        try:
            result = await self.redis_client.delete(key)
            logger.debug(f"Cache delete: {key}")
            return bool(result)

        except Exception as e:
            logger.error(
                "Cache delete failed for key %s: %s: %s", key, type(e).__name__, e, exc_info=True
            )
            return False

    async def exists(self, key: str) -> bool:
        """Check if key exists in cache (ASYNC)"""
        if not self.connected or self.redis_client is None:
            return False

        try:
            result = await self.redis_client.exists(key)
            return bool(result)

        except Exception as e:
            logger.error(
                "Cache exists check failed for key %s: %s: %s",
                key,
                type(e).__name__,
                e,
                exc_info=True,
            )
            return False

    async def clear_pattern(self, pattern: str) -> int:
        """Clear all keys matching pattern (ASYNC)"""
        if not self.connected or self.redis_client is None:
            return 0

        try:
            keys = await self.redis_client.keys(pattern)

            if keys:
                count = await self.redis_client.delete(*keys)
                logger.info(f"Cleared {count} keys matching pattern: {pattern}")
                return int(count)
            return 0

        except Exception as e:
            logger.error(
                "Cache pattern clear failed for pattern %s: %s: %s",
                pattern,
                type(e).__name__,
                e,
                exc_info=True,
            )
            return 0

    async def get_stats(self) -> dict[str, object]:
        """Get cache statistics (ASYNC)"""
        if not self.connected or self.redis_client is None:
            return {"connected": False}

        try:
            info = await self.redis_client.info()
            return {
                "connected": True,
                "redis_version": info.get("redis_version"),
                "used_memory": info.get("used_memory"),
                "connected_clients": info.get("connected_clients"),
                "total_commands_processed": info.get("total_commands_processed"),
                "instantaneous_ops_per_sec": info.get("instantaneous_ops_per_sec"),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
            }

        except Exception as e:
            logger.error("Failed to get cache stats: %s: %s", type(e).__name__, e, exc_info=True)
            return {"connected": True, "error": str(e)}


# Global async cache instance
_cache_instance: AsyncCacheLayer | None = None


async def get_cache() -> AsyncCacheLayer:
    """Get global async cache instance (singleton pattern with auto-reconnect)"""
    global _cache_instance

    if _cache_instance is None:
        _cache_instance = AsyncCacheLayer()

    # Auto-reconnect if instance exists but is not connected
    if not _cache_instance.connected:
        await _cache_instance.connect()

    return _cache_instance


def cached(
    ttl: int = 3600, key_prefix: str = "cached"
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """
    Asynchrone decorator voor caching function results
    Ondersteunt zowel functies als klasse-methoden.
    """

    def decorator(
        func: Callable[..., Awaitable[T]],
    ) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> T:
            try:
                cache = await get_cache()

                # Generate cache key
                # Skip 'self' (args[0]) if it looks like a class method
                # We use a string representation of args/kwargs for stable hashing
                if args and hasattr(args[0], "__class__") and func.__name__ in dir(args[0]):
                    relevant_args = args[1:]
                else:
                    relevant_args = args

                arg_str = str(relevant_args)
                kwarg_str = str(sorted(kwargs.items()))
                _tid = get_tenant_id() or 0
                # NOTE: t0 = system namespace; never a real tenant (tenant_id > 0 per ADR-005)
                _arg_hash = hashlib.md5(
                    (arg_str + kwarg_str).encode(), usedforsecurity=False
                ).hexdigest()
                cache_key = f"t{_tid}:{key_prefix}:{func.__name__}:{_arg_hash}"

                # Try to get from cache
                cached_result = await cache.get(cache_key)
                if cached_result is not None:
                    logger.debug(f"Cache hit for {func.__name__}")
                    return cast(T, cached_result)

                # Call async function
                result = await func(*args, **kwargs)

                # Cache result
                await cache.set(cache_key, result, ttl)
                logger.debug(f"Cached result for {func.__name__}")
                return result
            except Exception as e:
                logger.warning(f"Cache decorator error for {func.__name__}: {e}")
                # Fallback to direct call on error
                return await func(*args, **kwargs)

        return async_wrapper

    return decorator


# Convenience async functions
async def set_cache(key: str, value: object, ttl: int | None = None) -> bool:
    """Set cache value directly (ASYNC)"""
    cache = await get_cache()
    return await cache.set(key, value, ttl)


async def get_cache_value(key: str) -> object | None:
    """Get cache value directly (ASYNC)"""
    cache = await get_cache()
    return await cache.get(key)


async def delete_cache(key: str) -> bool:
    """Delete cache value directly (ASYNC)"""
    cache = await get_cache()
    return await cache.delete(key)


async def clear_cache_pattern(pattern: str) -> int:
    """Clear cache pattern directly (ASYNC)"""
    cache = await get_cache()
    return await cache.clear_pattern(pattern)


async def clear_cache() -> int:
    """Clear entire cache - convenience wrapper for main.py compatibility"""
    return await clear_cache_pattern("*")


def get_cache_manager() -> AsyncCacheLayer:
    """
    Get cache manager instance (synchronous interface for compatibility).
    Returns the global async cache instance.
    """
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = AsyncCacheLayer()
    return _cache_instance
