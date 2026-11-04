"""
Advanced Cache Decorators and Utilities
Provides caching strategies, invalidation patterns, and cache key management.
"""

import hashlib
import json
import logging
from functools import wraps
from typing import Any, TypeVar
from collections.abc import Callable, Coroutine

from src.core.caching.cache_layer import get_cache
from src.core.events.pubsub_manager import get_pubsub_manager

logger = logging.getLogger(__name__)


class CacheKeyBuilder:
    """Helper for building consistent cache keys"""

    @staticmethod
    def build_key(*args: Any, prefix: str = "cache", separator: str = ":") -> str:
        """
        Build cache key from arguments.

        Args:
            args: Key components
            prefix: Key prefix
            separator: Component separator

        Returns:
            Cache key string
        """
        parts = [str(arg) for arg in args if arg is not None]
        return f"{prefix}{separator}{separator.join(parts)}"

    @staticmethod
    def build_hash_key(
        data: Any, prefix: str = "cache"  # TODO(TYPE): replace Any with concrete type
    ) -> str:  # TODO(TYPE): replace Any with concrete type
        """
        Build cache key from complex data using hash.

        Args:
            data: Data to hash
            prefix: Key prefix

        Returns:
            Hashed cache key
        """
        try:
            json_str = json.dumps(data, sort_keys=True, ensure_ascii=True)
            hash_val = hashlib.md5(json_str.encode(), usedforsecurity=False).hexdigest()
            return f"{prefix}:hash:{hash_val}"
        except Exception:
            # Fallback for unhashable types
            return f"{prefix}:unhashable:{id(data)}"

    @staticmethod
    def get_user_key(user_id: int, suffix: str = "") -> str:
        """Build cache key for user data"""
        return CacheKeyBuilder.build_key(user_id, suffix, prefix="user")

    @staticmethod
    def get_tenant_key(tenant_id: int, suffix: str = "") -> str:
        """Build cache key for tenant data"""
        return CacheKeyBuilder.build_key(tenant_id, suffix, prefix="tenant")

    @staticmethod
    def get_workflow_key(workflow_id: int, suffix: str = "") -> str:
        """Build cache key for workflow data"""
        return CacheKeyBuilder.build_key(workflow_id, suffix, prefix="workflow")

    @staticmethod
    def get_agent_key(agent_id: int, suffix: str = "") -> str:
        """Build cache key for agent data"""
        return CacheKeyBuilder.build_key(agent_id, suffix, prefix="agent")


