"""Factory for creating MemoryManager instances."""

import logging
from typing import Optional

from src.core.memory.facade import MemoryManager

logger = logging.getLogger(__name__)

# Tenant-scoped memory manager cache
_tenant_memory_managers: dict[int, MemoryManager] = {}


def get_memory_manager_for_tenant(
    tenant_id: int,
    redis_url: str = "redis://localhost:6379",
    encryption_key: bytes | None = None,
) -> MemoryManager:
    """Return a tenant-specific MemoryManager (lazy-init, cached)."""
    if tenant_id not in _tenant_memory_managers:
        _tenant_memory_managers[tenant_id] = MemoryManager(
            redis_url=redis_url,
            tenant_id=tenant_id,
            encryption_key=encryption_key,
        )
    return _tenant_memory_managers[tenant_id]


def get_memory_manager(
    tenant_id: int | None = None,
    redis_url: str = "redis://localhost:6379",
    encryption_key: bytes | None = None,
) -> MemoryManager:
    """Get a memory manager, optionally for a specific tenant."""
    if tenant_id is not None:
        return get_memory_manager_for_tenant(tenant_id, redis_url, encryption_key)

    # Try to get from context
    try:
        from src.core.middleware.tenant_context import get_tenant_id as _ctx_tid

        ctx_tid = _ctx_tid()
        if ctx_tid:
            return get_memory_manager_for_tenant(ctx_tid, redis_url, encryption_key)
    except Exception:
        pass

    # Return unscoped instance
    return MemoryManager(redis_url=redis_url, encryption_key=encryption_key)


class TenantContextError(Exception):
    """Raised when tenant context is required but not available.

    SECURITY FIX (P0): This error prevents cross-tenant data leakage
    by enforcing explicit tenant identification for all memory operations.
    """

    pass


def resolve_memory_manager(
    redis_url: str = "redis://localhost:6379",
    encryption_key: bytes | None = None,
) -> MemoryManager:
    """Return the tenant-scoped MemoryManager when a tenant context exists.

    SECURITY FIX (P0): Removed silent fallback to prevent cross-tenant data leakage.

    Raises:
        TenantContextError: If no tenant context is available.
    """
    try:
        from src.core.middleware.tenant_context import get_tenant_id as _ctx_tid

        _tid = _ctx_tid()
        if _tid:
            return get_memory_manager_for_tenant(_tid, redis_url, encryption_key)
    except Exception:
        pass

    # SECURITY FIX (P0): No fallback - enforce tenant context
    raise TenantContextError(
        "Tenant context required for memory manager. "
        "Ensure tenant context is set before accessing memory."
    )
