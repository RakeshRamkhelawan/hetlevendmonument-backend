"""Tenants domain dependencies (ADR-033)."""

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.v1.orchestration.dependencies import clear_tenant_cache as clear_tenant_cache
from src.core.auth.api_deps import (
    get_current_user as get_current_user,
    is_admin,
    is_platform_superuser,
)
from src.core.auth.auth_service import UserResponse
from src.core.container import TenantContext
from src.core.database.database import get_db as get_db
from src.core.governance.audit import audit_service as audit_service
from src.core.services.tenant_service import TenantService


def get_tenant_service(
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
) -> TenantService:
    """
    Factory that builds a request-scoped TenantService from the authenticated user.

    Raises HTTPException(403) when a non-superuser has no tenant context.
    Superusers receive ``bypass_filter=True`` so they can manage any tenant.
    """
    if current_user.tenant_id is None and not is_platform_superuser(current_user):
        raise HTTPException(
            status_code=403,
            detail="Tenant context unavailable",
        )

    tenant_context = TenantContext(
        tenant_id=current_user.tenant_id,
        bypass_filter=is_platform_superuser(current_user),
    )
    return TenantService(db=db, tenant_context=tenant_context)


async def require_platform_superuser(
    current_user: UserResponse = Depends(get_current_user),
) -> UserResponse:
    """Alleen een platformbeheerder; als dependency, dus voor de validatie van de body.

    Stond tot 2026-10-08 in `create_tenant` zelf (plan nazorg, punt d).
    """
    if not is_platform_superuser(current_user):
        raise HTTPException(status_code=403, detail="Superuser privileges required")
    return current_user


async def require_own_tenant_or_superuser(
    tenant_id: int,
    current_user: UserResponse = Depends(get_current_user),
) -> UserResponse:
    """De eigen tenant (padparameter), of een platformbeheerder; voor de validatie van de body.

    Stond tot 2026-10-08 in `update_tenant` zelf (plan nazorg, punt d). Dit is een
    tenantgrens, geen rolcontrole: de controle zelf is niet gewijzigd.
    """
    if not is_platform_superuser(current_user) and current_user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="You can only modify your own tenant")
    return current_user


async def require_tenant_beheerder(
    current_user: UserResponse = Depends(get_current_user),
) -> UserResponse:
    """Alleen een beheerder (centrale definitie `is_admin`, die een superuser ook doorlaat).

    `require_own_tenant_or_superuser` toetst de tenantgrens, geen rol: tot 2026-10-08 kon elke
    gebruiker zo zijn eigen tenant wijzigen (gevonden in nazorg 2). Deze dependency staat er
    naast op `PUT /api/v1/tenants/{tenant_id}`, en geeft 403 voor de validatie van de body.
    """
    if not is_admin(current_user):
        raise HTTPException(status_code=403, detail="Admin role required")
    return current_user


__all__ = [
    "audit_service",
    "require_tenant_beheerder",
    "require_own_tenant_or_superuser",
    "require_platform_superuser",
    "clear_tenant_cache",
    "get_current_user",
    "is_platform_superuser",
    "get_tenant_service",
    "TenantService",
]
