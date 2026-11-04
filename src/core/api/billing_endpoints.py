# orphan:exempt reason: nog niet gemigreerd naar v1/; TODO(SP-VOLGENDE): migreer naar v1/<domein>/
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.api_deps import get_current_user
from src.core.config.unified_config import config
from src.core.api.dependencies import get_db
from src.core.middleware.tenant_context import get_tenant_id
from src.core.models.rbac_models import Tenant, User
from src.core.services.subscription_cache import TenantSubscriptionCache
from src.core.utils.best_effort import best_effort

router = APIRouter(prefix="/billing", tags=["Billing"])

# Server-side mapping of Stripe price IDs to internal subscription tiers.
# In production this should be loaded from configuration or database.
PRICE_ID_TO_TIER: dict[str, str] = {
    "price_free": "free",
    "price_starter_monthly": "starter",
    "price_starter_yearly": "starter",
    "price_pro_monthly": "pro",
    "price_pro_yearly": "pro",
    "price_enterprise_monthly": "enterprise",
    "price_enterprise_yearly": "enterprise",
}


def _resolve_tier_from_price_id(price_id: str) -> str:
    """Map a Stripe price ID to an internal subscription tier.

    Unknown price IDs fall back to 'free' to prevent unauthorized tier
    escalation via manipulated price identifiers.
    """
    tier = PRICE_ID_TO_TIER.get(price_id)
    if tier:
        return tier

    # Unknown price IDs are rejected to prevent tier escalation.
    return "free"


@router.post("/create-checkout-session")
async def create_checkout_session(
    price_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Create a Stripe checkout session for the user."""
    # 1. Ensure tenant has a stripe_customer_id
    tenant_id = current_user.tenant_id
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    if not tenant.stripe_customer_id:
        from src.core.services.stripe_service import stripe_service

        customer_id = await stripe_service.create_customer(
            email=current_user.email,
            name=getattr(current_user, "full_name", current_user.email),
            metadata={
                "user_id": str(current_user.id),
                "tenant_id": str(tenant_id),
            },
        )
        if not customer_id:
            raise HTTPException(status_code=500, detail="Failed to create Stripe customer")

        tenant.stripe_customer_id = customer_id
        await db.commit()

    # 2. Generate session
    success_url = f"{config.api_host}/settings?session_id={{CHECKOUT_SESSION_ID}}"
    cancel_url = f"{config.api_host}/settings?canceled=true"

    tier = _resolve_tier_from_price_id(price_id)

    from src.core.services.stripe_service import stripe_service

    checkout_url = await stripe_service.create_checkout_session(
        customer_id=tenant.stripe_customer_id,
        success_url=success_url,
        cancel_url=cancel_url,
        price_id=price_id,
        metadata={
            "tenant_id": str(current_user.tenant_id),
            "subscription_tier": tier,
        },
    )

    if not checkout_url:
        raise HTTPException(status_code=500, detail="Failed to create checkout session")

    # Audit logging is best-effort: must not block the primary response.
    async with best_effort("checkout session created", db_session=db):
        from src.core.governance.audit import AuditService

        await AuditService.log_action(
            tenant_id=current_user.tenant_id,
            action="checkout_session_created",
            resource=f"stripe:checkout_session:{price_id}",
            user_id=current_user.id,
            details={"price_id": price_id, "tier": tier},
            session=db,
            event_type="billing",
            threat_level="info",
            client_ip="internal",
            endpoint="/billing/create-checkout-session",
            description=(f"User {current_user.id} initiated checkout for tier {tier}"),
        )
        await db.commit()

    return {"url": checkout_url}


@router.get("/status")
async def get_billing_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get the current subscription status of the user/tenant."""
    tenant_id = get_tenant_id() or current_user.tenant_id
    cache = TenantSubscriptionCache(tenant_id=tenant_id)

    cached = await cache.get()
    if cached is not None:
        return {
            "tier": cached["tier"].lower(),
            "status": cached["status"].lower(),
            "has_stripe_id": bool(current_user.stripe_customer_id),
        }

    # Cache miss - fallback to DB
    # Tenant is the root table and has no tenant_id column,
    # so ORM auto-filter does not apply here.
    result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
    tenant = result.scalar_one_or_none()

    has_stripe_id = False
    if tenant:
        tier = tenant.subscription_tier or "free"
        status = tenant.subscription_status or "active"
        has_stripe_id = bool(tenant.stripe_customer_id)
    else:
        tier = "free"
        status = "active"

    tier_lower = tier.lower()
    status_lower = status.lower()

    # Save to cache
    await cache.set(tier=tier_lower, status=status_lower)

    return {
        "tier": tier_lower,
        "status": status_lower,
        "has_stripe_id": has_stripe_id,
    }
