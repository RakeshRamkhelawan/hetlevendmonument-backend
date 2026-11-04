"""Integration tests for Brevo webhook handling and magic-link redirect (BE-EP-049 / ADR-029 P1-5)."""

from __future__ import annotations

import secrets
from datetime import datetime, timezone
import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.foundation_content import (
    NewsletterStatus,
    NewsletterSubscription,
    PortalUser,
)
from src.core.shared.config import get_settings


def _url(tenant_slug: str, path: str = "") -> str:
    return f"/{tenant_slug}/foundation{path}"


@pytest.mark.asyncio
@pytest.mark.integration
class TestBrevoWebhook:
    """Integration tests for Brevo webhook processing."""

    @pytest.fixture(autouse=True)
    def _configure_webhook_secret(self):
        """BE-SEC-055: webhook is fail-closed; tests configureren een secret."""
        settings = get_settings()
        original_secret = settings.brevo_webhook_secret
        settings.brevo_webhook_secret = "test-brevo-webhook-secret"
        yield
        settings.brevo_webhook_secret = original_secret

    async def test_webhook_hard_bounce_updates_newsletter_status(
        self,
        integration_client: AsyncClient,
        postgres_session: AsyncSession,
        portal_visitor_user: PortalUser,
    ) -> None:
        """A hard_bounce event marks matching subscription as BOUNCED."""
        bounce_email = f"bounce_{secrets.token_hex(4)}@example.org"

        # Create active subscription
        subscription = NewsletterSubscription(
            tenant_id=portal_visitor_user.tenant_id,
            email=bounce_email,
            status=NewsletterStatus.SUBSCRIBED,
            unsubscribe_token_hash=secrets.token_hex(32),
            confirmed_at=datetime.now(timezone.utc),
        )
        postgres_session.add(subscription)
        await postgres_session.flush()

        # Send Brevo hard_bounce webhook
        payload = {
            "event": "hard_bounce",
            "email": bounce_email,
            "id": 123456,
            "date": "2026-09-14 12:00:00",
            "reason": "550 5.1.1 User unknown",
            "tag": "portal-newsletter",
        }

        response = await integration_client.post(
            _url("default", "/webhooks/brevo"),
            json=payload,
            headers={"X-Webhook-Secret": "test-brevo-webhook-secret"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "ok"
        assert data["processed"] == 1
        assert data["bounces_recorded"] == 1

        # Verify DB status updated
        await postgres_session.refresh(subscription)
        assert subscription.status == NewsletterStatus.BOUNCED

    async def test_webhook_unsubscribe_event(
        self,
        integration_client: AsyncClient,
        postgres_session: AsyncSession,
        portal_visitor_user: PortalUser,
    ) -> None:
        """An unsubscribe event marks matching subscription as UNSUBSCRIBED."""
        unsub_email = f"unsub_{secrets.token_hex(4)}@example.org"

        subscription = NewsletterSubscription(
            tenant_id=portal_visitor_user.tenant_id,
            email=unsub_email,
            status=NewsletterStatus.SUBSCRIBED,
            unsubscribe_token_hash=secrets.token_hex(32),
            confirmed_at=datetime.now(timezone.utc),
        )
        postgres_session.add(subscription)
        await postgres_session.flush()

        payload = {
            "event": "unsubscribe",
            "email": unsub_email,
        }

        response = await integration_client.post(
            _url("default", "/webhooks/brevo"),
            json=payload,
            headers={"X-Webhook-Secret": "test-brevo-webhook-secret"},
        )

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "ok"
        assert data["processed"] == 1

        await postgres_session.refresh(subscription)
        assert subscription.status == NewsletterStatus.UNSUBSCRIBED
        assert subscription.unsubscribed_at is not None

    async def test_webhook_secret_protection(
        self,
        integration_client: AsyncClient,
        portal_visitor_user: PortalUser,
    ) -> None:
        """When brevo_webhook_secret is configured, unauthorized requests return 401."""
        settings = get_settings()
        original_secret = settings.brevo_webhook_secret
        try:
            settings.brevo_webhook_secret = "super-secret-brevo-key-123"

            payload = {"event": "delivered", "email": "test@example.org"}

            # Request without secret header -> 401
            res_unauth = await integration_client.post(
                _url("default", "/webhooks/brevo"),
                json=payload,
            )
            assert res_unauth.status_code == status.HTTP_401_UNAUTHORIZED

            # Request with incorrect secret header -> 401
            res_bad = await integration_client.post(
                _url("default", "/webhooks/brevo"),
                json=payload,
                headers={"X-Webhook-Secret": "wrong-secret"},
            )
            assert res_bad.status_code == status.HTTP_401_UNAUTHORIZED

            # Request with correct secret header -> 200
            res_ok = await integration_client.post(
                _url("default", "/webhooks/brevo"),
                json=payload,
                headers={"X-Webhook-Secret": "super-secret-brevo-key-123"},
            )
            assert res_ok.status_code == status.HTTP_200_OK

        finally:
            settings.brevo_webhook_secret = original_secret


@pytest.mark.asyncio
@pytest.mark.integration
class TestMagicLinkRedirect:
    """Integration test for GET /auth/magic-link/verify browser fallback."""

    async def test_magic_link_browser_get_redirects_to_frontend(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """Browser clicking magic link sends GET and gets 307 redirected to frontend."""
        raw_token = secrets.token_urlsafe(32)
        response = await integration_client.get(
            _url("default", f"/auth/magic-link/verify?token={raw_token}"),
            follow_redirects=False,
        )

        assert response.status_code == status.HTTP_307_TEMPORARY_REDIRECT
        location = response.headers.get("location", "")
        assert "/inloggen" in location
        assert f"token={raw_token}" in location
        assert "tenant=default" in location
