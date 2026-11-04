"""Foundation Portal webhook endpoints for Brevo event handling (BE-EP-049 / ADR-029 P1-5).

Handles incoming Brevo transactional & marketing webhooks:
- hard_bounce, soft_bounce, blocked, spam -> updates NewsletterSubscription status to BOUNCED
- unsubscribe, unsubscribed -> updates NewsletterSubscription status to UNSUBSCRIBED
- delivered, opened, click -> logs audit event
"""

from __future__ import annotations

import secrets
from typing import Union
from fastapi import APIRouter, Body, Depends, Header, HTTPException, Query, Request, status
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.v1.foundation.dependencies import (
    AuditService,
    get_db,
    public_tenant_scope,
)
from src.core.connectors.brevo import mask_email
from src.core.models.foundation_content import NewsletterStatus, NewsletterSubscription
from src.core.shared.config import get_settings
from src.core.shared.datetime_utils import utc_now
from src.core.utils.best_effort import best_effort

router = APIRouter(prefix="/webhooks", tags=["foundation-webhooks"])


class BrevoWebhookPayload(BaseModel):
    """Model representing a single Brevo webhook event."""

    event: str = Field(..., description="Event type, e.g. delivered, hard_bounce, spam")
    email: str = Field(..., description="Target email address")
    id: int | str | None = Field(default=None, description="Brevo message or webhook ID")
    date: str | None = Field(default=None, description="Event date string")
    ts_event: int | None = Field(default=None, description="Epoch timestamp of event")
    subject: str | None = Field(default=None, description="Subject of email")
    tag: str | None = Field(default=None, description="Primary tag sent with email")
    tags: list[str] | None = Field(default=None, description="All tags sent with email")
    reason: str | None = Field(default=None, description="Bounce reason or failure description")

    model_config = ConfigDict(extra="allow")


class WebhookResponse(BaseModel):
    """Response returned after webhook processing."""

    status: str
    processed: int
    bounces_recorded: int


def _verify_webhook_secret(
    secret_header: str | None = Header(None, alias="X-Webhook-Secret"),
    brevo_header: str | None = Header(None, alias="X-Brevo-Secret"),
    token_query: str | None = Query(None, alias="token"),
) -> None:
    """Verify Brevo webhook authentication secret (fail-closed).

    BE-SEC-055: een ontbrekend of leeg brevo_webhook_secret geeft 503 --
    nooit stilletjes toestaan. Zonder shared secret kan iedereen bounce- en
    unsubscribe-events vervalsen voor willekeurige e-mailadressen.
    """
    settings = get_settings()
    configured = settings.brevo_webhook_secret
    if not configured or not configured.strip():
        logger.error(
            "brevo_webhook_secret is not configured; refusing webhook (fail-closed)"
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Webhook endpoint is not configured.",
        )

    provided = secret_header or brevo_header or token_query
    if not provided or not secrets.compare_digest(provided, configured):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing webhook secret",
        )


@router.post(
    "/brevo",
    response_model=WebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="Handle incoming Brevo email webhook events",
)
async def handle_brevo_webhook(
    tenantSlug: str,
    request: Request,
    payload: Union[BrevoWebhookPayload, list[BrevoWebhookPayload]] = Body(...),
    session: AsyncSession = Depends(get_db),
    _auth: None = Depends(_verify_webhook_secret),
) -> WebhookResponse:
    """Receive Brevo transactional or marketing webhook events.

    - Verifies shared secret against settings.brevo_webhook_secret (fail-closed:
      503 when not configured, 401 when missing/invalid)
    - Handles single events or batched event lists
    - Updates NewsletterSubscription.status to BOUNCED on hard_bounce / spam / blocked
    - Updates NewsletterSubscription.status to UNSUBSCRIBED on unsubscribe events
    - Records audit log for bounce and security events
    """
    events: list[BrevoWebhookPayload] = payload if isinstance(payload, list) else [payload]
    processed_count = len(events)
    bounces_recorded = 0

    bounce_event_types = {"hard_bounce", "soft_bounce", "blocked", "spam", "complaint", "invalid_email"}
    unsubscribe_event_types = {"unsubscribe", "unsubscribed"}

    async with public_tenant_scope(tenantSlug, session) as tenant:
        for ev in events:
            ev_type = ev.event.lower().strip()
            ev_email = ev.email.lower().strip()
            masked = mask_email(ev_email)

            logger.info(
                "brevo_webhook_event: tenant={} event={} email={} reason={}",
                tenantSlug,
                ev_type,
                masked,
                ev.reason or "none",
            )

            if ev_type in bounce_event_types:
                # Find matching newsletter subscription
                stmt = select(NewsletterSubscription).where(
                    NewsletterSubscription.tenant_id == tenant.id,
                    NewsletterSubscription.email == ev_email,
                )
                res = await session.execute(stmt)
                subscription = res.scalar_one_or_none()

                if subscription is not None and subscription.status != NewsletterStatus.BOUNCED:
                    subscription.status = NewsletterStatus.BOUNCED
                    await session.flush()
                    bounces_recorded += 1

                # Audit log bounce
                async with best_effort("audit_brevo_bounce", db_session=session):
                    await AuditService.log_event(
                        db=session,
                        event_type="newsletter_bounce",
                        severity="medium",
                        source_ip=request.client.host if request.client else "unknown",
                        endpoint=f"/{tenantSlug}/foundation/webhooks/brevo",
                        description=f"Brevo email bounce ({ev_type}) for {masked}",
                        user_id=None,
                        tenant_id=tenant.id,
                        action=f"brevo_bounce_{ev_type}",
                        resource=f"newsletter_subscription:{ev_email}",
                        metadata={
                            "event": ev_type,
                            "email": masked,
                            "reason": ev.reason or "none",
                            "message_id": str(ev.id or ""),
                        },
                    )

            elif ev_type in unsubscribe_event_types:
                stmt = select(NewsletterSubscription).where(
                    NewsletterSubscription.tenant_id == tenant.id,
                    NewsletterSubscription.email == ev_email,
                )
                res = await session.execute(stmt)
                subscription = res.scalar_one_or_none()

                if subscription is not None and subscription.status != NewsletterStatus.UNSUBSCRIBED:
                    subscription.status = NewsletterStatus.UNSUBSCRIBED
                    subscription.unsubscribed_at = utc_now()
                    await session.flush()

                async with best_effort("audit_brevo_unsubscribe", db_session=session):
                    await AuditService.log_event(
                        db=session,
                        event_type="newsletter_unsubscribed",
                        severity="low",
                        source_ip=request.client.host if request.client else "unknown",
                        endpoint=f"/{tenantSlug}/foundation/webhooks/brevo",
                        description=f"Brevo unsubscribe event for {masked}",
                        user_id=None,
                        tenant_id=tenant.id,
                        action="brevo_unsubscribe",
                        resource=f"newsletter_subscription:{ev_email}",
                        metadata={"event": ev_type, "email": masked},
                    )

    return WebhookResponse(
        status="ok",
        processed=processed_count,
        bounces_recorded=bounces_recorded,
    )
