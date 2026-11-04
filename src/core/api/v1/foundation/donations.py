"""Foundation Portal donations and adoption endpoints (BE-EP-046 / ADR-029 P2-2)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.v1.foundation.dependencies import (
    StripeNotConfiguredError,
    StripeWebhookSecretMissingError,
    get_db,
    portal_public_read_limit,
    portal_public_write_limit,
    public_tenant_scope,
    require_curator,
    stripe_service,
)
from src.core.api.v1.foundation.schemas import (
    DonationAdminItem,
    DonationAdminListResponse,
    DonationCheckoutRequest,
    DonationCheckoutResponse,
    DonationHistoryItem,
    DonationStatsResponse,
)
from src.core.config.unified_config import config
from src.core.models.foundation_content import FoundationDonation, PortalUser
from src.core.security.hcaptcha import require_hcaptcha
from src.core.shared.datetime_utils import utc_now

router = APIRouter(tags=["foundation-donations"])


@router.post(
    "/donations/checkout",
    response_model=DonationCheckoutResponse,
    status_code=status.HTTP_200_OK,
    summary="Create Stripe Checkout Session for a donation or adoption",
)
@portal_public_write_limit
async def create_donation_checkout(
    tenantSlug: str,
    payload: DonationCheckoutRequest,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Create a Stripe checkout session for a one-time or monthly donation.

    - Rate limited to 30 requests/min.
    - Verified against hCaptcha bot protection.
    - Validates amount (EUR 1.00 to EUR 5,000.00).
    - Supports anonymous donation flag.
    - Persists donation in foundation_donations with 'pending' status.
    - Fail-closed (BE-SEC-058): returns 503 when Stripe is not configured;
      no mock checkout session is ever generated.
    """
    client_ip = request.client.host if request.client else None
    await require_hcaptcha(payload.hcaptcha_token, remote_ip=client_ip)

    async with public_tenant_scope(tenantSlug, session) as tenant:
        frontend_base = (
            getattr(config, "portal_frontend_url", "").rstrip("/")
            or f"{request.base_url.scheme}://{request.base_url.netloc}"
        )
        success_url = f"{frontend_base}/doneren/bedankt?session_id={{CHECKOUT_SESSION_ID}}"
        cancel_url = f"{frontend_base}/doneren?canceled=true"

        metadata = {
            "tenant_id": str(tenant.id),
            "tenant_slug": tenantSlug,
            "donor_email": str(payload.donor_email),
            "donor_name": payload.donor_name or "",
            "is_anonymous": "true" if payload.is_anonymous else "false",
            "frequency": payload.frequency,
            "monument_id": str(payload.monument_id) if payload.monument_id else "",
            "donation_type": "heritage_donation",
        }

        try:
            checkout_url, session_id = await stripe_service.create_donation_checkout_session(
                amount_cents=payload.amount_cents,
                currency="eur",
                donor_email=str(payload.donor_email),
                is_monthly=(payload.frequency == "monthly"),
                success_url=success_url,
                cancel_url=cancel_url,
                metadata=metadata,
            )
        except StripeNotConfiguredError as exc:
            logger.error(
                "Donation checkout requested but Stripe is not configured (tenant={})",
                tenantSlug,
            )
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Betalingen zijn tijdelijk niet beschikbaar. Probeer het later opnieuw.",
            ) from exc

        if not checkout_url or not session_id:
            logger.error("Failed to generate checkout session via stripe_service")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Er is een fout opgetreden bij het aanmaken van de betaalsessie.",
            )

        # Persisteer donatie in de database (ADR-029 audit hardening)
        donation = FoundationDonation(
            tenant_id=tenant.id,
            email=str(payload.donor_email),
            amount_cents=payload.amount_cents,
            currency="EUR",
            frequency=str(payload.frequency),
            status="pending",
            donor_name=payload.donor_name,
            is_anonymous=payload.is_anonymous,
            adopted_content_id=payload.monument_id,
            stripe_session_id=session_id,
            message=payload.message,
        )
        session.add(donation)
        await session.commit()
        await session.refresh(donation)

        logger.info(
            "Donation checkout initiated: tenant={} amount_cents={} session_id={}",
            tenantSlug,
            payload.amount_cents,
            session_id,
        )

        return {
            "checkout_url": checkout_url,
            "session_id": session_id,
            "amount_cents": payload.amount_cents,
            "frequency": payload.frequency,
        }


