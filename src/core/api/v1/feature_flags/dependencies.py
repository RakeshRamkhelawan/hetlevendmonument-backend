"""
Feature Flags domain dependencies (ADR-033 Laag 1).

Shared lazy-import helpers reused by all sub-routers.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from src.core.auth.dependencies import is_platform_superuser as is_platform_superuser  # noqa: F401
from src.core.database.database import get_db as get_db  # noqa: F401
from src.core.database.tenant_query_filter import TenantFilterBypass as TenantFilterBypass  # noqa: F401

__all__ = [
    "get_db",
    "get_current_user_dep",
    "get_tenant_id",
    "is_platform_superuser",
    "TenantFilterBypass",
]


def get_current_user_dep() -> Callable[..., Awaitable[Any]]:  # TODO(TYPE): replace Any with concrete type
    """Return the platform get_current_user_dependency (lazy to avoid circular imports)."""
    from src.core.auth.dependencies import get_current_user_dependency

    return get_current_user_dependency


def get_tenant_id() -> int:
    """Return the current tenant ID from the JWT context.

    Raises RuntimeError if no tenant context is available.
    """
    from src.core.middleware.tenant_context import get_tenant_id as _get_tenant_id

    result = _get_tenant_id()
    if result is None:
        raise RuntimeError(
            "No tenant context available -- TenantMiddleware must run before this endpoint"
        )
    return result
