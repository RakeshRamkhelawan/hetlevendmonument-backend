"""Unit tests for Foundation Portal auth router (src/core/api/v1/foundation/auth.py).

Covers:
- POST /magic-link
- POST /magic-link/verify
- POST /logout
"""

from __future__ import annotations

import contextlib
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from src.core.api.v1.foundation.auth import (
    MagicLinkRequest,
    MagicLinkVerifyRequest,
    _hash_token,
    logout,
    request_magic_link,
    router,
    verify_magic_link,
)
from src.core.models.foundation_content import PortalRole


class DummyTenant:
    def __init__(self, id: int = 10, slug: str = "tenant-a") -> None:
        self.id = id
        self.slug = slug


class DummyPortalUser:
    def __init__(
        self,
        id: int = 100,
        tenant_id: int = 10,
        email: str = "user@example.com",
        is_blocked: bool = False,
        role: PortalRole = PortalRole.VISITOR,
    ) -> None:
        self.id = id
        self.tenant_id = tenant_id
        self.email = email
        self.is_blocked = is_blocked
        self.role = role
        self.last_login_at: datetime | None = None
        self.email_verified: bool = False


class DummyMagicLinkToken:
    def __init__(
        self,
        id: int = 50,
        tenant_id: int = 10,
        portal_user_id: int = 100,
        token_hash: str = "some_hash",
        expires_at: datetime | None = None,
        used_at: datetime | None = None,
    ) -> None:
        self.id = id
        self.tenant_id = tenant_id
        self.portal_user_id = portal_user_id
        self.token_hash = token_hash
        self.expires_at = expires_at or (datetime.now(timezone.utc) + timedelta(minutes=15))
        self.used_at = used_at


def _create_mock_request() -> Request:
    scope: dict[str, Any] = {
        "type": "http",
        "method": "POST",
        "path": "/auth/magic-link",
        "headers": [],
        "app": MagicMock(),
        "client": ("127.0.0.1", 12345),
    }
    req = Request(scope)
    req.state.parsed_email = None
    return req


def test_routes_registered() -> None:
    from fastapi.routing import APIRoute

    routes = [r for r in router.routes if isinstance(r, APIRoute)]
    paths = {r.path for r in routes}
    assert "/auth/magic-link" in paths
    assert "/auth/magic-link/verify" in paths
    assert "/auth/logout" in paths


@pytest.mark.asyncio
async def test_request_magic_link_user_not_found_returns_generic_message() -> None:
    req = _create_mock_request()
    session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_result

    tenant = DummyTenant(id=1, slug="demo")

    @contextlib.asynccontextmanager
    async def mock_scope(slug: str, s: Any):
        yield tenant

    with patch("src.core.api.v1.foundation.auth.public_tenant_scope", side_effect=mock_scope), patch(
        "src.core.api.v1.foundation.auth.require_portal_magic_link_email_rate_limit",
        new=AsyncMock(),
    ):
        data = MagicLinkRequest(email="unknown@example.com")
        res = await request_magic_link(
            tenantSlug="demo",
            request=req,
            data=data,
            session=session,
            _check_ip=None,
        )
        assert res["message"] == "If the email exists, a login link has been sent."
        # Verify no token was added
        session.add.assert_not_called()


@pytest.mark.asyncio
async def test_request_magic_link_user_found_creates_token_and_sends_notification() -> None:
    req = _create_mock_request()
    session = AsyncMock()
    tenant = DummyTenant(id=1, slug="demo")
    user = DummyPortalUser(id=42, tenant_id=1, email="existing@example.com")

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = user
    session.execute.return_value = mock_result

    @contextlib.asynccontextmanager
    async def mock_scope(slug: str, s: Any):
        yield tenant

    with patch("src.core.api.v1.foundation.auth.public_tenant_scope", side_effect=mock_scope), patch(
        "src.core.api.v1.foundation.auth.require_portal_magic_link_email_rate_limit",
        new=AsyncMock(),
    ), patch("src.core.api.v1.foundation.auth.notification_service.notify_user", new=AsyncMock()) as mock_notify:
        data = MagicLinkRequest(email="existing@example.com")
        res = await request_magic_link(
            tenantSlug="demo",
            request=req,
            data=data,
            session=session,
            _check_ip=None,
        )
        assert res["message"] == "If the email exists, a login link has been sent."
        session.add.assert_called_once()
        mock_notify.assert_awaited_once()


@pytest.mark.asyncio
async def test_verify_magic_link_token_not_found() -> None:
    req = _create_mock_request()
    session = AsyncMock()
    tenant = DummyTenant(id=1, slug="demo")

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    session.execute.return_value = mock_result

    @contextlib.asynccontextmanager
    async def mock_scope(slug: str, s: Any):
        yield tenant

    with patch("src.core.api.v1.foundation.auth.public_tenant_scope", side_effect=mock_scope):
        data = MagicLinkVerifyRequest(token="invalid_token_123")
        with pytest.raises(HTTPException) as exc_info:
            await verify_magic_link(
                tenantSlug="demo",
                request=req,
                data=data,
                session=session,
                _check_ip=None,
            )
        assert exc_info.value.status_code == 401
        assert "Invalid or expired token" in exc_info.value.detail


