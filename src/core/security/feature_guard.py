"""Feature gating based on tenant subscription tier.

Provides FastAPI-compatible dependencies for enforcing minimum subscription tiers
on endpoints. Includes database fallback and subscription status validation.
"""

from typing import Any

from fastapi import Depends, HTTPException, status
from sqlalchemy import select

from src.core.database.database import db_manager
from src.core.database.tenant_query_filter import TenantFilterBypass
from src.core.middleware.tenant_context import get_tenant_id
from src.core.models.rbac_models import Tenant
from src.core.services.subscription_cache import TenantSubscriptionCache

TIER_RANKING = {"free": 0, "starter": 1, "pro": 2, "enterprise": 3}

BLOCKED_STATUSES = {
    "canceled",
    "cancelled",
    "unpaid",
    "incomplete_expired",
    "suspended",
}


class RequireTier:
    """FastAPI dependency that enforces a minimum subscription tier.

    Usage:
        @router.get("/pro-feature")
        async def pro_feature(_: None = Depends(RequireTier("pro"))):
            ...
    """

    def __init__(self, required_tier: str) -> None:
        self.required_tier = required_tier.lower()

    async def __call__(self) -> None:
        tenant_id = get_tenant_id()
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="No active tenant context found.",
            )

        cache = TenantSubscriptionCache(tenant_id=tenant_id)
        sub = await cache.get()

        if sub is None:
            # Fallback to database when cache is cold or Redis is down.
            async with db_manager.get_session() as db:
                with TenantFilterBypass():
                    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
                    tenant = result.scalar_one_or_none()
                    if tenant:
                        tier = (tenant.subscription_tier or "free").lower()
                        status_str = (tenant.subscription_status or "active").lower()
                        await cache.set(tier=tier, status=status_str)
                        sub = {"tier": tier, "status": status_str}

        current_tier = sub.get("tier", "free") if sub else "free"
        current_status = sub.get("status", "active") if sub else "active"

        if current_status in BLOCKED_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "subscription_inactive",
                    "required_tier": self.required_tier,
                    "message": (
                        "This feature requires an active subscription. "
                        "Your subscription is currently inactive."
                    ),
                },
            )

        user_rank = TIER_RANKING.get(current_tier, 0)
        req_rank = TIER_RANKING.get(self.required_tier, 0)

        if user_rank < req_rank:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "error": "tier_insufficient",
                    "required_tier": self.required_tier,
                    "message": (
                        f"This feature requires a {self.required_tier.upper()} " "subscription."
                    ),
                },
            )


def require_tier(required_tier: str) -> Any:  # TODO(TYPE): replace Any with concrete type
    """Backwards-compatible factory returning a RequireTier instance.

    Note: For FastAPI endpoints use Depends(RequireTier("pro")) directly.
    This factory exists for code that dynamically builds dependencies.
    """
    return Depends(RequireTier(required_tier))
