"""
WebSocket Router - Real-time Communication Endpoints

Provides WebSocket endpoints at /api/v1/ws/{channel} for:
- Multi-channel/room support
- JWT authentication
- Bidirectional messaging
- Broadcasting to channels
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from src.core.middleware.tenant_context import set_tenant_id
from src.core.websocket.manager import connection_manager
from src.core.api.v1.websocket.dependencies import (
    _validate_channel_name,
    _send_pong,
    _send_error,
    _send_status,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WebSocket"])


# SEC-AGT-004: deze endpoints hadden een `token: str = Query(...)`-parameter, waardoor
# het JWT in de URL belandde. De extractie zit nu in connection_manager.connect(), dat
# de token uit de websocket haalt (cookie -> subprotocol -> Authorization-header) zodra
# er geen token wordt meegegeven. Bewust NIET hier, om core_api geen extra
# architectuurrand naar auth te geven (DSM fan-out-budget, Grade A+).


@router.websocket("/ws/{channel}")
async def websocket_endpoint(
    websocket: WebSocket,
    channel: str,
) -> None:
    """
    WebSocket endpoint for real-time communication.

    SEC-AGT-004: het token komt uit de access_token-cookie, het
    Sec-WebSocket-Protocol subprotocol of de Authorization-header -- niet uit de query
    string (2026-07-31). De extractie gebeurt in connection_manager.connect().
    """
    if not _validate_channel_name(channel):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    conn = await connection_manager.connect(
        websocket=websocket,
        channel=channel,
        require_auth=True,
    )

    if not conn:
        return

    if conn.tenant_id is not None:
        set_tenant_id(conn.tenant_id)

    try:
        while True:
            data = await websocket.receive_text()

            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                await _send_error(websocket, "Invalid JSON format")
                continue

            msg_type = message.get("type", "message")

            if msg_type == "ping":
                await _send_pong(websocket)

            elif msg_type == "message":
                response = {
                    "type": "message",
                    "data": message.get("data", {}),
                    "from": conn.user_id or "anonymous",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                await connection_manager.broadcast_to_channel(channel, response)

            elif msg_type == "broadcast":
                broadcast_msg = {
                    "type": "broadcast",
                    "from": conn.user_id or "anonymous",
                    "data": message.get("data", {}),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                await connection_manager.broadcast_to_channel(channel, broadcast_msg)

            elif msg_type == "status":
                await _send_status(websocket, conn, channel)

            else:
                await _send_error(websocket, f"Unknown message type: {msg_type}")

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: channel={channel}, user={conn.user_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        connection_manager.disconnect(conn)


@router.websocket("/ws/{channel}/{room_id}")
async def websocket_room_endpoint(
    websocket: WebSocket,
    channel: str,
    room_id: str,
) -> None:
    """
    WebSocket endpoint for room-specific communication within a channel.

    SEC-AGT-004: token uit cookie/subprotocol/header, niet uit de query string.
    """
    full_channel = f"{channel}/{room_id}"

    if not _validate_channel_name(channel) or not _validate_channel_name(room_id):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    conn = await connection_manager.connect(
        websocket=websocket,
        channel=full_channel,
        require_auth=True,
    )

    if not conn:
        return

    if conn.tenant_id is not None:
        set_tenant_id(conn.tenant_id)

    try:
        while True:
            data = await websocket.receive_text()

            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                await _send_error(websocket, "Invalid JSON format")
                continue

            msg_type = message.get("type", "message")

            if msg_type == "ping":
                await _send_pong(websocket)

            elif msg_type in ("message", "update", "operation"):
                broadcast_msg = {
                    "type": msg_type,
                    "from": conn.user_id,
                    "data": message.get("data", {}),
                    "room_id": room_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                await connection_manager.broadcast_to_channel(
                    full_channel, broadcast_msg, exclude={conn}
                )
                await websocket.send_json({"type": "ack", "msg_type": msg_type})

            elif msg_type == "status":
                await _send_status(websocket, conn, full_channel)

            else:
                await _send_error(websocket, f"Unknown message type: {msg_type}")

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: channel={full_channel}, user={conn.user_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        connection_manager.disconnect(conn)
