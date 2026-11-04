"""
Feature Flags -- admin sub-router (ADR-033 Laag 1).

Routes:
  POST /admin/features/{feature}/toggle -- toggle a feature for a specific tenant
"""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.api_deps import require_admin
from src.core.feature_flags import Feature, FeatureFlagManager
from .dependencies import get_current_user_dep, get_db, is_platform_superuser, TenantFilterBypass

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ToggleFeatureRequest(BaseModel):
    """Request body for toggling a feature flag."""

    enabled: bool


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


# De rolcontrole als dependency: 403 voordat de body gevalideerd wordt (plan nazorg, punt d).
@router.post("/admin/features/{feature}/toggle", dependencies=[Depends(require_admin)])
async def toggle_feature(
    feature: str,
    request_body: ToggleFeatureRequest,
    request: Request,
    target_tenant_id: int = Query(..., description="Target tenant ID to toggle feature for"),
    admin_user: Any = Depends(get_current_user_dep()),  # TODO(TYPE): replace Any with concrete type
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Admin: toggle a specific feature flag for a tenant.

    Requires admin role. Uses TenantFilterBypass so the current request tenant
    does not interfere with the target tenant's data.
    """

    # Een tenantbeheerder mag alleen de schakelaar van de EIGEN tenant zetten; de doeltenant komt
    # uit een queryparameter en is dus niet te vertrouwen. De eigen tenant komt uit de gebruiker
    # (token), nooit uit het verzoek. Alleen een platformbeheerder mag de tenantgrens over.
    own_tenant_id = (
        admin_user.get("tenant_id")
        if isinstance(admin_user, dict)
        else getattr(admin_user, "tenant_id", None)
    )
    if target_tenant_id != own_tenant_id and not is_platform_superuser(admin_user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You may only change feature flags of your own tenant",
        )

    try:
        Feature(feature)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid feature: {feature}. Valid features: {[f.value for f in Feature]}",
        )

    ff_manager: FeatureFlagManager | None = getattr(request.app.state, "ff_manager", None)
    if ff_manager is None:
        raise HTTPException(status_code=503, detail="Feature flag service unavailable")

    from sqlalchemy import select, text

    from src.core.feature_flags.models import FeatureFlag

    with TenantFilterBypass():
        await db.execute(
            text("SELECT set_config('app.current_tenant', :t, true)"),
            {"t": str(target_tenant_id)},
        )

        result = await db.execute(
            select(FeatureFlag).where(
                FeatureFlag.tenant_id == target_tenant_id,
                FeatureFlag.feature_name == feature,
            )
        )
        flag = result.scalar_one_or_none()

        if flag:
            flag.is_enabled = request_body.enabled
        else:
            flag = FeatureFlag(
                tenant_id=target_tenant_id,
                feature_name=feature,
                is_enabled=request_body.enabled,
            )
            db.add(flag)

        await db.commit()

    if ff_manager.redis:
        cache_key = f"{ff_manager.CACHE_KEY_PREFIX}{target_tenant_id}:{feature}"
        await ff_manager.redis.delete(cache_key)

    admin_id = (
        admin_user.get("user_id")
        if isinstance(admin_user, dict)
        else getattr(admin_user, "id", None)
    )
    logger.info(
        "Admin %s toggled feature %s for tenant %s: %s",
        admin_id,
        feature,
        target_tenant_id,
        request_body.enabled,
    )

    return {
        "success": True,
        "feature": feature,
        "tenant_id": str(target_tenant_id),
        "enabled": request_body.enabled,
    }
