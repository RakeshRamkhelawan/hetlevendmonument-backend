"""Tenants detail/update/delete sub-router (ADR-033 Laag 1)."""
# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)

import logging

from fastapi import APIRouter, Depends, HTTPException, Response, status

from src.core.api.v1.tenants.dependencies import (
    TenantService,
    audit_service,
    clear_tenant_cache,
    get_current_user,
    get_tenant_service,
    require_own_tenant_or_superuser,
    require_tenant_beheerder,
)
from src.core.auth.auth_service import UserResponse
from src.core.api.v1.tenants.dependencies import is_platform_superuser
from src.core.api.v1.tenants.schemas import TenantResponse, TenantUpdate
from src.core.utils.best_effort import best_effort

logger = logging.getLogger(__name__)

tenants_detail_router = APIRouter()


@tenants_detail_router.get(
    "/{tenant_id}",
    response_model=TenantResponse,
    summary="Get tenant by ID",
    description="Get detailed information about a specific tenant.",
)
async def get_tenant(
    tenant_id: int,
    service: TenantService = Depends(get_tenant_service),
    current_user: UserResponse = Depends(get_current_user),
) -> TenantResponse:
    """Get a specific tenant by ID."""
    if not is_platform_superuser(current_user) and current_user.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own tenant",
        )

    tenant = await service.get_tenant(tenant_id)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant with ID {tenant_id} not found",
        )

    return tenant


@tenants_detail_router.put(
    "/{tenant_id}",
    response_model=TenantResponse,
    summary="Update tenant",
    description="Update tenant information.",
    dependencies=[Depends(require_own_tenant_or_superuser), Depends(require_tenant_beheerder)],
)
async def update_tenant(
    tenant_id: int,
    data: TenantUpdate,
    service: TenantService = Depends(get_tenant_service),
    current_user: UserResponse = Depends(get_current_user),
) -> TenantResponse:
    """Update a tenant's information."""
    # Dubbel met `require_own_tenant_or_superuser` op de route (403 voor de body).
    if not is_platform_superuser(current_user) and current_user.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only modify your own tenant",
        )

    tenant = await service.update_tenant(tenant_id, data)
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant with ID {tenant_id} not found",
        )

    async with best_effort("tenant.updated audit log"):
        await audit_service.log_action(
            tenant_id=tenant.id,
            action="tenant.updated",
            resource=f"tenant:{tenant.id}",
            user_id=current_user.id,
            details={"changes": data.model_dump(exclude_unset=True)},
            session=service.db,
        )

    logger.info("Tenant %s updated by user %s", tenant_id, current_user.id)
    return tenant


@tenants_detail_router.delete(
    "/{tenant_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete tenant (soft delete)",
    description="Deactivate a tenant. Superuser only.",
    response_class=Response,
)
async def delete_tenant(
    tenant_id: int,
    service: TenantService = Depends(get_tenant_service),
    current_user: UserResponse = Depends(get_current_user),
) -> None:
    """Soft delete a tenant by deactivating it."""
    if not is_platform_superuser(current_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superuser privileges required",
        )

    deleted = await service.delete_tenant(tenant_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant with ID {tenant_id} not found",
        )

    async with best_effort("tenant.deleted audit log"):
        await audit_service.log_action(
            tenant_id=tenant_id,
            action="tenant.deleted",
            resource=f"tenant:{tenant_id}",
            user_id=current_user.id,
            details={"deactivated": True},
            session=service.db,
        )

    clear_tenant_cache(tenant_id)
    logger.info("Tenant %s deactivated by user %s", tenant_id, current_user.id)
