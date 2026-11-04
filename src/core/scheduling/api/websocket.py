"""
WebSocket endpoint for real-time scheduling updates.

Heartbeat: server sends ping every 30 s; client must reply with pong
            within 10 s or the connection is dropped.
Reconnect: on server-initiated close the payload contains
           {"code": 1001, "reconnect": true, "backoff_ms": <int>}.
           Clients should honour the backoff before reconnecting.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from src.core.auth.websocket_auth import AuthenticatedUser, WebSocketAuthenticator

logger = logging.getLogger(__name__)

HEARTBEAT_INTERVAL_S = 30
HEARTBEAT_TIMEOUT_S = 10

router = APIRouter()


# ---------------------------------------------------------------------------
# Connection tracking
# ---------------------------------------------------------------------------


@dataclass
class _TrackedConnection:
    ws: WebSocket
    user: AuthenticatedUser
    last_pong: float = field(default_factory=time.monotonic)
    subscriptions: set[str] = field(default_factory=set)


class SchedulingConnectionManager:
    """Per-tenant connection registry for scheduling updates."""

    def __init__(self) -> None:
        # tenant_id -> {user_id -> connection}
        self._conns: dict[int, dict[str, _TrackedConnection]] = {}

    # -- lifecycle -----------------------------------------------------------

    def add(self, conn: _TrackedConnection) -> None:
        tid = conn.user.tenant_id
        uid = conn.user.user_id
        bucket = self._conns.setdefault(tid, {})
        bucket[uid] = conn

    def remove(self, user: AuthenticatedUser) -> None:
        bucket = self._conns.get(user.tenant_id)
        if bucket:
            bucket.pop(user.user_id, None)
            if not bucket:
                del self._conns[user.tenant_id]

    # -- querying ------------------------------------------------------------

    def tenant_connections(self, tenant_id: int) -> list[_TrackedConnection]:
        return list(self._conns.get(tenant_id, {}).values())

    @property
    def total(self) -> int:
        return sum(len(b) for b in self._conns.values())


# Module-level instance (attached to app.state in lifespan if desired).
_manager = SchedulingConnectionManager()


def get_manager() -> SchedulingConnectionManager:
    return _manager


# ---------------------------------------------------------------------------
# Broadcast helpers
# ---------------------------------------------------------------------------


async def broadcast_to_tenant(tenant_id: int, event_type: str, payload: dict[str, Any]) -> int:  # TODO(TYPE): replace Any with concrete type
    """Push a scheduling event to every connected user for *tenant_id*."""
    message = json.dumps({"type": event_type, "data": payload})
    sent = 0
    for conn in _manager.tenant_connections(tenant_id):
        try:
            if conn.ws.client_state == WebSocketState.CONNECTED:
                await conn.ws.send_text(message)
                sent += 1
        except Exception:
            logger.debug("Failed to send to %s", conn.user.user_id)
    return sent


async def notify_participants(
    tenant_id: int, participant_ids: list[str], event_type: str, payload: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
) -> int:
    """Notify a specific set of participants within a tenant."""
    message = json.dumps({"type": event_type, "data": payload})
    sent = 0
    for conn in _manager.tenant_connections(tenant_id):
        if conn.user.user_id in participant_ids:
            try:
                if conn.ws.client_state == WebSocketState.CONNECTED:
                    await conn.ws.send_text(message)
                    sent += 1
            except Exception:
                logger.debug("Failed to send to %s", conn.user.user_id)
    return sent


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------


async def _heartbeat_loop(conn: _TrackedConnection) -> None:
    """Periodically ping the client; drop connection if no pong arrives."""
    try:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL_S)
            if conn.ws.client_state != WebSocketState.CONNECTED:
                return
            try:
                await conn.ws.send_json({"type": "ping", "ts": time.time()})
            except Exception:
                return
            # Check last pong age
            if time.monotonic() - conn.last_pong > (HEARTBEAT_INTERVAL_S + HEARTBEAT_TIMEOUT_S):
                logger.warning("Heartbeat timeout for user %s", conn.user.user_id)
                try:
                    await conn.ws.close(
                        code=1001,
                        reason=json.dumps({"reconnect": True, "backoff_ms": 2000}),
                    )
                except Exception:
                    pass
                return
    except asyncio.CancelledError:
        return


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------

_authenticator = WebSocketAuthenticator()


@router.websocket("/ws/scheduling")
async def scheduling_ws(websocket: WebSocket) -> None:
    user: AuthenticatedUser | None = await _authenticator.authenticate(websocket)
    if user is None:
        return  # authenticate() already closed the socket

    conn = _TrackedConnection(ws=websocket, user=user)
    _manager.add(conn)
    heartbeat_task = asyncio.create_task(_heartbeat_loop(conn))

    try:
        # Send welcome payload
        await websocket.send_json(
            {
                "type": "connected",
                "user_id": user.user_id,
                "tenant_id": user.tenant_id,
                "heartbeat_interval_s": HEARTBEAT_INTERVAL_S,
            }
        )

        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                await websocket.send_json({"type": "error", "message": "Invalid JSON"})
                continue

            msg_type = msg.get("type")

            if msg_type == "pong":
                conn.last_pong = time.monotonic()

            elif msg_type == "subscribe":
                # Subscribe to specific event channels
                channel = msg.get("channel")
                if channel:
                    conn.subscriptions.add(channel)
                    await websocket.send_json({"type": "subscribed", "channel": channel})

            elif msg_type == "unsubscribe":
                channel = msg.get("channel")
                if channel:
                    conn.subscriptions.discard(channel)
                    await websocket.send_json({"type": "unsubscribed", "channel": channel})

            else:
                await websocket.send_json({"type": "error", "message": f"Unknown type: {msg_type}"})

    except WebSocketDisconnect:
        logger.info("Client disconnected: %s", user.user_id)
    except Exception:
        logger.exception("WebSocket error for user %s", user.user_id)
    finally:
        heartbeat_task.cancel()
        _manager.remove(user)
        _authenticator.disconnect(user.user_id)
