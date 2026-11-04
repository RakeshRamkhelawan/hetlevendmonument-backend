"""
Feature Flags -- tenant-scoped sub-router (ADR-033 Laag 1).

Routes:
  GET /tenant/features       -- list tenant's enabled features
  GET /tenant/tier           -- get tenant's subscription tier + upgrade info
  GET /tenant/features/{feature}/check -- check a specific feature
"""

import logging
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from .dependencies import get_db
from src.core.models.rbac_models import Tenant
from src.core.feature_flags import (
    Feature,
    FeatureFlagManager,
    Tier,
    get_missing_features,
    get_tier_features,
    get_tier_for_feature,
)

from .dependencies import get_current_user_dep, get_tenant_id
from .features_router import FEATURE_DESCRIPTIONS, TIER_PRICING

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class TenantFeaturesResponse(BaseModel):
    """Current tenant's enabled features."""

    tenant_id: str
    tier: str
    enabled_features: list[str]
    total_features: int


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/tenant/features", response_model=TenantFeaturesResponse)
async def get_tenant_features(
    request: Request,
    current_user: Any = Depends(get_current_user_dep()),  # TODO(TYPE): replace Any with concrete type
    db: AsyncSession = Depends(get_db),
) -> TenantFeaturesResponse:
    """Get current tenant's enabled features."""
    tenant_id = get_tenant_id()
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No tenant context available",
        )

    from sqlalchemy import select

    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant {tenant_id} not found",
        )

    tier = Tier(tenant.plan)
    features = get_tier_features(tier)

    return TenantFeaturesResponse(
        tenant_id=str(tenant_id),
        tier=tier.value,
        enabled_features=[f.value for f in features],
        total_features=len(features),
    )


@router.get("/tenant/tier")
async def get_tenant_tier(
    current_user: Any = Depends(get_current_user_dep()),  # TODO(TYPE): replace Any with concrete type
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get current tenant's subscription tier with upgrade information."""
    tenant_id = get_tenant_id()

    from sqlalchemy import select

    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tenant {tenant_id} not found",
        )

    current_tier = Tier(tenant.plan)

    tier_order = [Tier.STARTER, Tier.PRO, Tier.ENTERPRISE]
    try:
        current_index = tier_order.index(current_tier)
    except ValueError:
        # FREE tier is not in tier_order upgrade path
        current_index = -1
    next_tier = tier_order[current_index + 1] if 0 <= current_index < len(tier_order) - 1 else None

    result_dict: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
        "current_tier": current_tier.value,
        "current_price": TIER_PRICING[current_tier]["price"],
    }

    if next_tier:
        missing_features = get_missing_features(current_tier, next_tier)
        result_dict.update(
            {
                "next_tier": next_tier.value,
                "missing_features": [f.value for f in missing_features],
                "upgrade_price": cast(float, TIER_PRICING[next_tier]["price"])
                - cast(float, TIER_PRICING[current_tier]["price"]),
                "upgrade_url": f"/upgrade?from={current_tier.value}&to={next_tier.value}",
            }
        )

    return result_dict


@router.get("/tenant/features/{feature}/check")
async def check_feature(
    feature: str,
    request: Request,
    current_user: Any = Depends(get_current_user_dep()),  # TODO(TYPE): replace Any with concrete type
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Check if a specific feature is enabled for the current tenant."""
    tenant_id = get_tenant_id()

    try:
        feature_enum = Feature(feature)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid feature: {feature}",
        )

    ff_manager: FeatureFlagManager | None = getattr(request.app.state, "ff_manager", None)
    if ff_manager is None:
        raise HTTPException(status_code=503, detail="Feature flag service unavailable")

    is_enabled = await ff_manager.is_enabled(str(tenant_id), feature_enum)

    from sqlalchemy import select

    db_result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = db_result.scalar_one_or_none()
    current_tier = Tier(tenant.plan) if tenant else Tier.STARTER

    minimum_tier = get_tier_for_feature(feature_enum)

    return {
        "feature": feature,
        "enabled": is_enabled,
        "minimum_tier": minimum_tier.value,
        "current_tier": current_tier.value,
        "description": FEATURE_DESCRIPTIONS.get(feature_enum, ""),
        "upgrade_required": not is_enabled,
        "upgrade_url": f"/upgrade?feature={feature}" if not is_enabled else None,
    }
