"""Foundation Portal Tenant Resolution router (ADR-029 P2-1, ADR-033 Laag 2)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Query, Request

from src.core.api.v1.foundation.dependencies import (
    Tenant,
    get_public_tenant,
    portal_public_read_limit,
)
from src.core.api.v1.foundation.schemas import TenantPublicInfo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/foundation/tenant", tags=["foundation-tenant"])


@router.get(
    "/resolve",
    response_model=TenantPublicInfo,
    summary="Resolve tenant public info from host header or query params",
    description=(
        "Public endpoint used by frontend for bootstrap resolution. Resolves "
        "tenant by custom domain, subdomain, ?slug= or ?domain=."
    ),
)
@portal_public_read_limit
async def resolve_tenant_endpoint(
    request: Request,
    tenant: Tenant = Depends(get_public_tenant),
) -> TenantPublicInfo:
    """Resolve active tenant from request and return public metadata."""
    return TenantPublicInfo.model_validate(tenant)
