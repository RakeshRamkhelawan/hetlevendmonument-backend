"""
Caching Module - Production Implementation
Asynchrone caching services, session management, and cache decorators.
"""

from typing import Any

from .cache_decorators import (
    CacheInvalidationManager,
    CacheKeyBuilder,
    cache_list_results,
    cache_per_tenant,
    cache_per_user,
    cache_with_tenant_invalidation,
    get_invalidation_manager,
)
from .cache_layer import (
    AsyncCacheLayer,
    CacheConfig,
    cached,
    clear_cache,
    clear_cache_pattern,
    delete_cache,
    get_cache,
    get_cache_manager,
    get_cache_value,
    set_cache,
)
from .session_manager import RedisSessionManager, SessionData, get_session_manager

# Use a lazy-initialized proxy or the getter for cache_system
# This ensures it's an instance, not the class
cache_system = get_cache_manager()

__all__ = [
    # Cache layer
    "AsyncCacheLayer",
    "CacheConfig",
    "cached",
    "get_cache",
    "set_cache",
    "get_cache_value",
    "delete_cache",
    "clear_cache_pattern",
    "clear_cache",
    # Session management
    "RedisSessionManager",
    "SessionData",
    "get_session_manager",
    # Decorators and utilities
    "CacheKeyBuilder",
    "CacheInvalidationManager",
    "cache_with_tenant_invalidation",
    "cache_per_user",
    "cache_per_tenant",
    "cache_list_results",
    "get_invalidation_manager",
    # System
    "cache_system",
]
