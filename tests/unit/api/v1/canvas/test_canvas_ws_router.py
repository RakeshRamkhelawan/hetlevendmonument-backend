"""Unit tests for canvas WebSocket router (src/core/api/v1/canvas/canvas_ws_router.py).

Covers:
- WebSocket /ws/{canvas_id}
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from starlette.routing import WebSocketRoute

from src.core.api.v1.canvas.canvas_ws_router import (
    canvas_websocket_endpoint,
    canvas_ws_router,
)


def test_routes_registered() -> None:
    routes = [r for r in canvas_ws_router.routes if isinstance(r, WebSocketRoute)]
    paths = {r.path for r in routes}
    assert "/ws/{canvas_id}" in paths


@pytest.mark.asyncio
async def test_canvas_websocket_endpoint_delegates_to_handler() -> None:
    mock_ws = AsyncMock()
    canvas_id = uuid4()
    mock_db = AsyncMock()
    mock_user = MagicMock()
    mock_user.id = 123

    with patch("src.core.api.v1.canvas.websocket.handle_canvas_websocket", new=AsyncMock()) as mock_handle:
        await canvas_websocket_endpoint(
            websocket=mock_ws,
            canvas_id=canvas_id,
            client_id="client-xyz",
            db=mock_db,
            tenant_id=42,
            current_user=mock_user,
        )
        mock_handle.assert_awaited_once_with(
            websocket=mock_ws,
            canvas_id=canvas_id,
            client_id="client-xyz",
            user_id=123,
            user_name="User 123",
            db=mock_db,
            tenant_id=42,
        )
