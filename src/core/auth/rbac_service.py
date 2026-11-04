"""
DEPRECATED: RBACService has moved to core.services.rbac_service

This module exists for backwards compatibility only.
All imports are re-exported from the canonical location.

Migration:
    OLD: from core.auth.rbac_service import RBACService
    NEW: from core.services.rbac_service import RBACService

Phase 6 Task 4 - Service Consolidation
"""

import warnings
from typing import Optional, Protocol

warnings.warn(
    "core.auth.rbac_service is deprecated. " "Use core.services.rbac_service instead.",
    DeprecationWarning,
    stacklevel=2,
)

# Re-export from canonical location for backwards compatibility
# Keep RBACServiceProtocol for backwards compatibility with scope_validator.py
from src.core.models.rbac_models import Role

# Also re-export get_rbac_service for dependency injection compatibility
from src.core.services.rbac_service import (
    Permission,
    RBACService,
    ResourceOwnershipChecker,
    get_rbac_service,
    logger,
)


class RBACServiceProtocol(Protocol):
    """Protocol for RBAC service - enables dependency injection and testing"""

    async def has_permission(
        self, user_id: int, resource: str, action: str, tenant_id: int | None = None
    ) -> bool:
        """Check if user has permission for resource:action"""
        ...

    async def get_user_roles(self, user_id: int) -> list[Role]:
        """Get all roles assigned to a user"""
        ...


__all__ = [
    "RBACService",
    "Permission",
    "ResourceOwnershipChecker",
    "get_rbac_service",
    "RBACServiceProtocol",
    "logger",
]
