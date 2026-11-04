"""Tenant management domain shared dependencies (ADR-033 Laag 1)."""

import logging

from fastapi import Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.api_deps import (
    UserResponse,
    get_current_user_dependency as get_current_user,
    is_admin,
)
from src.core.database.database import get_db
from src.core.database.tenant_query_filter import TenantFilterBypass
from src.core.governance.audit import audit_service
from src.core.governance.prana_service import PranaService
from src.core.services.rbac_service import RBACService

__all__ = [
    "audit_service",
    "get_db",
    "PranaService",
    "RBACService",
    "require_admin",
    "TenantFilterBypass",
    "zaai_standaardrollen",
]

logger = logging.getLogger(__name__)


async def require_admin(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    """Verify the current user has admin privileges -- delegeert naar `is_admin` (ADR-036 OP-40).

    Tot 2026-09-01 stond hier een eigen `role in ["admin", "system_admin"]`, exacte case en
    zonder superuser-bypass. Dat was een van de zeven eigen definities.
    """
    if not is_admin(current_user):
        logger.warning(
            "Permission denied: user %s has roles %s (geen beheerdersrol)",
            current_user.email,
            current_user.roles or [],
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    return current_user


async def zaai_standaardrollen(db: AsyncSession, tenant_id: int) -> None:
    """Zaai de standaardrollen voor een nieuwe tenant.

    Staat hier en niet in de router: ADR-033 Laag 1 verbiedt een `*_router.py` om
    domeinlogica rechtstreeks te importeren, en `rbac_service` is domeinlogica. Gemeten
    2026-09-11: de eerste versie importeerde RBACService in crud_router.py en zette
    daarmee vijf architectuurguards op rood, waaronder
    test_sub_routers_do_not_directly_import_domain_logic met precies dit bestand erin.

    Waarom er uberhaupt gezaaid wordt: sinds ADR-036 OP-185 maakt `create_user` geen
    rollen meer aan, dus een tenant zonder rollen kan niemand aanmaken.
    """
    await RBACService(db).ensure_default_roles(tenant_id)