@router.get(
    "/donations/stats",
    response_model=DonationStatsResponse,
    summary="Get transparency statistics and recent supporters for the foundation",
)
@portal_public_read_limit
async def get_donation_stats(
    request: Request,
    tenantSlug: str,
    session: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Public statistics showing total raised, donor count and recent public supporters.

    Queries only completed donations from PostgreSQL with strict multi-tenant isolation.


    `request` is required by `portal_public_read_limit`: without a real Request parameter the
    limiter cannot key on the caller and silently does nothing (guard added upstream, 2026-10).
    """
    async with public_tenant_scope(tenantSlug, session) as tenant:
        totals_stmt = select(
            func.coalesce(func.sum(FoundationDonation.amount_cents), 0),
            func.count(FoundationDonation.id),
        ).where(
            FoundationDonation.tenant_id == tenant.id,
            FoundationDonation.status == "completed",
        )
        totals_res = await session.execute(totals_stmt)
        row = totals_res.first()
        total_cents = int(row[0]) if row and row[0] is not None else 0
        total_count = int(row[1]) if row and row[1] is not None else 0

        monthly_stmt = select(func.count(FoundationDonation.id)).where(
            FoundationDonation.tenant_id == tenant.id,
            FoundationDonation.status == "completed",
            FoundationDonation.frequency == "monthly",
        )
        monthly_res = await session.execute(monthly_stmt)
        monthly_count = monthly_res.scalar() or 0

        # Haal de meest recente afgeronde donaties op (maximaal 10)
        recent_stmt = (
            select(FoundationDonation)
            .where(
                FoundationDonation.tenant_id == tenant.id,
                FoundationDonation.status == "completed",
            )
            .order_by(FoundationDonation.created_at.desc())
            .limit(10)
        )
        recent_res = await session.execute(recent_stmt)
        recent_rows = recent_res.scalars().all()

        recent_items: list[dict[str, object]] = []
        for d in recent_rows:
            donor_display = (
                "Anonieme Vriend van het Monument"
                if d.is_anonymous
                else (d.donor_name or "Vriend van het Monument")
            )
            recent_items.append(
                {
                    "id": d.id,
                    "amount_cents": d.amount_cents,
                    "frequency": d.frequency,
                    "donor_name": donor_display,
                    "message": d.message,
                    "created_at": d.created_at.isoformat() if d.created_at else "",
                    "is_anonymous": d.is_anonymous,
                }
            )

        return {
            "total_raised_cents": total_cents,
            "total_donations_count": total_count,
            "monthly_supporters_count": monthly_count,
            "recent_donations": recent_items,
        }


@router.post(
    "/donations/webhook",
    summary="Handle incoming Stripe webhook events for donations",
)
async def stripe_donations_webhook(
    tenantSlug: str,
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Process Stripe webhook events (checkout.session.completed) to finalize donations.

    Fail-closed (BE-SEC-058): without a configured webhook signing secret the
    payload is never parsed and the endpoint answers 503; an invalid or missing
    Stripe-Signature header answers 400. In both cases no state is changed.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    try:
        event = stripe_service.construct_webhook_event(payload, sig_header)
    except StripeWebhookSecretMissingError as err:
        logger.error(
            "Stripe donations webhook refused for tenant {}: webhook secret not configured",
            tenantSlug,
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook verification is not configured",
        ) from err
    except Exception as err:
        logger.warning("Stripe webhook verification error for tenant {}: {}", tenantSlug, err)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook signature verification failed",
        ) from err

    event_type = event.get("type")
    logger.info("Stripe webhook event received: {} for tenant {}", event_type, tenantSlug)

    if event_type == "checkout.session.completed":
        session_obj = event.get("data", {}).get("object", {})
        session_id = session_obj.get("id")
        payment_intent_id = session_obj.get("payment_intent")

        if session_id:
            async with public_tenant_scope(tenantSlug, session) as tenant:
                stmt = select(FoundationDonation).where(
                    FoundationDonation.tenant_id == tenant.id,
                    FoundationDonation.stripe_session_id == session_id,
                )
                res = await session.execute(stmt)
                donation = res.scalar_one_or_none()

                if donation:
                    donation.status = "completed"
                    donation.completed_at = utc_now()
                    if payment_intent_id:
                        donation.stripe_payment_intent_id = str(payment_intent_id)
                    await session.commit()
                    logger.info(
                        "Donation marked as completed: id={} session_id={}",
                        donation.id,
                        session_id,
                    )
                else:
                    logger.warning(
                        "Donation not found for session_id={} tenant={}",
                        session_id,
                        tenantSlug,
                    )

    return {"received": True}


@router.get(
    "/admin/donations",
    response_model=DonationAdminListResponse,
    summary="Admin list of all donations with full audit information",
)
async def list_admin_donations(
    tenantSlug: str,
    current_user: PortalUser = Depends(require_curator),
    session: AsyncSession = Depends(get_db),
) -> dict[str, object]:
    """Curator and admin only endpoint listing all donation records from the database."""
    async with public_tenant_scope(tenantSlug, session) as tenant:
        # BE-SEC-056: token-tenant moet overeenkomen met de pad-tenant, zoals
        # curatie.py/edu.py/settings.py al deden. Zonder deze check leest een
        # curator van tenant A met zijn eigen JWT donor-PII van tenant B.
        if current_user.tenant_id != tenant.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User does not belong to this tenant",
            )

        stmt = (
            select(FoundationDonation)
            .where(FoundationDonation.tenant_id == tenant.id)
            .order_by(FoundationDonation.created_at.desc())
        )
        res = await session.execute(stmt)
        donations = res.scalars().all()

        items = [
            {
                "id": d.id,
                "amount_cents": d.amount_cents,
                "frequency": d.frequency,
                "donor_email": d.email,
                "donor_name": d.donor_name,
                "is_anonymous": d.is_anonymous,
                "monument_id": d.adopted_content_id,
                "message": d.message,
                "status": d.status,
                "stripe_session_id": d.stripe_session_id,
                "created_at": d.created_at.isoformat() if d.created_at else "",
            }
            for d in donations
        ]

        return {
            "total": len(items),
            "items": items,
        }
