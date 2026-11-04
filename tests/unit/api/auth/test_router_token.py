"""Unit tests for token router (src/core/api/auth/router_token.py).

Covers all 5 endpoints:
- POST /refresh
- POST /revoke
- GET  /validate
- POST /verify-token
- POST /logout
"""

from __future__ import annotations

import contextlib
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from starlette.requests import Request
from starlette.responses import Response

from src.core.api.auth.router_token import (
    RefreshTokenRequest,
    RevokeTokenRequest,
    TokenVerifyRequest,
    logout_endpoint,
    refresh_token,
    revoke_token_endpoint,
    router,
    validate_token,
    verify_token_endpoint,
)
from src.core.api.auth.schemas import UserResponse


class DummyUser:
    def __init__(self, id: int = 1, email: str = "test@example.com", tenant_id: int = 42) -> None:
        self.id = id
        self.email = email
        self.tenant_id = tenant_id
        self.is_active = True


def _create_mock_request(cookies: dict[str, str] | None = None, headers: list[tuple[bytes, bytes]] | None = None) -> Request:
    scope: dict[str, Any] = {
        "type": "http",
        "method": "POST",
        "path": "/refresh",
        "headers": headers or [],
        "client": ("127.0.0.1", 8080),
    }
    req = Request(scope)
    if cookies:
        req._cookies = cookies
    return req


def test_routes_registered() -> None:
    from fastapi.routing import APIRoute

    routes = [r for r in router.routes if isinstance(r, APIRoute)]
    paths = {r.path for r in routes}
    assert "/refresh" in paths
    assert "/revoke" in paths
    assert "/validate" in paths
    assert "/verify-token" in paths
    assert "/logout" in paths


@pytest.mark.asyncio
async def test_refresh_token_missing_token_returns_401() -> None:
    req = _create_mock_request()
    res = Response()
    data = RefreshTokenRequest(refresh_token="")

    with pytest.raises(HTTPException) as exc_info:
        await refresh_token(data=data, request=req, response=res, db=AsyncMock())
    assert exc_info.value.status_code == 401
    assert "Refresh token required" in exc_info.value.detail


@pytest.mark.asyncio
async def test_refresh_token_invalid_returns_401() -> None:
    req = _create_mock_request()
    res = Response()
    data = RefreshTokenRequest(refresh_token="invalid.refresh.token")

    with patch("src.core.api.auth.router_token.oauth2_service.refresh_access_token", new=AsyncMock(return_value=None)), patch(
        "src.core.api.auth.router_token.log_security_event", new=AsyncMock()
    ) as mock_log:
        with pytest.raises(HTTPException) as exc_info:
            await refresh_token(data=data, request=req, response=res, db=AsyncMock())
        assert exc_info.value.status_code == 401
        assert "Invalid or expired refresh token" in exc_info.value.detail
        mock_log.assert_awaited_once()


@pytest.mark.asyncio
async def test_refresh_token_success() -> None:
    req = _create_mock_request()
    res = Response()
    data = RefreshTokenRequest(refresh_token="valid.refresh.token")

    fake_result = {
        "access_token": "new.access.token",
        "token_type": "bearer",
        "expires_in": 3600,
    }

    with patch("src.core.api.auth.router_token.oauth2_service.refresh_access_token", new=AsyncMock(return_value=fake_result)), patch(
        "src.core.api.auth.router_token.log_security_event", new=AsyncMock()
    ):
        result = await refresh_token(data=data, request=req, response=res, db=AsyncMock())
        assert result.access_token == "new.access.token"
        assert result.expires_in == 3600


@pytest.mark.asyncio
async def test_revoke_token_invalid_token_returns_401() -> None:
    req = _create_mock_request()
    res = Response()
    data = RevokeTokenRequest(token="bad.token")
    user = UserResponse(id="1", email="u@example.com", tenant_id="42", role="user")

    with patch("src.core.api.auth.router_token.jwt_handler.verify_token", return_value=None), patch(
        "src.core.api.auth.router_token.log_security_event", new=AsyncMock()
    ):
        with pytest.raises(HTTPException) as exc_info:
            await revoke_token_endpoint(data=data, request=req, response=res, current_user=user, db=AsyncMock())
        assert exc_info.value.status_code == 401
        assert "Invalid token" in exc_info.value.detail


