"""Integration tests for Foundation Portal newsletter endpoints (ADR-029 BE-EP-050)."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import status
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.foundation_content import NewsletterStatus, NewsletterSubscription


def _url(tenant_slug: str, path: str = "") -> str:
    return f"/{tenant_slug}/foundation{path}"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ============================================================================
# Subscribe endpoint (POST /{tenantSlug}/foundation/newsletter/subscribe)
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestNewsletterSubscribe:
    """Tests for the newsletter subscribe endpoint."""

    async def test_subscribe_success(
        self,
        integration_client: AsyncClient,
        postgres_session: AsyncSession,
    ) -> None:
        """Public user can initiate double opt-in subscription to newsletter."""
        payload = {"email": "subscriber@example.com"}
        response = await integration_client.post(
            _url("default", "/newsletter/subscribe"),
            json=payload,
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert "received" in data["message"]

        # Verify in DB: initial status is PENDING_OPT_IN with tokens and consent metadata
        stmt = select(NewsletterSubscription).where(
            NewsletterSubscription.email == "subscriber@example.com",
        )
        result = await postgres_session.execute(stmt)
        sub = result.scalar_one_or_none()
        assert sub is not None
        assert sub.status == NewsletterStatus.PENDING_OPT_IN
        assert sub.confirm_token_hash is not None
        assert sub.unsubscribe_token_hash is not None
        assert sub.confirmed_at is None

    async def test_subscribe_already_subscribed(
        self,
        integration_client: AsyncClient,
        postgres_session: AsyncSession,
    ) -> None:
        """Subscribing again when already confirmed returns generic success message."""
        # First subscribe
        payload = {"email": "dup@example.com"}
        response = await integration_client.post(
            _url("default", "/newsletter/subscribe"),
            json=payload,
        )
        assert response.status_code == status.HTTP_201_CREATED

        # Mark as SUBSCRIBED
        stmt = select(NewsletterSubscription).where(
            NewsletterSubscription.email == "dup@example.com",
        )
        result = await postgres_session.execute(stmt)
        sub = result.scalar_one()
        sub.status = NewsletterStatus.SUBSCRIBED
        await postgres_session.flush()

        # Second subscribe
        response = await integration_client.post(
            _url("default", "/newsletter/subscribe"),
            json=payload,
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert "received" in data["message"]

    async def test_subscribe_no_auth_required(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """No authentication required for subscribe."""
        payload = {"email": "public@example.com"}
        response = await integration_client.post(
            _url("default", "/newsletter/subscribe"),
            json=payload,
        )
        assert response.status_code == status.HTTP_201_CREATED

    async def test_subscribe_invalid_tenant(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """Invalid tenant slug returns 404."""
        payload = {"email": "test@example.com"}
        response = await integration_client.post(
            _url("nonexistent", "/newsletter/subscribe"),
            json=payload,
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_subscribe_resubscribe_regenerates_token(
        self,
        integration_client: AsyncClient,
        postgres_session: AsyncSession,
    ) -> None:
        """Re-subscribing after unsubscribe generates a fresh token."""
        email = "resub@example.com"
        # Subscribe
        response = await integration_client.post(
            _url("default", "/newsletter/subscribe"),
            json={"email": email},
        )
        assert response.status_code == status.HTTP_201_CREATED

        # Get original token hash
        stmt = select(NewsletterSubscription).where(
            NewsletterSubscription.email == email,
        )
        result = await postgres_session.execute(stmt)
        sub = result.scalar_one()
        original_hash = sub.unsubscribe_token_hash

        # Unsubscribe with token
        raw_token = secrets.token_urlsafe(32)
        sub.unsubscribe_token_hash = _hash(raw_token)
        sub.status = NewsletterStatus.SUBSCRIBED
        await postgres_session.flush()

        response = await integration_client.post(
            _url("default", "/newsletter/unsubscribe"),
            json={"email": email, "token": raw_token},
        )
        assert response.status_code == status.HTTP_200_OK

        # Re-subscribe
        response = await integration_client.post(
            _url("default", "/newsletter/subscribe"),
            json={"email": email},
        )
        assert response.status_code == status.HTTP_201_CREATED

        # Verify token was regenerated
        await postgres_session.refresh(sub)
        assert sub.unsubscribe_token_hash != original_hash
        assert sub.status == NewsletterStatus.PENDING_OPT_IN


# ============================================================================
# Confirm endpoint (POST /{tenantSlug}/foundation/newsletter/confirm)
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestNewsletterConfirm:
    """Tests for the double opt-in confirmation endpoint."""

    async def test_confirm_success(
        self,
        integration_client: AsyncClient,
        postgres_session: AsyncSession,
    ) -> None:
        """Valid confirm token confirms subscription and updates status to SUBSCRIBED."""
        email = "confirm-me@example.com"
        # 1. Subscribe
        await integration_client.post(
            _url("default", "/newsletter/subscribe"),
            json={"email": email},
        )

        # 2. Get record and simulate known confirm token
        stmt = select(NewsletterSubscription).where(NewsletterSubscription.email == email)
        result = await postgres_session.execute(stmt)
        sub = result.scalar_one()
        raw_token = secrets.token_urlsafe(32)
        sub.confirm_token_hash = _hash(raw_token)
        await postgres_session.flush()

        # 3. Confirm
        response = await integration_client.post(
            _url("default", "/newsletter/confirm"),
            json={"email": email, "token": raw_token},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "confirmed" in data["message"].lower()

        # 4. Verify DB state: SUBSCRIBED, confirmed_at set, confirm_token_hash cleared
        await postgres_session.refresh(sub)
        assert sub.status == NewsletterStatus.SUBSCRIBED
        assert sub.confirmed_at is not None
        assert sub.confirm_token_hash is None

    async def test_confirm_replay_attack_rejected(
        self,
        integration_client: AsyncClient,
        postgres_session: AsyncSession,
    ) -> None:
        """Using a confirm token twice fails on second attempt (replay attack protection)."""
        email = "replay@example.com"
        await integration_client.post(
            _url("default", "/newsletter/subscribe"),
            json={"email": email},
        )

        stmt = select(NewsletterSubscription).where(NewsletterSubscription.email == email)
        result = await postgres_session.execute(stmt)
        sub = result.scalar_one()
        raw_token = secrets.token_urlsafe(32)
        sub.confirm_token_hash = _hash(raw_token)
        await postgres_session.flush()

        # First confirm -> OK
        res1 = await integration_client.post(
            _url("default", "/newsletter/confirm"),
            json={"email": email, "token": raw_token},
        )
        assert res1.status_code == status.HTTP_200_OK
        assert "confirmed" in res1.json()["message"].lower()

        # Second confirm with same token -> Generic response (processed), not confirmed again
        res2 = await integration_client.post(
            _url("default", "/newsletter/confirm"),
            json={"email": email, "token": raw_token},
        )
        assert res2.status_code == status.HTTP_200_OK
        assert "processed" in res2.json()["message"].lower()

    async def test_confirm_invalid_token_returns_generic(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """Invalid confirm token returns generic response without enumeration."""
        response = await integration_client.post(
            _url("default", "/newsletter/confirm"),
            json={"email": "nonexistent@example.com", "token": "invalid-token-12345"},
        )
        assert response.status_code == status.HTTP_200_OK
        assert "processed" in response.json()["message"].lower()

    async def test_confirm_expired_token(
        self,
        integration_client: AsyncClient,
        postgres_session: AsyncSession,
    ) -> None:
        """Confirm token older than 7 days is rejected."""
        email = "expired@example.com"
        await integration_client.post(
            _url("default", "/newsletter/subscribe"),
            json={"email": email},
        )

        stmt = select(NewsletterSubscription).where(NewsletterSubscription.email == email)
        result = await postgres_session.execute(stmt)
        sub = result.scalar_one()
        raw_token = secrets.token_urlsafe(32)
        sub.confirm_token_hash = _hash(raw_token)
        sub.updated_at = datetime.now(timezone.utc) - timedelta(days=8)
        await postgres_session.flush()

        response = await integration_client.post(
            _url("default", "/newsletter/confirm"),
            json={"email": email, "token": raw_token},
        )
        assert response.status_code == status.HTTP_200_OK
        assert "processed" in response.json()["message"].lower()

        # Record is still PENDING_OPT_IN, not SUBSCRIBED
        await postgres_session.refresh(sub)
        assert sub.status == NewsletterStatus.PENDING_OPT_IN


# ============================================================================
# Redirect endpoints (GET /{tenantSlug}/foundation/newsletter/confirm & unsubscribe)
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestNewsletterRedirects:
    """Tests for email link GET redirect endpoints (bot/scanner protection)."""

    async def test_confirm_get_redirects_to_portal(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """GET /newsletter/confirm returns 307 redirect to frontend portal."""
        response = await integration_client.get(
            _url("default", "/newsletter/confirm?email=reader@example.com&token=tok123"),
            follow_redirects=False,
        )
        assert response.status_code == status.HTTP_307_TEMPORARY_REDIRECT
        loc = response.headers.get("location")
        assert loc is not None
        assert "/nieuwsbrief" in loc
        assert "confirm=tok123" in loc
        assert "email=reader%40example.com" in loc
        assert "tenant=default" in loc

    async def test_unsubscribe_get_redirects_to_portal(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """GET /newsletter/unsubscribe returns 307 redirect to frontend portal."""
        response = await integration_client.get(
            _url("default", "/newsletter/unsubscribe?email=reader@example.com&token=tok456"),
            follow_redirects=False,
        )
        assert response.status_code == status.HTTP_307_TEMPORARY_REDIRECT
        loc = response.headers.get("location")
        assert loc is not None
        assert "/nieuwsbrief" in loc
        assert "unsubscribe=true" in loc
        assert "email=reader%40example.com" in loc
        assert "token=tok456" in loc
        assert "tenant=default" in loc


# ============================================================================
# Unsubscribe endpoint (POST /{tenantSlug}/foundation/newsletter/unsubscribe)
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestNewsletterUnsubscribe:
    """Tests for the newsletter unsubscribe endpoint."""

    async def test_unsubscribe_success(
        self,
        integration_client: AsyncClient,
        postgres_session: AsyncSession,
    ) -> None:
        """Public user can unsubscribe from newsletter with valid token."""
        email = "unsub@example.com"
        # First subscribe
        subscribe_payload = {"email": email}
        await integration_client.post(
            _url("default", "/newsletter/subscribe"),
            json=subscribe_payload,
        )

        # Get token hash from DB and compute raw token for test
        raw_token = secrets.token_urlsafe(32)
        stmt = select(NewsletterSubscription).where(
            NewsletterSubscription.email == email,
        )
        result = await postgres_session.execute(stmt)
        sub = result.scalar_one()
        sub.unsubscribe_token_hash = _hash(raw_token)
        sub.status = NewsletterStatus.SUBSCRIBED
        await postgres_session.flush()

        # Then unsubscribe with token
        response = await integration_client.post(
            _url("default", "/newsletter/unsubscribe"),
            json={"email": email, "token": raw_token},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "received" in data["message"]

        # Verify in DB
        await postgres_session.refresh(sub)
        assert sub.status == NewsletterStatus.UNSUBSCRIBED
        assert sub.unsubscribed_at is not None

    async def test_unsubscribe_invalid_token_returns_generic(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """Unsubscribing with invalid token returns generic message (no enumeration)."""
        payload = {"email": "test@example.com", "token": "invalid-token"}
        response = await integration_client.post(
            _url("default", "/newsletter/unsubscribe"),
            json=payload,
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "received" in data["message"]

    async def test_unsubscribe_no_auth_required(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """No authentication required for unsubscribe."""
        payload = {"email": "public-unsub@example.com", "token": "some-token"}
        response = await integration_client.post(
            _url("default", "/newsletter/unsubscribe"),
            json=payload,
        )
        assert response.status_code == status.HTTP_200_OK

    async def test_unsubscribe_missing_token_returns_422(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """Unsubscribe without token returns 422."""
        payload = {"email": "test@example.com"}
        response = await integration_client.post(
            _url("default", "/newsletter/unsubscribe"),
            json=payload,
        )
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT

    async def test_unsubscribe_is_tenant_scoped(
        self,
        integration_client: AsyncClient,
        postgres_session: AsyncSession,
    ) -> None:
        """A subscription in one tenant is not touched by an unsubscribe call
        against a different tenant, even for the same email address."""
        email = "cross-tenant@example.com"

        # Subscribe in tenant "default" (tenant_id=1)
        response = await integration_client.post(
            _url("default", "/newsletter/subscribe"),
            json={"email": email},
        )
        assert response.status_code == status.HTTP_201_CREATED

        stmt = select(NewsletterSubscription).where(
            NewsletterSubscription.email == email,
            NewsletterSubscription.tenant_id == 1,
        )
        result = await postgres_session.execute(stmt)
        sub = result.scalar_one()
        sub.status = NewsletterStatus.SUBSCRIBED
        await postgres_session.flush()
        assert sub.status == NewsletterStatus.SUBSCRIBED

        # Unsubscribe the SAME email in tenant "other" (tenant_id=2, pre-seeded
        # secondary tenant -- see tests/integration/conftest.py), without a valid
        # token -- the subscription doesn't exist there, so this must return the
        # generic 200 (no enumeration), not touch tenant 1's row.
        response = await integration_client.post(
            _url("other", "/newsletter/unsubscribe"),
            json={"email": email, "token": "irrelevant-token"},
        )
        assert response.status_code == status.HTTP_200_OK

        # Tenant "default"'s subscription must still be SUBSCRIBED.
        await postgres_session.refresh(sub)
        assert sub.status == NewsletterStatus.SUBSCRIBED

