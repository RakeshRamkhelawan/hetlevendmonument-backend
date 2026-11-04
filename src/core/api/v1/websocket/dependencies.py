"""WebSocket dependencies -- helper functions."""

from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket
from src.core.websocket.manager import connection_manager


def _validate_channel_name(name: str) -> bool:
    """Validate channel/room name format."""
    if not name or len(name) > 64:
        return False
    allowed_chars = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
    return all(c in allowed_chars for c in name)


async def _send_pong(websocket: WebSocket) -> None:
    """Send pong response."""
    await websocket.send_json(
        {
            "type": "pong",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )


async def _send_error(websocket: WebSocket, message: str) -> None:
    """Send error message."""
    await websocket.send_json(
        {
            "type": "error",
            "message": message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )


async def _send_status(websocket: WebSocket, conn: Any, channel: str) -> None:  # TODO(TYPE): replace Any with concrete type
    """Send connection status."""
    await websocket.send_json(
        {
            "type": "status",
            "channel": channel,
            "user_id": conn.user_id,
            "tenant_id": conn.tenant_id,
            "connected_at": conn.connected_at.isoformat(),
            "channel_connections": connection_manager.get_channel_count(channel),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    )