@pytest.mark.asyncio
async def test_revoke_token_success() -> None:
    req = _create_mock_request()
    res = Response()
    data = RevokeTokenRequest(token="valid.token")
    user = UserResponse(id="1", email="u@example.com", tenant_id="42", role="user")

    with patch("src.core.api.auth.router_token.jwt_handler.verify_token",
        # Een echt token draagt altijd `tenant_id`; de eigenaarcontrole vergelijkt die met de sessie.
        return_value={"sub": "1", "tenant_id": 42},
    ), patch(
        "src.core.api.auth.router_token.oauth2_service.revoke_token", new=AsyncMock(return_value=True)
    ), patch("src.core.api.auth.router_token.log_security_event", new=AsyncMock()):
        result = await revoke_token_endpoint(data=data, request=req, response=res, current_user=user, db=AsyncMock())
        assert result.revoked is True


@pytest.mark.asyncio
async def test_validate_token_success() -> None:
    token = "test.jwt.token"
    payload = {"sub": "1", "scopes": ["read", "write"], "exp": 1999999999}

    db = AsyncMock()
    lookup_session = AsyncMock()
    lookup_row = MagicMock()
    lookup_row.id = 1
    lookup_row.tenant_id = 42

    mock_lookup_res = MagicMock()
    mock_lookup_res.one_or_none.return_value = lookup_row
    lookup_session.execute.return_value = mock_lookup_res

    user = DummyUser(id=1, email="test@example.com", tenant_id=42)
    mock_db_res = MagicMock()
    mock_db_res.scalar_one_or_none.return_value = user
    db.execute.return_value = mock_db_res

    @contextlib.asynccontextmanager
    async def mock_pre_auth(s: Any):
        yield lookup_session

    @contextlib.asynccontextmanager
    async def mock_adopt(s: Any, tid: Any):
        yield

    with patch("src.core.api.auth.router_token.jwt_handler.verify_token", return_value=payload), patch(
        "src.core.api.auth.router_token.oauth2_service.is_token_valid", new=AsyncMock(return_value=True)
    ), patch("src.core.api.auth.router_token.pre_auth_lookup", side_effect=mock_pre_auth), patch(
        "src.core.api.auth.router_token.adopt_tenant", side_effect=mock_adopt
    ):
        res = await validate_token(token=token, db=db)
        assert res.active is True
        assert res.username == "test@example.com"
        assert res.scope == "read write"


@pytest.mark.asyncio
async def test_verify_token_endpoint_success() -> None:
    token = "sync.jwt.token"
    data = TokenVerifyRequest(token=token)
    req = _create_mock_request()
    res = Response()
    payload = {"sub": "5", "tenant_id": "42"}

    db = AsyncMock()
    lookup_session = AsyncMock()
    lookup_row = MagicMock()
    lookup_row.id = 5
    lookup_row.tenant_id = 42

    mock_lookup_res = MagicMock()
    mock_lookup_res.one_or_none.return_value = lookup_row
    lookup_session.execute.return_value = mock_lookup_res

    user = DummyUser(id=5, email="sync@example.com", tenant_id=42)
    mock_db_res = MagicMock()
    mock_db_res.scalar_one_or_none.return_value = user
    db.execute.return_value = mock_db_res

    @contextlib.asynccontextmanager
    async def mock_pre_auth(s: Any):
        yield lookup_session

    @contextlib.asynccontextmanager
    async def mock_adopt(s: Any, tid: Any):
        yield

    with patch("src.core.api.auth.router_token.jwt_handler.verify_token", return_value=payload), patch(
        "src.core.api.auth.router_token.oauth2_service.is_token_valid", new=AsyncMock(return_value=True)
    ), patch("src.core.api.auth.router_token.pre_auth_lookup", side_effect=mock_pre_auth), patch(
        "src.core.api.auth.router_token.adopt_tenant", side_effect=mock_adopt
    ):
        resp = await verify_token_endpoint(data=data, request=req, response=res, db=db)
        assert resp.valid is True
        assert resp.tenantId == "42"
        assert resp.userId == "5"


@pytest.mark.asyncio
async def test_logout_endpoint_clears_cookies() -> None:
    req = _create_mock_request(cookies={"access_token": "logged_in_token"})
    res = Response()
    user = UserResponse(id="1", email="u@example.com", tenant_id="42", role="user")

    from src.core.auth.oauth2_service import oauth2_service

    with patch.object(oauth2_service, "revoke_token", new_callable=AsyncMock, return_value=True):
        result = await logout_endpoint(
            request=req,
            response=res,
            current_user=user,
            db=AsyncMock(),
            _csrf=None,
        )
    assert result["message"] == "Logged out successfully"
