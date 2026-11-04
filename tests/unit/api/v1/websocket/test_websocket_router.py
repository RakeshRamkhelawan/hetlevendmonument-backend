"""Unit tests for WebSocket router (src/core/api/v1/websocket/router.py)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import WebSocketDisconnect
from starlette.routing import WebSocketRoute

from src.core.api.v1.websocket.router import (
    router,
    websocket_endpoint,
    websocket_room_endpoint,
)

pytestmark = pytest.mark.unit


def test_routes_registered() -> None:
    routes = [r for r in router.routes if isinstance(r, WebSocketRoute)]
    paths = {r.path for r in routes}
    assert "/ws/{channel}" in paths
    assert "/ws/{channel}/{room_id}" in paths


@pytest.mark.asyncio
async def test_websocket_endpoint_invalid_channel_closes_connection() -> None:
    mock_ws = AsyncMock()
    await websocket_endpoint(mock_ws, channel="invalid channel!")
    mock_ws.close.assert_awaited_once_with(code=1008)


@pytest.mark.asyncio
async def test_websocket_endpoint_auth_failure() -> None:
    mock_ws = AsyncMock()
    with patch("src.core.api.v1.websocket.router.connection_manager.connect", AsyncMock(return_value=None)):
        await websocket_endpoint(mock_ws, channel="valid-channel")
    mock_ws.receive_text.assert_not_called()


@pytest.mark.asyncio
async def test_websocket_endpoint_ping_pong_and_disconnect() -> None:
    mock_ws = AsyncMock()
    mock_ws.receive_text.side_effect = [
        json.dumps({"type": "ping"}),
        WebSocketDisconnect(1000),
    ]

    mock_conn = MagicMock()
    mock_conn.tenant_id = 1
    mock_conn.user_id = "user_1"

    with patch("src.core.api.v1.websocket.router.connection_manager.connect", AsyncMock(return_value=mock_conn)), \
         patch("src.core.api.v1.websocket.router.connection_manager.disconnect") as mock_disconnect, \
         patch("src.core.api.v1.websocket.router._send_pong", AsyncMock()) as mock_pong:
        await websocket_endpoint(mock_ws, channel="general")

        mock_pong.assert_awaited_once_with(mock_ws)
        mock_disconnect.assert_called_once_with(mock_conn)


@pytest.mark.asyncio
async def test_websocket_endpoint_message_broadcast() -> None:
    mock_ws = AsyncMock()
    mock_ws.receive_text.side_effect = [
        json.dumps({"type": "message", "data": {"text": "hello"}}),
        WebSocketDisconnect(1000),
    ]

    mock_conn = MagicMock()
    mock_conn.tenant_id = 1
    mock_conn.user_id = "user_1"

    with patch("src.core.api.v1.websocket.router.connection_manager.connect", AsyncMock(return_value=mock_conn)), \
         patch("src.core.api.v1.websocket.router.connection_manager.broadcast_to_channel", AsyncMock()) as mock_broadcast, \
         patch("src.core.api.v1.websocket.router.connection_manager.disconnect"):
        await websocket_endpoint(mock_ws, channel="general")

        assert mock_broadcast.called
        channel_arg, msg_arg = mock_broadcast.call_args[0]
        assert channel_arg == "general"
        assert msg_arg["type"] == "message"
        assert msg_arg["data"] == {"text": "hello"}


@pytest.mark.asyncio
async def test_websocket_room_endpoint_invalid_room_closes() -> None:
    mock_ws = AsyncMock()
    await websocket_room_endpoint(mock_ws, channel="general", room_id="invalid room!")
    mock_ws.close.assert_awaited_once_with(code=1008)


@pytest.mark.asyncio
async def test_websocket_room_endpoint_message_and_ack() -> None:
    mock_ws = AsyncMock()
    mock_ws.receive_text.side_effect = [
        json.dumps({"type": "message", "data": {"room": "data"}}),
        WebSocketDisconnect(1000),
    ]

    mock_conn = MagicMock()
    mock_conn.tenant_id = 2
    mock_conn.user_id = "user_2"

    with patch("src.core.api.v1.websocket.router.connection_manager.connect", AsyncMock(return_value=mock_conn)), \
         patch("src.core.api.v1.websocket.router.connection_manager.broadcast_to_channel", AsyncMock()) as mock_broadcast, \
         patch("src.core.api.v1.websocket.router.connection_manager.disconnect"):
        await websocket_room_endpoint(mock_ws, channel="general", room_id="room-1")

        assert mock_broadcast.called
        assert mock_ws.send_json.called
        ack_call = mock_ws.send_json.call_args[0][0]
        assert ack_call == {"type": "ack", "msg_type": "message"}
