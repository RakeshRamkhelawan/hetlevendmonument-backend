"""Foundation Portal newsletter endpoints."""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from urllib.parse import quote_plus

from fastapi import APIRouter, Body, Depends, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.v1.foundation.dependencies import (
    AuditService,
    brevo_email_service,
    get_db,
    public_tenant_scope,
    require_portal_newsletter_rate_limit,
)
from src.core.api.v1.foundation.schemas import (
    NewsletterConfirmRequest,
    NewsletterResponse,
    NewsletterSubscribeRequest,
    NewsletterUnsubscribeRequest,
)
from src.core.connectors.brevo import mask_email
from src.core.models.foundation_content import NewsletterStatus, NewsletterSubscription
from src.core.security.hcaptcha import require_hcaptcha
from src.core.shared.config import get_settings
from src.core.shared.datetime_utils import utc_now
from src.core.utils.best_effort import best_effort

router = APIRouter(tags=["foundation-newsletter"])


def _hash_token(token: str) -> str:
    """Hash a raw token with SHA-256."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@router.post(
    "/newsletter/subscribe",
    response_model=NewsletterResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Subscribe to newsletter (initiate double opt-in)",
)
async def subscribe_newsletter(
    tenantSlug: str,
    request: Request,
    data: NewsletterSubscribeRequest = Body(...),
    session: AsyncSession = Depends(get_db),
    _check: None = Depends(require_portal_newsletter_rate_limit),
) -> dict[str, str]:
    """Subscribe to the foundation portal newsletter (initiates double opt-in).

    - Public endpoint (no auth required)
    - Stores consent metadata (IP and User-Agent)
    - Sets initial status to PENDING_OPT_IN
    - Generates 32-byte confirm token (hashed in DB)
    - Sends double opt-in confirmation email with secure confirmation link
    - Returns generic message (no email enumeration)
    - Rate limit: 3 per hour per IP
    """
    client_ip = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    if user_agent and len(user_agent) > 500:
        user_agent = user_agent[:500]

    await require_hcaptcha(data.hcaptcha_token, remote_ip=client_ip)
    async with public_tenant_scope(tenantSlug, session) as tenant:
        # Check if subscription already exists
        stmt = select(NewsletterSubscription).where(
            NewsletterSubscription.tenant_id == tenant.id,
            NewsletterSubscription.email == data.email,
        )
        result = await session.execute(stmt)
        existing: NewsletterSubscription | None = result.scalar_one_or_none()

        raw_confirm_token = secrets.token_urlsafe(32)
        confirm_hash = _hash_token(raw_confirm_token)
        raw_unsub_token = secrets.token_urlsafe(32)
        unsub_hash = _hash_token(raw_unsub_token)

        if existing is not None:
            if existing.status == NewsletterStatus.SUBSCRIBED:
                # Already confirmed and active; return generic success (no enumeration)
                return {"message": "Subscription request received."}
            # Re-subscribe / update pending verification with fresh tokens
            existing.status = NewsletterStatus.PENDING_OPT_IN
            existing.confirm_token_hash = confirm_hash
            existing.unsubscribe_token_hash = unsub_hash
            existing.consent_ip = client_ip
            existing.consent_user_agent = user_agent
            existing.confirmed_at = None
            await session.flush()
        else:
            # Create new subscription with status PENDING_OPT_IN
            subscription = NewsletterSubscription(
                tenant_id=tenant.id,
                email=data.email,
                confirm_token_hash=confirm_hash,
                unsubscribe_token_hash=unsub_hash,
                status=NewsletterStatus.PENDING_OPT_IN,
                consent_ip=client_ip,
                consent_user_agent=user_agent,
            )
            session.add(subscription)
            await session.flush()

        # Send double opt-in verification email via brevo_email_service (best_effort)
        settings = get_settings()
        base_url = settings.foundation_portal_base_url.rstrip("/")
        confirm_url = (
            f"{base_url}/{tenantSlug}/foundation/newsletter/confirm"
            f"?email={quote_plus(data.email)}&token={raw_confirm_token}"
        )
        async with best_effort("newsletter_optin_email"):
            await brevo_email_service.send_newsletter_optin_request(
                to_email=data.email,
                confirm_url=confirm_url,
                tenant_name=getattr(tenant, "name", None),
            )

        # Audit log opt-in request
        masked = mask_email(data.email)
        async with best_effort("audit_newsletter_optin", db_session=session):
            await AuditService.log_event(
                db=session,
                event_type="newsletter_optin_requested",
                severity="low",
                source_ip=client_ip or "unknown",
                endpoint=f"/{tenantSlug}/foundation/newsletter/subscribe",
                description=f"Newsletter opt-in requested for {masked}",
                user_id=None,
                tenant_id=tenant.id,
                action="newsletter_optin_requested",
                resource=f"newsletter_subscription:{masked}",
            )

        return {"message": "Subscription request received."}


@router.post(
    "/newsletter/confirm",
    response_model=NewsletterResponse,
    summary="Confirm newsletter subscription (double opt-in)",
)
async def confirm_newsletter(
    tenantSlug: str,
    request: Request,
    data: NewsletterConfirmRequest = Body(...),
    session: AsyncSession = Depends(get_db),
    _check: None = Depends(require_portal_newsletter_rate_limit),
) -> dict[str, str]:
    """Confirm a newsletter subscription via one-time double opt-in token.

    - Validates confirm_token_hash against database record
    - Enforces 7-day token TTL
    - Sets status to SUBSCRIBED and confirmed_at timestamp
    - Clears confirm_token_hash (replay attack prevention)
    - Generates fresh unsubscribe token and sends welcome email with unsubscribe link
    - Emits structured audit event (art. 7 lid 1 AVG compliance)
    - Returns generic message (no email enumeration)
    """
    client_ip = request.client.host if request.client else None
    token_hash = _hash_token(data.token)

    async with public_tenant_scope(tenantSlug, session) as tenant:
        stmt = select(NewsletterSubscription).where(
            NewsletterSubscription.tenant_id == tenant.id,
            NewsletterSubscription.email == data.email,
            NewsletterSubscription.confirm_token_hash == token_hash,
        )
        result = await session.execute(stmt)
        subscription: NewsletterSubscription | None = result.scalar_one_or_none()

        if subscription is None:
            # Generic response to prevent enumeration
            return {"message": "Subscription confirmation processed."}

        # Enforce 7-day TTL
        now = utc_now()
        record_time = subscription.updated_at or subscription.created_at
        if record_time and (now - record_time) > timedelta(days=7):
            return {"message": "Subscription confirmation processed."}

        # Single-use: clear confirm_token_hash to prevent replay attacks
        subscription.confirm_token_hash = None
        subscription.status = NewsletterStatus.SUBSCRIBED
        subscription.confirmed_at = now

        # Generate fresh unsubscribe token for welcome email
        raw_unsub_token = secrets.token_urlsafe(32)
        subscription.unsubscribe_token_hash = _hash_token(raw_unsub_token)
        await session.flush()

        # Send welcome email with unsubscribe link (best_effort)
        settings = get_settings()
        base_url = settings.foundation_portal_base_url.rstrip("/")
        unsub_url = (
            f"{base_url}/{tenantSlug}/foundation/newsletter/unsubscribe"
            f"?email={quote_plus(subscription.email)}&token={raw_unsub_token}"
        )
        async with best_effort("newsletter_welcome_email"):
            await brevo_email_service.send_newsletter_confirmation(
                to_email=subscription.email,
                unsubscribe_url=unsub_url,
                tenant_name=getattr(tenant, "name", None),
            )

        # Audit log confirmation
        masked = mask_email(data.email)
        async with best_effort("audit_newsletter_confirmed", db_session=session):
            await AuditService.log_event(
                db=session,
                event_type="newsletter_confirmed",
                severity="low",
                source_ip=client_ip or "unknown",
                endpoint=f"/{tenantSlug}/foundation/newsletter/confirm",
                description=f"Newsletter subscription confirmed for {masked}",
                user_id=None,
                tenant_id=tenant.id,
                action="newsletter_confirmed",
                resource=f"newsletter_subscription:{masked}",
            )

        return {"message": "Subscription confirmed."}


@router.get(
    "/newsletter/confirm",
    summary="Redirect email link to frontend confirmation page",
    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
)
async def redirect_newsletter_confirm(
    tenantSlug: str,
    email: str,
    token: str,
) -> RedirectResponse:
    """Redirect incoming email link to frontend portal page.

    Does not mutate subscription state on GET to protect against automated
    email security scanners / bot clicks.
    """
    settings = get_settings()
    portal_url = settings.foundation_portal_base_url.rstrip("/")
    target_url = (
        f"{portal_url}/nieuwsbrief?confirm={quote_plus(token)}"
        f"&email={quote_plus(email)}&tenant={quote_plus(tenantSlug)}"
    )
    return RedirectResponse(url=target_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get(
    "/newsletter/unsubscribe",
    summary="Redirect email link to frontend unsubscribe page",
    status_code=status.HTTP_307_TEMPORARY_REDIRECT,
)
async def redirect_newsletter_unsubscribe(
    tenantSlug: str,
    email: str,
    token: str,
) -> RedirectResponse:
    """Redirect incoming unsubscribe link to frontend portal page.

    Does not mutate subscription state on GET to protect against automated
    email security scanners / bot clicks.
    """
    settings = get_settings()
    portal_url = settings.foundation_portal_base_url.rstrip("/")
    target_url = (
        f"{portal_url}/nieuwsbrief?unsubscribe=true"
        f"&email={quote_plus(email)}&token={quote_plus(token)}&tenant={quote_plus(tenantSlug)}"
    )
    return RedirectResponse(url=target_url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.post(
    "/newsletter/unsubscribe",
    response_model=NewsletterResponse,
    summary="Unsubscribe from newsletter",
)
async def unsubscribe_newsletter(
    tenantSlug: str,
    request: Request,
    data: NewsletterUnsubscribeRequest = Body(...),
    session: AsyncSession = Depends(get_db),
    _check: None = Depends(require_portal_newsletter_rate_limit),
) -> dict[str, str]:
    """Unsubscribe from the foundation portal newsletter.

    - Public endpoint (no auth required)
    - Verifies unsubscribe token before updating status
    - Records unsubscribed_at timestamp
    - Emits audit log
    - Returns generic message (no enumeration)
    - Rate limit: 3 per hour per IP
    """
    client_ip = request.client.host if request.client else None
    async with public_tenant_scope(tenantSlug, session) as tenant:
        stmt = select(NewsletterSubscription).where(
            NewsletterSubscription.tenant_id == tenant.id,
            NewsletterSubscription.email == data.email,
            NewsletterSubscription.unsubscribe_token_hash == _hash_token(data.token),
        )
        result = await session.execute(stmt)
        subscription: NewsletterSubscription | None = result.scalar_one_or_none()

        if subscription is None:
            # Return generic message even if not found (no enumeration)
            return {"message": "Unsubscribe request received."}

        subscription.status = NewsletterStatus.UNSUBSCRIBED
        subscription.unsubscribed_at = utc_now()
        await session.flush()

        masked = mask_email(data.email)
        async with best_effort("audit_newsletter_unsubscribed", db_session=session):
            await AuditService.log_event(
                db=session,
                event_type="newsletter_unsubscribed",
                severity="low",
                source_ip=client_ip or "unknown",
                endpoint=f"/{tenantSlug}/foundation/newsletter/unsubscribe",
                description=f"Newsletter subscription unsubscribed for {masked}",
                user_id=None,
                tenant_id=tenant.id,
                action="newsletter_unsubscribed",
                resource=f"newsletter_subscription:{masked}",
            )

        return {"message": "Unsubscribe request received."}

