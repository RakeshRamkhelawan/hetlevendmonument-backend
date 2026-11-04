"""
Integration tests for WebSocket cookie-based authentication (Phase 6).

Covers:
- Cookie token is preferred over query param in WS auth
- Invalid cookie token is rejected
- Query-token backward compatibility still works
"""

from unittest.mock import AsyncMock

import pytest
from fastapi import WebSocket
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.dependencies import get_current_user_ws
from src.core.auth.jwt_handler import jwt_handler
from src.core.auth.websocket_auth import WebSocketAuthenticator


@pytest.fixture
def mock_ws_with_cookie():
    """Mock WebSocket with access_token cookie."""
    ws = AsyncMock(spec=WebSocket)
    ws.cookies = {"access_token": "valid_cookie_token"}
    ws.query_params = {}
    ws.headers = {}
    ws.scope = {"query_string": b"", "subprotocols": [], "headers": []}
    return ws


@pytest.fixture
def mock_ws_with_query_token():
    """Mock WebSocket with token in query params (legacy)."""
    ws = AsyncMock(spec=WebSocket)
    ws.cookies = {}
    ws.query_params = {"token": "valid_query_token"}
    ws.headers = {}
    ws.scope = {"query_string": b"token=valid_query_token", "subprotocols": [], "headers": []}
    return ws


@pytest.fixture
def mock_ws_no_auth():
    """Mock WebSocket with no auth credentials."""
    ws = AsyncMock(spec=WebSocket)
    ws.cookies = {}
    ws.query_params = {}
    ws.headers = {}
    ws.scope = {"query_string": b"", "subprotocols": [], "headers": []}
    return ws


@pytest.mark.asyncio
async def test_ws_auth_prefers_cookie_over_query_param(db_session: AsyncSession):
    """Happy path: cookie token takes precedence over query param token."""
    # Create a user and generate a real JWT
    user_email = "ws_cookie_user@example.com"
    from sqlalchemy import select

    from src.core.models.rbac_models import User

    # Check if user exists
    result = await db_session.execute(select(User).where(User.email == user_email))
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            email=user_email,
            hashed_password="dummy",
            tenant_id=1,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

    token = jwt_handler.create_access_token(
        {"sub": str(user.id), "email": user_email, "tenant_id": 1, "user_id": user.id}
    )

    ws = AsyncMock(spec=WebSocket)
    ws.cookies = {"access_token": token}
    ws.query_params = {"token": "legacy_query_token"}
    ws.headers = {}
    ws.scope = {
        "query_string": b"token=legacy_query_token",
        "subprotocols": [],
        "headers": [],
    }

    result_user = await get_current_user_ws(ws, db_session)
    assert result_user.email == user_email


@pytest.mark.asyncio
async def test_ws_auth_rejects_invalid_cookie(db_session: AsyncSession):
    """Unhappy path: invalid cookie token is rejected with 401."""
    ws = AsyncMock(spec=WebSocket)
    ws.cookies = {"access_token": "invalid_token"}
    ws.query_params = {}
    ws.headers = {}
    ws.scope = {"query_string": b"", "subprotocols": [], "headers": []}

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_ws(ws, db_session)
    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_ws_auth_rejects_query_param_token(db_session: AsyncSession):
    """SEC-AGT-004: get_current_user_ws mag een token uit de query string NIET accepteren.

    Deze test heette test_ws_auth_query_param_backward_compat en verifieerde het
    omgekeerde: dat een geldig token in de URL nog steeds inlogde "voor transitional
    compatibility". Dat maakte de SEC-AGT-004-hardening in WebSocketAuthenticator
    omzeilbaar via deze dependency -- en de test hield dat gat in stand in plaats van het
    te signaleren. Het query-pad is op 2026-07-31 verwijderd; deze test bewaakt dat nu.
    """
    user_email = "ws_query_user@example.com"
    from sqlalchemy import select

    from src.core.models.rbac_models import User

    result = await db_session.execute(select(User).where(User.email == user_email))
    user = result.scalar_one_or_none()

    if not user:
        user = User(
            email=user_email,
            hashed_password="dummy",
            tenant_id=1,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)

    token = jwt_handler.create_access_token(
        {"sub": str(user.id), "email": user_email, "tenant_id": 1, "user_id": user.id}
    )

    ws = AsyncMock(spec=WebSocket)
    ws.cookies = {}
    ws.query_params = {"token": token}
    ws.headers = {}
    ws.scope = {"query_string": f"token={token}".encode(), "subprotocols": [], "headers": []}

    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user_ws(ws, db_session)
    assert exc_info.value.status_code == 401, (
        "Een geldig token in de query string moet 401 geven, niet inloggen "
        "(SEC-AGT-004, OWASP ASVS V7)"
    )


class TestWebSocketAuthenticatorCookieExtraction:
    """Unit-style tests for WebSocketAuthenticator cookie extraction."""

    def test_extract_from_cookie(self):
        ws = AsyncMock(spec=WebSocket)
        ws.cookies = {"access_token": "cookie_jwt"}
        ws.scope = {"query_string": b"", "subprotocols": [], "headers": []}

        auth = WebSocketAuthenticator()
        token = auth._extract_token(ws)
        assert token == "cookie_jwt"

    def test_cookie_precedence_over_query(self):
        ws = AsyncMock(spec=WebSocket)
        ws.cookies = {"access_token": "cookie_jwt"}
        ws.scope = {
            "query_string": b"token=query_jwt",
            "subprotocols": [],
            "headers": [],
        }

        auth = WebSocketAuthenticator()
        token = auth._extract_token(ws)
        assert token == "cookie_jwt"

    def test_query_param_token_is_never_accepted(self):
        """SEC-AGT-004: het ``?token=``-pad is bewust verwijderd en mag niet terugkomen.

        Deze test eiste tot 2026-07-31 het OMGEKEERDE (``assert token == "query_jwt"``)
        en stond daardoor rood sinds de hardening -- OWASP ASVS V7 verbiedt
        sessie-identifiers in query strings: ze lekken in access logs, browsergeschiedenis,
        proxy logs en de Referer-header. Nu bewaakt hij de hardening in plaats van hem
        tegen te spreken (OP-11 cluster E).
        """
        ws = AsyncMock(spec=WebSocket)
        ws.cookies = {}
        ws.scope = {
            "query_string": b"token=query_jwt",
            "subprotocols": [],
            "headers": [],
        }

        auth = WebSocketAuthenticator()
        token = auth._extract_token(ws)
        assert token is None, (
            "Een token uit de query string mag NOOIT geaccepteerd worden (SEC-AGT-004). "
            f"Gekregen: {token!r}"
        )

    def test_no_token_returns_none(self):
        ws = AsyncMock(spec=WebSocket)
        ws.cookies = {}
        ws.scope = {"query_string": b"", "subprotocols": [], "headers": []}

        auth = WebSocketAuthenticator()
        token = auth._extract_token(ws)
        assert token is None
