"""Stripe webhook handler for subscription lifecycle events.

Handles checkout completion, subscription updates, and subscription deletions.
Implements idempotency via Redis, signature verification, and audit logging.
"""

from typing import Any

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.webhooks.dependencies import (
    AuditService,
    TenantFilterBypass,
    TenantSubscriptionCache,
    get_db,
)
from src.core.config.unified_config import config
from src.core.models.rbac_models import Tenant
from src.core.shared.redis_client import get_redis
from src.core.utils.best_effort import best_effort

router = APIRouter(prefix="/webhooks/stripe", tags=["Webhooks"])


@router.post("")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(...),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Handle Stripe webhooks for subscription updates."""
    payload = await request.body()

    # BE-SEC-055: fail-closed. HMAC met een lege sleutel is publiek
    # berekenbaar; zonder endpoint-secret is signature-verificatie waardeloos.
    webhook_secret = config.stripe_webhook_secret
    if not webhook_secret or not webhook_secret.strip():
        logger.error(
            "stripe_webhook_secret is not configured; refusing webhook (fail-closed)"
        )
        raise HTTPException(
            status_code=503,
            detail="Webhook endpoint is not configured.",
        )

    try:
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, webhook_secret
        )
    except Exception as e:
        logger.error(
            "Webhook signature verification failed: %s: %s",
            type(e).__name__,
            e,
            exc_info=True,
        )
        raise HTTPException(status_code=400, detail="Invalid signature")

    logger.info("Received Stripe event: %s", event["type"])

    # Reject test events in production
    if event.get("livemode") is False and getattr(config, "environment", "") == "production":
        raise HTTPException(
            status_code=400,
            detail="Test events not accepted in production.",
        )

    # Apply idempotency lock via Redis (fail-closed)
    event_id = event.get("id")
    if event_id:
        try:
            redis = await get_redis()
            event_ttl = getattr(config, "stripe_event_ttl", 86400)
            lock_key = f"stripe_webhook_event:{event_id}"

            # Two-phase lock: try to set "processing" with NX
            is_new = await redis.set(lock_key, "processing", ex=event_ttl, nx=True)
            if not is_new:
                # Key exists - check current state
                existing = await redis.get(lock_key)
                if existing == "processed":
                    logger.info(
                        "Stripe event %s already processed. Ignoring.",
                        event_id,
                    )
                    return {"status": "ignored"}
                # If "processing", allow re-processing (idempotent retry)
                logger.info(
                    "Stripe event %s is processing. Allowing retry.",
                    event_id,
                )
        except Exception as redis_err:
            logger.error(
                "Redis idempotency lock unavailable: %s: %s",
                type(redis_err).__name__,
                redis_err,
                exc_info=True,
            )
            # Fail-closed: if Redis is down, return 503 so Stripe retries later.
            raise HTTPException(
                status_code=503,
                detail="Service temporarily unavailable. Please retry.",
            )

    # Process events
    try:
        if event["type"] == "checkout.session.completed":
            session = event["data"]["object"]
            await handle_checkout_completed(session, db)
        elif event["type"] == "customer.subscription.updated":
            subscription = event["data"]["object"]
            await handle_subscription_updated(subscription, db)
        elif event["type"] == "customer.subscription.deleted":
            subscription = event["data"]["object"]
            await handle_subscription_deleted(subscription, db)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Stripe event processing failed: %s: %s",
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        raise HTTPException(status_code=500, detail="Event processing failed")

    # Mark event as processed in Redis
    if event_id:
        try:
            redis = await get_redis()
            await redis.set(
                f"stripe_webhook_event:{event_id}",
                "processed",
                ex=getattr(config, "stripe_event_ttl", 86400),
            )
        except Exception as redis_err:
            logger.warning(
                "Failed to mark event %s as processed: %s",
                event_id,
                redis_err,
            )

    return {"status": "success"}


async def handle_checkout_completed(
    session: Any,  # TODO(TYPE): replace Any with concrete type
    db: AsyncSession,  # TODO(TYPE): replace Any with concrete type
) -> None:  # TODO(TYPE): replace Any with concrete type
    """Process a checkout.session.completed event."""
    customer_id = session.get("customer")
    metadata = session.get("metadata") or {}
    tenant_id_str = metadata.get("tenant_id")
    tier = metadata.get("subscription_tier") or "free"

    tenant = None
    with TenantFilterBypass():
        if tenant_id_str:
            try:
                tenant_id = int(tenant_id_str)
                query = select(Tenant).where(Tenant.id == tenant_id)
                result = await db.execute(query)
                tenant = result.scalar_one_or_none()
            except ValueError:
                logger.error(
                    "Invalid tenant_id in checkout metadata: %s",
                    tenant_id_str,
                )

        if not tenant and customer_id:
            query = select(Tenant).where(Tenant.stripe_customer_id == customer_id)
            result = await db.execute(query)
            tenant = result.scalar_one_or_none()

        if tenant:
            # Security: verify customer_id matches tenant record
            if (
                customer_id
                and tenant.stripe_customer_id is not None
                and tenant.stripe_customer_id != customer_id
            ):
                logger.error(
                    "Customer ID mismatch for tenant %s: expected %s, got %s",
                    tenant.id,
                    tenant.stripe_customer_id,
                    customer_id,
                )
                return

            previous_tier = tenant.subscription_tier or "free"
            previous_status = tenant.subscription_status or "active"

            tenant.subscription_status = "active"
            tenant.subscription_tier = tier
            if customer_id:
                tenant.stripe_customer_id = customer_id
            await db.commit()
            logger.info(
                "Updated tenant %s to %s via Stripe checkout",
                tenant.id,
                tier,
            )

            # Update subscription cache
            cache = TenantSubscriptionCache(tenant_id=tenant.id)
            await cache.set(tier=tier, status="active")

            # Audit logging (best-effort)
            await _log_billing_event(
                db=db,
                tenant_id=tenant.id,
                action="checkout_completed",
                previous_tier=previous_tier,
                new_tier=tier,
                previous_status=previous_status,
                new_status="active",
                stripe_event_id=session.get("id"),
            )


async def handle_subscription_updated(
    subscription: Any,  # TODO(TYPE): replace Any with concrete type
    db: AsyncSession,  # TODO(TYPE): replace Any with concrete type
) -> None:  # TODO(TYPE): replace Any with concrete type
    """Process a customer.subscription.updated event."""
    customer_id = subscription.get("customer")
    if not customer_id:
        logger.warning("No customer_id found in subscription updated event")
        return

    status = subscription.get("status")

    with TenantFilterBypass():
        query = select(Tenant).where(Tenant.stripe_customer_id == customer_id)
        result = await db.execute(query)
        tenant = result.scalar_one_or_none()

        if not tenant:
            logger.warning(
                "No tenant found for customer %s in subscription updated event",
                customer_id,
            )
            return

        previous_tier = tenant.subscription_tier or "free"
        previous_status = tenant.subscription_status or "active"

        if status in ("canceled", "unpaid", "incomplete_expired"):
            tier = "free"
            db_status = "canceled"
        elif status == "past_due":
            tier = previous_tier  # Preserve existing tier
            db_status = "past_due"
        else:
            tier = previous_tier  # Preserve existing tier (do not hardcode "pro")
            db_status = status or "active"

        tenant.subscription_status = db_status
        tenant.subscription_tier = tier
        await db.commit()
        logger.info(
            "Updated tenant %s subscription status to %s (tier: %s)",
            tenant.id,
            db_status,
            tier,
        )

        # Update subscription cache
        cache = TenantSubscriptionCache(tenant_id=tenant.id)
        await cache.set(tier=tier, status=db_status)

        # Audit logging (best-effort)
        await _log_billing_event(
            db=db,
            tenant_id=tenant.id,
            action="subscription_updated",
            previous_tier=previous_tier,
            new_tier=tier,
            previous_status=previous_status,
            new_status=db_status,
            stripe_event_id=subscription.get("id"),
        )


async def handle_subscription_deleted(
    subscription: Any,  # TODO(TYPE): replace Any with concrete type
    db: AsyncSession,  # TODO(TYPE): replace Any with concrete type
) -> None:  # TODO(TYPE): replace Any with concrete type
    """Process a customer.subscription.deleted event."""
    customer_id = subscription.get("customer")
    if not customer_id:
        logger.warning("No customer_id found in subscription deleted event")
        return

    with TenantFilterBypass():
        query = select(Tenant).where(Tenant.stripe_customer_id == customer_id)
        result = await db.execute(query)
        tenant = result.scalar_one_or_none()

        if tenant:
            previous_tier = tenant.subscription_tier or "free"
            previous_status = tenant.subscription_status or "active"

            tenant.subscription_status = "canceled"
            tenant.subscription_tier = "free"
            await db.commit()
            logger.info("Tenant %s subscription canceled", tenant.id)

            # Update subscription cache
            cache = TenantSubscriptionCache(tenant_id=tenant.id)
            await cache.set(tier="free", status="canceled")

            # Audit logging (best-effort)
            await _log_billing_event(
                db=db,
                tenant_id=tenant.id,
                action="subscription_deleted",
                previous_tier=previous_tier,
                new_tier="free",
                previous_status=previous_status,
                new_status="canceled",
                stripe_event_id=subscription.get("id"),
            )


async def _log_billing_event(
    db: AsyncSession,
    tenant_id: int,
    action: str,
    previous_tier: str,
    new_tier: str,
    previous_status: str,
    new_status: str,
    stripe_event_id: str | None = None,
) -> None:
    """Write an audit log entry for a billing state change.

    This operation is best-effort: failures must never block the primary
    billing flow which has already succeeded.
    """
    async with best_effort("billing audit log", db_session=db):
        await AuditService.log_action(
            tenant_id=tenant_id,
            action=action,
            resource=f"stripe:{stripe_event_id or 'unknown'}",
            details={
                "previous_tier": previous_tier,
                "new_tier": new_tier,
                "previous_status": previous_status,
                "new_status": new_status,
                "stripe_event_id": stripe_event_id,
            },
            session=db,
            event_type="billing",
            threat_level="info",
            client_ip="internal",
            endpoint="/webhooks/stripe",
            description=(
                f"Billing action {action}: {previous_tier}/{previous_status} "
                f"-> {new_tier}/{new_status}"
            ),
        )
        await db.commit()