def cache_with_tenant_invalidation(
    ttl: int = 3600,
    key_prefix: str = "cached",
    invalidate_on_tenant: bool = True,
) -> Callable[..., Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Decorator for caching with automatic tenant-aware invalidation.
    Publishes cache invalidation events to other services.

    Usage:
        @cache_with_tenant_invalidation(ttl=300, key_prefix="user_data")
        async def get_user_data(user_id: int, tenant_id: int):
            # expensive operation
            return data

    Args:
        ttl: Cache TTL in seconds
        key_prefix: Cache key prefix
        invalidate_on_tenant: Whether to publish invalidation events
    """

    def decorator(
        func: Callable[..., Coroutine[Any, Any, Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> Callable[..., Coroutine[Any, Any, Any]]:  # TODO(TYPE): replace Any with concrete type
        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            cache = await get_cache()

            # Build cache key from function arguments
            cache_key = CacheKeyBuilder.build_key(
                func.__name__, *args, *kwargs.values(), prefix=key_prefix
            )

            # Try to get from cache
            cached_result = await cache.get(cache_key)
            if cached_result is not None:
                logger.debug(f"Cache hit for {func.__name__}: {cache_key}")
                return cached_result

            # Call async function
            result = await func(*args, **kwargs)

            # Cache result
            await cache.set(cache_key, result, ttl)

            # Get tenant_id from kwargs if present
            if invalidate_on_tenant and "tenant_id" in kwargs:
                pubsub = await get_pubsub_manager()
                await pubsub.publish_cache_invalidation(
                    pattern=f"{key_prefix}:*",
                    tenant_id=kwargs["tenant_id"],
                    source=func.__name__,
                )

            logger.debug(f"Cached result for {func.__name__}: {cache_key}")
            return result

        return async_wrapper

    return decorator


def cache_per_user(
    ttl: int = 1800, suffix: str = ""
) -> Callable[..., Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Decorator for user-specific caching with automatic key generation.

    Usage:
        @cache_per_user(ttl=300)
        async def get_user_preferences(user_id: int):
            return preferences

    Args:
        ttl: Cache TTL in seconds
        suffix: Additional cache key suffix
    """

    def decorator(
        func: Callable[..., Coroutine[Any, Any, Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> Callable[..., Coroutine[Any, Any, Any]]:  # TODO(TYPE): replace Any with concrete type
        @wraps(func)
        async def async_wrapper(user_id: int, *args: Any, **kwargs: Any) -> Any:
            cache = await get_cache()
            cache_key = CacheKeyBuilder.get_user_key(user_id, suffix or func.__name__)

            cached_result = await cache.get(cache_key)
            if cached_result is not None:
                logger.debug(f"Cache hit for user {user_id}: {cache_key}")
                return cached_result

            result = await func(user_id, *args, **kwargs)
            await cache.set(cache_key, result, ttl)
            logger.debug(f"Cached user data: {cache_key}")
            return result

        return async_wrapper

    return decorator


def cache_per_tenant(
    ttl: int = 3600, suffix: str = ""
) -> Callable[..., Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Decorator for tenant-specific caching with automatic invalidation.

    Usage:
        @cache_per_tenant(ttl=600)
        async def get_tenant_settings(tenant_id: int):
            return settings

    Args:
        ttl: Cache TTL in seconds
        suffix: Additional cache key suffix
    """

    def decorator(
        func: Callable[..., Coroutine[Any, Any, Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> Callable[..., Coroutine[Any, Any, Any]]:  # TODO(TYPE): replace Any with concrete type
        @wraps(func)
        async def async_wrapper(tenant_id: int, *args: Any, **kwargs: Any) -> Any:
            cache = await get_cache()
            cache_key = CacheKeyBuilder.get_tenant_key(tenant_id, suffix or func.__name__)

            cached_result = await cache.get(cache_key)
            if cached_result is not None:
                logger.debug(f"Cache hit for tenant {tenant_id}: {cache_key}")
                return cached_result

            result = await func(tenant_id, *args, **kwargs)
            await cache.set(cache_key, result, ttl)

            # Publish invalidation event
            pubsub = await get_pubsub_manager()
            await pubsub.publish_cache_invalidation(
                pattern=f"tenant:{tenant_id}:*",
                tenant_id=tenant_id,
                source=func.__name__,
            )

            logger.debug(f"Cached tenant data: {cache_key}")
            return result

        return async_wrapper

    return decorator


def cache_list_results(
    ttl: int = 300, key_prefix: str = "list", include_params: list[str] | None = None
) -> Callable[..., Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Decorator for caching list query results with filter parameters.

    Usage:
        @cache_list_results(ttl=300, include_params=["status", "limit"])
        async def list_workflows(tenant_id: int, status: str = "active", limit: int = 10):
            return workflows

    Args:
        ttl: Cache TTL in seconds
        key_prefix: Cache key prefix
        include_params: List[Any] of kwarg names to include in cache key  # TODO(TYPE): replace Any with concrete type
    """

    def decorator(
        func: Callable[..., Coroutine[Any, Any, Any]],  # TODO(TYPE): replace Any with concrete type
    ) -> Callable[..., Coroutine[Any, Any, Any]]:  # TODO(TYPE): replace Any with concrete type
        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            cache = await get_cache()

            # Build cache key including specified parameters
            key_parts = [key_prefix, func.__name__]
            if include_params:
                for param in include_params:
                    if param in kwargs:
                        key_parts.append(f"{param}={kwargs[param]}")

            cache_key = ":".join(str(p) for p in key_parts)

            cached_result = await cache.get(cache_key)
            if cached_result is not None:
                logger.debug(f"Cache hit for list: {cache_key}")
                return cached_result

            result = await func(*args, **kwargs)
            await cache.set(cache_key, result, ttl)

            logger.debug(f"Cached list results: {cache_key}")
            return result

        return async_wrapper

    return decorator


class CacheInvalidationManager:
    """
    Manager for coordinating cache invalidation across services.
    Works with pub/sub to notify other instances.
    """

    def __init__(self) -> None:
        self.invalidation_patterns: set[str] = set()

    async def register_invalidation_pattern(self, pattern: str, resource_type: str) -> bool:
        """
        Register a cache invalidation pattern.

        Args:
            pattern: Redis key pattern (e.g., "user:*", "workflow:123:*")
            resource_type: Type of resource (e.g., "user", "workflow")

        Returns:
            True if registered successfully
        """
        try:
            key = f"{resource_type}:invalidation:{pattern}"
            self.invalidation_patterns.add(key)
            logger.info(f"Registered invalidation pattern: {pattern}")
            return True
        except Exception as e:
            logger.error(f"Failed to register pattern: {e}")
            return False

    async def invalidate_user_cache(self, user_id: int, tenant_id: int | None = None) -> int:
        """
        Invalidate all cached data for a user.

        Args:
            user_id: User ID
            tenant_id: Tenant ID (for pub/sub)

        Returns:
            Number of keys invalidated
        """
        cache = await get_cache()
        pattern = f"user:{user_id}:*"
        count = await cache.clear_pattern(pattern)

        # Publish invalidation event
        pubsub = await get_pubsub_manager()
        await pubsub.publish_cache_invalidation(
            pattern=pattern,
            tenant_id=tenant_id,
            source="cache_invalidation_manager",
        )

        logger.info(f"Invalidated {count} cache entries for user {user_id}")
        return count

    async def invalidate_tenant_cache(self, tenant_id: int) -> int:
        """
        Invalidate all cached data for a tenant.

        Args:
            tenant_id: Tenant ID

        Returns:
            Number of keys invalidated
        """
        cache = await get_cache()
        pattern = f"tenant:{tenant_id}:*"
        count = await cache.clear_pattern(pattern)

        # Publish invalidation event
        pubsub = await get_pubsub_manager()
        await pubsub.publish_cache_invalidation(
            pattern=pattern,
            tenant_id=tenant_id,
            source="cache_invalidation_manager",
        )

        logger.info(f"Invalidated {count} cache entries for tenant {tenant_id}")
        return count

    async def invalidate_workflow_cache(self, workflow_id: int, tenant_id: int) -> int:
        """
        Invalidate all cached data for a workflow.

        Args:
            workflow_id: Workflow ID
            tenant_id: Tenant ID

        Returns:
            Number of keys invalidated
        """
        cache = await get_cache()
        pattern = f"workflow:{workflow_id}:*"
        count = await cache.clear_pattern(pattern)

        # Publish invalidation event
        pubsub = await get_pubsub_manager()
        await pubsub.publish_cache_invalidation(
            pattern=pattern,
            tenant_id=tenant_id,
            source="cache_invalidation_manager",
        )

        logger.info(f"Invalidated {count} cache entries for workflow {workflow_id}")
        return count

    async def invalidate_pattern(self, pattern: str, tenant_id: int | None = None) -> int:
        """
        Invalidate cache for a specific pattern.

        Args:
            pattern: Redis key pattern
            tenant_id: Tenant ID (for pub/sub)

        Returns:
            Number of keys invalidated
        """
        cache = await get_cache()
        count = await cache.clear_pattern(pattern)

        # Publish invalidation event
        pubsub = await get_pubsub_manager()
        await pubsub.publish_cache_invalidation(
            pattern=pattern,
            tenant_id=tenant_id,
            source="cache_invalidation_manager",
        )

        logger.info(f"Invalidated {count} cache entries for pattern {pattern}")
        return count


# Global instance
_invalidation_manager: CacheInvalidationManager | None = None


async def get_invalidation_manager() -> CacheInvalidationManager:
    """Get global invalidation manager instance"""
    global _invalidation_manager

    if _invalidation_manager is None:
        _invalidation_manager = CacheInvalidationManager()

    return _invalidation_manager
