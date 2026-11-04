"""User Management domain dependencies (ADR-033 Laag 1)."""

import logging

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.api_deps import (
    UserResponse as AuthUserResponse,
    get_current_user_dependency as get_current_user,
    is_admin,
)
from src.core.database.database import get_db
from src.core.database.tenant_query_filter import TenantFilterBypass
from src.core.governance.audit import audit_service
from src.core.services.rbac_service import RBACService

__all__ = [
    "audit_service",
    "get_current_user",
    "get_db",
    "RBACService",
    "require_admin",
    "TenantFilterBypass",
]

logger = logging.getLogger(__name__)


async def require_admin(
    current_user: AuthUserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AuthUserResponse:
    """Verify that the current user has admin privileges -- via `is_admin` (ADR-036 OP-40).

    Tot 2026-09-01 stond hier een eigen `role in ["admin", "system_admin"]`, exacte case en
    zonder superuser-bypass. Dat was een van de zeven eigen definities.
    """
    logger.debug("require_admin: checking user %s", current_user.email)

    if not is_admin(current_user):
        logger.warning(
            "Permission denied: user %s has roles %s (geen beheerdersrol)",
            current_user.email,
            current_user.roles or [],
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required for user management",
        )

    logger.debug("Admin access granted for user: %s", current_user.email)
    return current_user
