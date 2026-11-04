"""Tenants list/create sub-router (ADR-033 Laag 1)."""
# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status

from src.core.api.v1.tenants.dependencies import (
    TenantService,
    audit_service,
    get_current_user,
    get_tenant_service,
    require_platform_superuser,
)
from src.core.auth.auth_service import UserResponse
from src.core.api.v1.tenants.dependencies import is_platform_superuser
from src.core.api.v1.tenants.schemas import TenantCreate, TenantListResponse, TenantResponse
from src.core.utils.best_effort import best_effort

logger = logging.getLogger(__name__)

tenants_list_router = APIRouter()


@tenants_list_router.post(
    "/",
    response_model=TenantResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new tenant",
    description="Create a new tenant organization. Superuser only.",
    dependencies=[Depends(require_platform_superuser)],
)
async def create_tenant(
    data: TenantCreate,
    service: TenantService = Depends(get_tenant_service),
    current_user: UserResponse = Depends(get_current_user),
) -> TenantResponse:
    """Create a new tenant organization."""
    # Dubbel met `require_platform_superuser` op de route (die geeft de 403 voor de body);
    # hier blijft hij voor wie de functie rechtstreeks aanroept.
    if not is_platform_superuser(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superuser privileges required",
        )

    tenant = await service.create_tenant(data)

    async with best_effort("tenant.created audit log"):
        await audit_service.log_action(
            tenant_id=tenant.id,
            action="tenant.created",
            resource=f"tenant:{tenant.id}",
            user_id=current_user.id,
            details={"name": tenant.name, "slug": tenant.slug},
            session=service.db,
        )

    logger.info("Tenant '%s' (ID: %s) created by user %s", tenant.name, tenant.id, current_user.id)
    return tenant


@tenants_list_router.get(
    "/",
    response_model=TenantListResponse,
    summary="List all tenants",
    description="List all tenants with pagination.",
)
async def list_tenants(
    skip: int = Query(0, ge=0, description="Number of items to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of items to return"),
    is_active: bool | None = Query(None, description="Filter by active status"),
    service: TenantService = Depends(get_tenant_service),
) -> TenantListResponse:
    """List tenants with optional filtering."""
    return await service.list_tenants(skip=skip, limit=limit, is_active=is_active)
