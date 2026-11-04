"""Integration tests for Foundation Portal rate limiters (429 verification).

Rate-limit state (real Redis + InMemory fallback) is reset before/after every
test by the autouse ``_clear_rate_limits`` fixture in conftest.py -- that
fixture originally only covered this file, and is now shared by the whole
``tests/integration/api/v1/foundation/`` tree (2026-09-03, PR #163) since the
same Redis-state carryover broke test_auth.py and test_newsletter.py too.
"""

from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient


def _url(tenant_slug: str, path: str = "") -> str:
    return f"/{tenant_slug}/foundation{path}"


@pytest.mark.asyncio
@pytest.mark.integration
class TestMagicLinkRateLimits:
    """Rate limit tests for magic-link endpoints."""

    async def test_magic_link_ip_rate_limit(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """IP-based rate limit: 5 per minute. 6th request returns 429."""
        # Use different emails so the email-keyed limit (3/hr) is not hit first
        for i in range(5):
            payload = {"email": f"user{i}@example.com"}
            response = await integration_client.post(
                _url("default", "/auth/magic-link"),
                json=payload,
            )
            assert response.status_code == status.HTTP_202_ACCEPTED, f"Request {i + 1} should succeed"

        # 6th request from same IP should be rate limited
        payload = {"email": "user5@example.com"}
        response = await integration_client.post(
            _url("default", "/auth/magic-link"),
            json=payload,
        )
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert response.headers["Retry-After"] is not None
        assert response.headers["X-RateLimit-Limit"] is not None

    async def test_magic_link_email_rate_limit(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """Email-based rate limit: 3 per hour. 4th request with same email returns 429."""
        email = "same@example.com"
        for i in range(3):
            payload = {"email": email}
            response = await integration_client.post(
                _url("default", "/auth/magic-link"),
                json=payload,
            )
            assert response.status_code == status.HTTP_202_ACCEPTED, f"Request {i + 1} should succeed"

        # 4th request with same email should be rate limited
        payload = {"email": email}
        response = await integration_client.post(
            _url("default", "/auth/magic-link"),
            json=payload,
        )
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert response.headers["Retry-After"] is not None
        assert response.headers["X-RateLimit-Limit"] is not None


@pytest.mark.asyncio
@pytest.mark.integration
class TestTakedownRateLimit:
    """Rate limit tests for takedown endpoint."""

    async def test_takedown_rate_limit(
        self,
        integration_client: AsyncClient,
        portal_visitor_token: str,
        approved_public_content: object,
    ) -> None:
        """Takedown rate limit: 5 per hour. 6th request returns 429."""
        payload = {
            "content_id": approved_public_content.id,
            "reason": "Copyright violation",
            "contact_email": "claimant@example.com",
        }

        for i in range(5):
            response = await integration_client.post(
                _url("default", "/takedown"),
                json=payload,
                headers={"Authorization": f"Bearer {portal_visitor_token}"},
            )
            assert response.status_code == status.HTTP_201_CREATED, f"Request {i + 1} should succeed"

        # 6th request should be rate limited
        response = await integration_client.post(
            _url("default", "/takedown"),
            json=payload,
            headers={"Authorization": f"Bearer {portal_visitor_token}"},
        )
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert response.headers["Retry-After"] is not None
        assert response.headers["X-RateLimit-Limit"] is not None


@pytest.mark.asyncio
@pytest.mark.integration
class TestNewsletterRateLimit:
    """Rate limit tests for newsletter subscribe endpoint."""

    async def test_newsletter_subscribe_rate_limit(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """Newsletter subscribe rate limit: 3 per hour. 4th request returns 429."""
        for i in range(3):
            payload = {"email": f"subscriber{i}@example.com"}
            response = await integration_client.post(
                _url("default", "/newsletter/subscribe"),
                json=payload,
            )
            assert response.status_code == status.HTTP_201_CREATED, f"Request {i + 1} should succeed"

        # 4th request should be rate limited
        payload = {"email": "subscriber3@example.com"}
        response = await integration_client.post(
            _url("default", "/newsletter/subscribe"),
            json=payload,
        )
        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert response.headers["Retry-After"] is not None
        assert response.headers["X-RateLimit-Limit"] is not None
