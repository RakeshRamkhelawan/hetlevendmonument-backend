"""
SP-G03: Copilot WebSocket chat end-to-end verification tests.

Scope:
- Backend: cookie-first auth, set_tenant_id, streaming response format
- Frontend: mountedRef guard, cleanup, no hardcoded localhost, env var usage

These tests verify (not build) the existing implementation.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, WebSocketDisconnect
from fastapi.testclient import TestClient

from src.core.copilot.api.chat_websocket import router as ws_router


@pytest.fixture
def app_with_ws() -> FastAPI:
    app = FastAPI()

    from src.core.database.database import get_db

    async def _mock_db() -> Any:
        yield AsyncMock()

    app.dependency_overrides[get_db] = _mock_db
    app.include_router(ws_router)
    return app


@pytest.fixture
def client(app_with_ws: FastAPI) -> TestClient:
    return TestClient(app_with_ws)


def _fake_user(user_id: str = "7", tenant_id: int = 42) -> MagicMock:
    user = MagicMock()
    user.user_id = user_id
    user.tenant_id = tenant_id
    return user


def _mock_auth_accept(user: MagicMock) -> Any:
    """Patch _auth.authenticate to accept the websocket and return user."""

    async def _auth(websocket, required_roles=None):
        await websocket.accept()
        return user

    return patch("src.core.copilot.api.chat_websocket._auth.authenticate", new=_auth)


def _mock_auth_reject() -> Any:
    """Patch _auth.authenticate to close websocket and return None."""

    async def _auth(websocket, required_roles=None):
        await websocket.close(code=4001, reason="No authentication token provided")
        return None

    return patch("src.core.copilot.api.chat_websocket._auth.authenticate", new=_auth)


def _patch_redis() -> Any:
    """Return a patch target that mocks Redis."""
    mock_redis = AsyncMock()
    return patch("src.core.copilot.api.chat_websocket.get_redis", return_value=mock_redis)


def _patch_service() -> Any:
    """Return a patch target that mocks the CopilotService."""
    mock_svc = AsyncMock()

    async def _stream(*args, **kwargs):
        yield {"type": "chunk", "content": "Hello"}
        yield {"type": "done", "payload": {"verdict": "approved"}}

    mock_svc.handle_turn_stream = _stream
    mock_svc.handle_turn.return_value = MagicMock(message="Hello")

    return patch(
        "src.core.copilot.api.chat_websocket._build_copilot_service",
        return_value=mock_svc,
    )


def _patch_db_manager() -> Any:
    """Return a patch target that mocks db_manager."""
    mock_session = AsyncMock()
    mock_session_maker = MagicMock(return_value=mock_session)
    return patch(
        "src.core.copilot.api.chat_websocket.db_manager.async_session_maker",
        mock_session_maker,
    )


# =====================================================================
# Backend Tests
# =====================================================================


class TestCopilotWebSocketBackend:
    """Verify backend Copilot WS endpoint behavior per SP-G03 spec."""

    @pytest.mark.unit
    def test_endpoint_registered_at_canonical_path(self, client: TestClient) -> None:
        """The canonical /ws/copilot/chat endpoint must accept connections."""
        user = _fake_user()
        with _mock_auth_accept(user), _patch_redis(), _patch_service(), _patch_db_manager():
            with client.websocket_connect("/ws/copilot/chat") as ws:
                init = ws.receive_json()
                assert init["type"] == "session_init"
                assert "session_id" in init

    @pytest.mark.unit
    def test_endpoint_registered_at_alias_path(self, client: TestClient) -> None:
        """The alias /api/v1/ws/copilot/chat endpoint must accept connections."""
        user = _fake_user()
        with _mock_auth_accept(user), _patch_redis(), _patch_service(), _patch_db_manager():
            with client.websocket_connect("/api/v1/ws/copilot/chat") as ws:
                init = ws.receive_json()
                assert init["type"] == "session_init"

    @pytest.mark.unit
    @pytest.mark.security
    def test_rejects_unauthenticated_connection(self, client: TestClient) -> None:
        """WS connection without valid auth must be rejected (4001)."""
        with _mock_auth_reject():
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect("/ws/copilot/chat") as ws:
                    ws.receive_text()

    @pytest.mark.unit
    @pytest.mark.security
    def test_sets_tenant_id_after_auth(self, client: TestClient) -> None:
        """After successful auth, set_tenant_id must be called with user.tenant_id."""
        user = _fake_user(tenant_id=99)
        with patch("src.core.copilot.api.chat_websocket.set_tenant_id") as mock_set_tenant:
            with _mock_auth_accept(user), _patch_redis(), _patch_service(), _patch_db_manager():
                with client.websocket_connect("/ws/copilot/chat") as ws:
                    ws.receive_json()  # session_init
                    # Trigger any message to ensure the handler runs past auth
                    ws.send_json({"type": "ping"})
                    ws.receive_json()  # pong

        mock_set_tenant.assert_called_once_with(99)

    @pytest.mark.unit
    @pytest.mark.security
    def test_cookie_first_auth_attempt(self, client: TestClient) -> None:
        """WebSocketAuthenticator must try cookie before subprotocol/header, and
        must never fall back to a ?token= query param (removed per SEC-AGT-004,
        OWASP ASVS V7 -- session identifiers must not appear in URLs)."""
        import inspect

        from src.core.auth.websocket_auth import WebSocketAuthenticator

        source = inspect.getsource(WebSocketAuthenticator._extract_token)
        cookie_idx = source.find('cookies.get("access_token")')
        subprotocol_idx = source.find('protocol == "access_token"')
        header_idx = source.find('headers.get(b"authorization"')

        assert cookie_idx != -1, "Cookie auth not found in _extract_token"
        assert subprotocol_idx != -1, "Sec-WebSocket-Protocol fallback not found in _extract_token"
        assert header_idx != -1, "Authorization header fallback not found in _extract_token"
        assert cookie_idx < subprotocol_idx < header_idx, (
            "Order must be cookie -> subprotocol -> Authorization header"
        )
        # SEC-AGT-004: the query-param method must stay removed.
        assert '"token" in params' not in source
        assert "request.query_params" not in source

    @pytest.mark.unit
    def test_streaming_response_format(self, client: TestClient) -> None:
        """Streaming response must send chunk objects followed by done."""
        user = _fake_user()
        with _mock_auth_accept(user), _patch_redis(), _patch_service(), _patch_db_manager():
            with client.websocket_connect("/ws/copilot/chat") as ws:
                ws.receive_json()  # session_init
                ws.send_json({"type": "message", "content": "hello"})

                chunk = ws.receive_json()
                assert chunk["type"] == "chunk"
                assert "content" in chunk

                done = ws.receive_json()
                assert done["type"] == "done"
