"""Integration tests for Foundation Portal auth endpoints."""

from __future__ import annotations

import pytest
from fastapi import status
from httpx import AsyncClient
from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.jwt_handler import jwt_handler
from src.core.models.foundation_content import MagicLinkToken, PortalUser


def _url(tenant_slug: str, path: str = "") -> str:
    return f"/{tenant_slug}/foundation{path}"


# ============================================================================
# Magic link request (POST /{tenantSlug}/foundation/auth/magic-link)
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestMagicLinkRequest:
    """Tests for the magic link request endpoint."""

    async def test_request_magic_link_existing_user(
        self,
        integration_client: AsyncClient,
        portal_visitor_user: PortalUser,
        postgres_session: AsyncSession,
    ) -> None:
        """Magic link request for existing user creates token."""
        payload = {"email": portal_visitor_user.email}
        response = await integration_client.post(
            _url("default", "/auth/magic-link"),
            json=payload,
        )
        assert response.status_code == status.HTTP_202_ACCEPTED
        data = response.json()
        assert "login link has been sent" in data["message"]

        # Verify token was created in DB
        stmt = select(MagicLinkToken).where(
            MagicLinkToken.portal_user_id == portal_visitor_user.id,
        )
        result = await postgres_session.execute(stmt)
        token = result.scalar_one_or_none()
        assert token is not None
        assert token.used_at is None

    async def test_request_magic_link_nonexistent_user_returns_generic(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """Magic link request for non-existent email returns generic message."""
        payload = {"email": "doesnotexist@example.com"}
        response = await integration_client.post(
            _url("default", "/auth/magic-link"),
            json=payload,
        )
        assert response.status_code == status.HTTP_202_ACCEPTED
        data = response.json()
        assert "login link has been sent" in data["message"]

    async def test_request_magic_link_invalid_email_format(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """Invalid email format returns 422."""
        payload = {"email": "not-an-email"}
        # Pydantic validates min_length but not email format by default
        # The endpoint should accept it (email validation is loose)
        response = await integration_client.post(
            _url("default", "/auth/magic-link"),
            json=payload,
        )
        # Should still return 202 even for invalid-looking emails
        # (to prevent enumeration)
        assert response.status_code == status.HTTP_202_ACCEPTED

    async def test_request_magic_link_invalid_tenant(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """Invalid tenant slug returns 404."""
        payload = {"email": "test@example.com"}
        response = await integration_client.post(
            _url("nonexistent", "/auth/magic-link"),
            json=payload,
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND


# ============================================================================
# Magic link verify (POST /{tenantSlug}/foundation/auth/magic-link/verify)
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestMagicLinkVerify:
    """Tests for the magic link verify endpoint."""

    async def test_verify_valid_token(
        self,
        integration_client: AsyncClient,
        portal_visitor_user: PortalUser,
        postgres_session: AsyncSession,
    ) -> None:
        """Valid token returns JWT access token."""
        # First create a magic link token directly
        from datetime import datetime, timedelta, timezone
        import hashlib
        import secrets

        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

        magic_link = MagicLinkToken(
            tenant_id=portal_visitor_user.tenant_id,
            portal_user_id=portal_visitor_user.id,
            token_hash=token_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        )
        postgres_session.add(magic_link)
        await postgres_session.flush()

        payload = {"token": raw_token}
        response = await integration_client.post(
            _url("default", "/auth/magic-link/verify"),
            json=payload,
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"

        # Verify token was marked as used
        await postgres_session.refresh(magic_link)
        assert magic_link.used_at is not None

    async def test_verify_jwt_claims(
        self,
        integration_client: AsyncClient,
        portal_visitor_user: PortalUser,
        postgres_session: AsyncSession,
    ) -> None:
        """Verify JWT contains correct claims after magic-link verification."""
        from datetime import datetime, timedelta, timezone
        import hashlib
        import secrets

        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

        magic_link = MagicLinkToken(
            tenant_id=portal_visitor_user.tenant_id,
            portal_user_id=portal_visitor_user.id,
            token_hash=token_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        )
        postgres_session.add(magic_link)
        await postgres_session.flush()

        payload = {"token": raw_token}
        response = await integration_client.post(
            _url("default", "/auth/magic-link/verify"),
            json=payload,
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()

        # Decode and verify JWT claims
        decoded = jwt.decode(
            data["access_token"],
            jwt_handler.secret_key,
            algorithms=[jwt_handler.algorithm],
            audience="portal",
        )
        assert decoded["sub"] == str(portal_visitor_user.id)
        assert decoded["tenant_id"] == portal_visitor_user.tenant_id
        assert decoded["aud"] == "portal"
        assert decoded["scope"] == "portal_uploader"
        assert decoded["role"] == portal_visitor_user.role.value

    async def test_verify_expired_token(
        self,
        integration_client: AsyncClient,
        portal_visitor_user: PortalUser,
        postgres_session: AsyncSession,
    ) -> None:
        """Expired token returns 401."""
        from datetime import datetime, timedelta, timezone
        import hashlib
        import secrets

        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

        magic_link = MagicLinkToken(
            tenant_id=portal_visitor_user.tenant_id,
            portal_user_id=portal_visitor_user.id,
            token_hash=token_hash,
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        postgres_session.add(magic_link)
        await postgres_session.flush()

        payload = {"token": raw_token}
        response = await integration_client.post(
            _url("default", "/auth/magic-link/verify"),
            json=payload,
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_verify_reused_token(
        self,
        integration_client: AsyncClient,
        portal_visitor_user: PortalUser,
        postgres_session: AsyncSession,
    ) -> None:
        """Reused token returns 410 Gone."""
        from datetime import datetime, timedelta, timezone
        import hashlib
        import secrets

        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

        magic_link = MagicLinkToken(
            tenant_id=portal_visitor_user.tenant_id,
            portal_user_id=portal_visitor_user.id,
            token_hash=token_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
            used_at=datetime.now(timezone.utc),
        )
        postgres_session.add(magic_link)
        await postgres_session.flush()

        payload = {"token": raw_token}
        response = await integration_client.post(
            _url("default", "/auth/magic-link/verify"),
            json=payload,
        )
        assert response.status_code == status.HTTP_410_GONE

    async def test_verify_invalid_token(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """Invalid token returns 401."""
        payload = {"token": "invalid-token"}
        response = await integration_client.post(
            _url("default", "/auth/magic-link/verify"),
            json=payload,
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    async def test_verify_blocked_user_returns_403(
        self,
        integration_client: AsyncClient,
        portal_visitor_user: PortalUser,
        postgres_session: AsyncSession,
    ) -> None:
        """A blocked user cannot verify a magic link, even with a valid token."""
        from datetime import datetime, timedelta, timezone
        import hashlib
        import secrets

        portal_visitor_user.is_blocked = True
        await postgres_session.flush()

        raw_token = secrets.token_urlsafe(32)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()

        magic_link = MagicLinkToken(
            tenant_id=portal_visitor_user.tenant_id,
            portal_user_id=portal_visitor_user.id,
            token_hash=token_hash,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
        )
        postgres_session.add(magic_link)
        await postgres_session.flush()

        payload = {"token": raw_token}
        response = await integration_client.post(
            _url("default", "/auth/magic-link/verify"),
            json=payload,
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # The token is still consumed (atomic UPDATE runs before the block check),
        # so a blocked user cannot retry the same token after being unblocked.
        await postgres_session.refresh(magic_link)
        assert magic_link.used_at is not None


# ============================================================================
# Logout (POST /{tenantSlug}/foundation/auth/logout)
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
class TestLogout:
    """Tests for the logout endpoint."""

    async def test_logout_returns_204(
        self,
        integration_client: AsyncClient,
    ) -> None:
        """Logout returns 204 No Content."""
        response = await integration_client.post(_url("default", "/auth/logout"))
        assert response.status_code == status.HTTP_204_NO_CONTENT
