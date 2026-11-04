"""
Unit tests for Copilot chat WebSocket endpoint.

Covers:
- Auth rejection (no token)
- ping -> pong
- clear -> cleared
- message -> streaming chunks + done
- Max message length enforcement
- ConversationMemory integration (history persists)
- Transitional alias path
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

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


@pytest.mark.unit
@pytest.mark.security
def test_ws_rejects_missing_token(client: TestClient) -> None:
    """Connection without token must be closed."""
    with _mock_auth_reject():
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/copilot/chat") as ws:
                ws.receive_text()


@pytest.mark.unit
def test_ws_ping_pong(client: TestClient) -> None:
    """Authenticated WS responds to ping with pong."""
    user = _fake_user()
    with _mock_auth_accept(user), _patch_redis(), _patch_service(), _patch_db_manager():
        with client.websocket_connect("/ws/copilot/chat") as ws:
            # Skip session_init
            ws.receive_json()
            ws.send_json({"type": "ping"})
            resp = ws.receive_json()
            assert resp["type"] == "pong"


@pytest.mark.unit
def test_ws_clear_clears_memory(client: TestClient) -> None:
    """clear message clears conversation memory."""
    user = _fake_user()
    with _mock_auth_accept(user), _patch_redis(), _patch_service(), _patch_db_manager():
        with client.websocket_connect("/ws/copilot/chat") as ws:
            ws.receive_json()  # session_init
            ws.send_json({"type": "clear"})
            resp = ws.receive_json()
            assert resp["type"] == "cleared"


@pytest.mark.unit
def test_ws_message_streams_chunks_then_done(client: TestClient) -> None:
    """message triggers streaming chunks followed by done."""
    user = _fake_user()
    with _mock_auth_accept(user), _patch_redis(), _patch_service(), _patch_db_manager():
        with client.websocket_connect("/ws/copilot/chat") as ws:
            ws.receive_json()  # session_init
            ws.send_json({"type": "message", "content": "hello"})

            chunk = ws.receive_json()
            assert chunk["type"] == "chunk"
            assert chunk["content"] == "Hello"

            done = ws.receive_json()
            assert done["type"] == "done"


@pytest.mark.unit
@pytest.mark.security
def test_ws_message_too_long_rejected(client: TestClient) -> None:
    """Message exceeding MAX_MESSAGE_LENGTH returns error."""
    user = _fake_user()
    with _mock_auth_accept(user), _patch_redis(), _patch_service(), _patch_db_manager():
        with client.websocket_connect("/ws/copilot/chat") as ws:
            ws.receive_json()  # session_init
            ws.send_json({"type": "message", "content": "x" * 2001})
            resp = ws.receive_json()
            assert resp["type"] == "error"
            assert "too long" in resp["message"]


@pytest.mark.unit
def test_ws_unknown_type_returns_error(client: TestClient) -> None:
    """Unknown message type returns error."""
    user = _fake_user()
    with _mock_auth_accept(user), _patch_redis(), _patch_service(), _patch_db_manager():
        with client.websocket_connect("/ws/copilot/chat") as ws:
            ws.receive_json()  # session_init
            ws.send_json({"type": "foobar"})
            resp = ws.receive_json()
            assert resp["type"] == "error"
            assert "Unknown type" in resp["message"]


@pytest.mark.unit
def test_ws_alias_path_works(client: TestClient) -> None:
    """Transitional alias /api/v1/ws/copilot/chat works."""
    user = _fake_user()
    with _mock_auth_accept(user), _patch_redis(), _patch_service(), _patch_db_manager():
        with client.websocket_connect("/api/v1/ws/copilot/chat") as ws:
            ws.receive_json()  # session_init
            ws.send_json({"type": "ping"})
            resp = ws.receive_json()
            assert resp["type"] == "pong"


@pytest.mark.unit
def test_ws_stores_user_and_assistant_messages(client: TestClient) -> None:
    """ConversationMemory add is called for user message."""
    mock_redis = AsyncMock()
    user = _fake_user()
    with (
        _mock_auth_accept(user),
        patch("src.core.copilot.api.chat_websocket.get_redis", return_value=mock_redis),
        _patch_service(),
        _patch_db_manager(),
    ):
        with client.websocket_connect("/ws/copilot/chat") as ws:
            ws.receive_json()  # session_init
            ws.send_json({"type": "message", "content": "hello"})

            # Consume chunks
            ws.receive_json()  # chunk
            ws.receive_json()  # done

    # Verify rpush was called at least once (user message stored)
    rpush_calls = [c for c in mock_redis.method_calls if c[0] == "rpush"]
    assert len(rpush_calls) >= 1
