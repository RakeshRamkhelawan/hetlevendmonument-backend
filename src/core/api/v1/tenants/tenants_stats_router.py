"""Tenants stats sub-router (ADR-033 Laag 1)."""
# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from src.core.api.v1.tenants.dependencies import (
    TenantService,
    get_current_user,
    get_tenant_service,
)
from src.core.auth.auth_service import UserResponse
from src.core.api.v1.tenants.dependencies import is_platform_superuser
from src.core.api.v1.tenants.schemas import TenantStats

logger = logging.getLogger(__name__)

tenants_stats_router = APIRouter()


@tenants_stats_router.get(
    "/{tenant_id}/stats",
    response_model=TenantStats,
    summary="Get tenant statistics",
    description="Get usage statistics for a tenant.",
)
async def get_tenant_stats(
    tenant_id: int,
    service: TenantService = Depends(get_tenant_service),
    current_user: UserResponse = Depends(get_current_user),
) -> TenantStats:
    """Get statistics for a specific tenant."""
    if not is_platform_superuser(current_user) and current_user.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only access your own tenant statistics",
        )

    stats = await service.get_tenant_stats(tenant_id)
    if stats is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant with ID {tenant_id} not found",
        )

    return stats
