"""Shared dependencies for RBAC domain routers."""

from collections.abc import Awaitable, Callable

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.dependencies import get_db
from src.core.auth.api_deps import get_current_user_id
from src.core.middleware.tenant_context import require_tenant_id
from src.core.services.rbac_service import Permission, RBACService, ReservedRoleNameError

__all__ = [
    "get_db",
    "get_current_user_id",
    "Permission",
    "require_tenant_id",
    "RBACService",
    "ReservedRoleNameError",
    "require_rbac_permission",
    "require_tenant_admin",
    "require_user_manage",
]


def require_rbac_permission(permission: str) -> Callable[..., Awaitable[int]]:
    """Rolcontrole als dependency: 403 VOORDAT de body gevalideerd wordt (plan nazorg, punt d).

    Waarom niet `src.core.auth.dependencies.require_permission`: die neemt het Enum uit
    `src.core.auth.rbac` (READ, WRITE, ADMIN, ...) en vraagt `has_permission(user, "*", value)`.
    Deze routers gebruikten altijd de tekstconstanten uit `src.core.services.rbac_service`
    (`tenant:admin`, `user:manage`) via `user_has_permission`, met de tenant uit de context.
    Gemeten 2026-10-08: de twee `Permission`-typen zijn NIET gelijk (het Enum kent geen
    TENANT_ADMIN). Deze fabriek houdt dus precies de controle die in de handlers stond.
    """

    async def rbac_permission_checker(
        db: AsyncSession = Depends(get_db),
        current_user_id: int = Depends(get_current_user_id),
    ) -> int:
        tenant_id = require_tenant_id()
        if not await RBACService(db).user_has_permission(current_user_id, permission, tenant_id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Missing permission: %s" % permission,
            )
        return current_user_id

    rbac_permission_checker.__name__ = "require_rbac_permission"
    return rbac_permission_checker


#: Rollen en hun permissies beheren.
require_tenant_admin = require_rbac_permission(Permission.TENANT_ADMIN)
#: Rollen toewijzen en intrekken.
require_user_manage = require_rbac_permission(Permission.USER_MANAGE)
