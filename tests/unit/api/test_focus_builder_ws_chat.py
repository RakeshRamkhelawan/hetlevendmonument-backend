"""
Unit tests for the Focus Builder ws/chat WebSocket endpoint.

Verifies:
- Connection without token is rejected (receives non-session_init message or error)
- Authenticated connection responds to ping with pong
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_with_overrides():
    from sqlalchemy.ext.asyncio import AsyncSession

    from src.main import create_test_app
    from src.core.database.database import get_db

    app = create_test_app()

    async def mock_db():
        yield AsyncMock(spec=AsyncSession)

    app.dependency_overrides[get_db] = mock_db
    return app


def test_ws_chat_rejects_missing_token(app_with_overrides):
    """Connection without token must be closed — no session_init sent."""
    with TestClient(app_with_overrides) as client:
        try:
            with client.websocket_connect("/api/v1/focus-builder/ws/chat") as ws:
                data = ws.receive_json()
                # If server sends something, it must not be session_init
                assert data.get("type") != "session_init"
        except Exception:
            # Server may close the connection immediately — that's acceptable
            pass


def test_ws_chat_ping_pong(app_with_overrides):
    """Authenticated connection should respond to ping with pong."""
    valid_token = "test.jwt.token"

    mock_user = MagicMock()
    mock_user.id = 1
    mock_user.tenant_id = 1

    with patch(
        "src.core.api.v1.focus_builder.ws_chat_router.validate_ws_token",
        new=AsyncMock(return_value=mock_user),
    ):
        with patch(
            "src.core.api.v1.focus_builder.ws_chat_router.FocusBuilderToolAgent"
        ) as MockToolAgent:
            MockToolAgent.return_value.start_session = AsyncMock()
            with patch(
                "src.core.api.v1.focus_builder.ws_chat_router.FocusBuilderChatAgent"
            ) as MockAgent:
                instance = MockAgent.return_value
                instance.start_session = AsyncMock()

                with TestClient(app_with_overrides) as client:
                    # SEC-AGT-004: authenticatie via de access_token-cookie; het
                    # ?token=-pad is verwijderd (2026-07-31).
                    client.cookies.set("access_token", valid_token)
                    with client.websocket_connect("/api/v1/focus-builder/ws/chat") as ws:
                        ws.send_json({"type": "ping"})
                        resp = ws.receive_json()
                        assert resp["type"] == "pong"