@pytest.mark.asyncio
async def test_verify_magic_link_token_expired() -> None:
    req = _create_mock_request()
    session = AsyncMock()
    tenant = DummyTenant(id=1, slug="demo")

    token_obj = DummyMagicLinkToken(
        id=10,
        tenant_id=1,
        portal_user_id=42,
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),  # Expired
    )
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = token_obj
    session.execute.return_value = mock_result

    @contextlib.asynccontextmanager
    async def mock_scope(slug: str, s: Any):
        yield tenant

    with patch("src.core.api.v1.foundation.auth.public_tenant_scope", side_effect=mock_scope):
        data = MagicLinkVerifyRequest(token="expired_token")
        with pytest.raises(HTTPException) as exc_info:
            await verify_magic_link(
                tenantSlug="demo",
                request=req,
                data=data,
                session=session,
                _check_ip=None,
            )
        assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_verify_magic_link_replay_prevention_410() -> None:
    req = _create_mock_request()
    session = AsyncMock()
    tenant = DummyTenant(id=1, slug="demo")

    token_obj = DummyMagicLinkToken(
        id=10,
        tenant_id=1,
        portal_user_id=42,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    # First select returns token
    mock_sel = MagicMock()
    mock_sel.scalar_one_or_none.return_value = token_obj
    # Atomic update returns None (already used)
    mock_upd = MagicMock()
    mock_upd.scalar_one_or_none.return_value = None

    session.execute.side_effect = [mock_sel, mock_upd]

    @contextlib.asynccontextmanager
    async def mock_scope(slug: str, s: Any):
        yield tenant

    with patch("src.core.api.v1.foundation.auth.public_tenant_scope", side_effect=mock_scope):
        data = MagicLinkVerifyRequest(token="replayed_token")
        with pytest.raises(HTTPException) as exc_info:
            await verify_magic_link(
                tenantSlug="demo",
                request=req,
                data=data,
                session=session,
                _check_ip=None,
            )
        assert exc_info.value.status_code == 410
        assert "Token already used" in exc_info.value.detail


@pytest.mark.asyncio
async def test_verify_magic_link_blocked_user_403() -> None:
    req = _create_mock_request()
    session = AsyncMock()
    tenant = DummyTenant(id=1, slug="demo")

    token_obj = DummyMagicLinkToken(
        id=10,
        tenant_id=1,
        portal_user_id=42,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    user = DummyPortalUser(id=42, tenant_id=1, is_blocked=True)

    mock_sel = MagicMock()
    mock_sel.scalar_one_or_none.return_value = token_obj
    mock_upd = MagicMock()
    mock_upd.scalar_one_or_none.return_value = token_obj.id
    mock_user = MagicMock()
    mock_user.scalar_one_or_none.return_value = user

    session.execute.side_effect = [mock_sel, mock_upd, mock_user]

    @contextlib.asynccontextmanager
    async def mock_scope(slug: str, s: Any):
        yield tenant

    with patch("src.core.api.v1.foundation.auth.public_tenant_scope", side_effect=mock_scope), patch(
        "src.core.api.v1.foundation.auth.AuditService.log_event",
        new=AsyncMock(),
    ) as mock_audit:
        data = MagicLinkVerifyRequest(token="valid_token")
        with pytest.raises(HTTPException) as exc_info:
            await verify_magic_link(
                tenantSlug="demo",
                request=req,
                data=data,
                session=session,
                _check_ip=None,
            )
        assert exc_info.value.status_code == 403
        assert "User account is blocked" in exc_info.value.detail
        mock_audit.assert_awaited_once()


@pytest.mark.asyncio
async def test_verify_magic_link_success() -> None:
    req = _create_mock_request()
    session = AsyncMock()
    tenant = DummyTenant(id=1, slug="demo")

    token_obj = DummyMagicLinkToken(
        id=10,
        tenant_id=1,
        portal_user_id=42,
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=5),
    )
    user = DummyPortalUser(id=42, tenant_id=1, is_blocked=False)

    mock_sel = MagicMock()
    mock_sel.scalar_one_or_none.return_value = token_obj
    mock_upd = MagicMock()
    mock_upd.scalar_one_or_none.return_value = token_obj.id
    mock_user = MagicMock()
    mock_user.scalar_one_or_none.return_value = user

    session.execute.side_effect = [mock_sel, mock_upd, mock_user]

    @contextlib.asynccontextmanager
    async def mock_scope(slug: str, s: Any):
        yield tenant

    with patch("src.core.api.v1.foundation.auth.public_tenant_scope", side_effect=mock_scope), patch(
        "src.core.api.v1.foundation.auth.AuditService.log_event",
        new=AsyncMock(),
    ), patch(
        "src.core.api.v1.foundation.auth.jwt_handler.create_access_token",
        return_value="jwt.portal.token",
    ):
        data = MagicLinkVerifyRequest(token="valid_token")
        res = await verify_magic_link(
            tenantSlug="demo",
            request=req,
            data=data,
            session=session,
            _check_ip=None,
        )
        assert res["access_token"] == "jwt.portal.token"
        assert res["token_type"] == "bearer"
        assert user.email_verified is True
        assert user.last_login_at is not None


@pytest.mark.asyncio
async def test_logout() -> None:
    res = await logout()
    assert res is None
