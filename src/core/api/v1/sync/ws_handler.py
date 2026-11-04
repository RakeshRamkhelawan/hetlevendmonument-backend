"""
# orphan:exempt reason: pre-ADR-033 domain sub-file, pending Strangler Fig migration (Dag 4/5)
SP-E02 Dag 2: WebSocket Awareness Handler

Real-time collaborative awareness updates via WebSocket.
Clients push cursor/presence updates; the server writes them to Redis
(30 s TTL hash) where other clients read them via the HTTP GET endpoint.

Includes server-side heartbeat (25 s interval) to keep connections alive
through proxies and load balancers.

Endpoint: ws://host/api/v1/sync/ws/awareness/{workflow_id}?token=xxx

ASCII-only, no emojis (CLAUDE.md Section 10).
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from src.core.auth.api_deps import WebSocketAuthenticator
from src.core.api.v1.sync.dependencies import get_redis_client
from src.core.exceptions import ValidatieFout

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sync", tags=["sync"])

# Constants
_AWARENESS_TTL_SECONDS = 30
_HEARTBEAT_INTERVAL_SECONDS = 25
_MAX_MESSAGE_BYTES = 65536  # 64 KiB
_AWARENESS_KEY_PREFIX = "awareness"

# Regex must match json_router.py workflow_id validation
_WORKFLOW_ID_RE = re.compile(r"^[\w\-]+$")

_auth = WebSocketAuthenticator()


class _AwarenessMessageValidator:
    """Validate incoming awareness update messages."""

    ALLOWED_TYPES = {"cursor", "selection", "presence"}

    @classmethod
    def validate(
        cls,
        data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> tuple[str, dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """
        Validate and extract message type + payload.

        Returns:
            (msg_type, payload) on success.

        Raises:
            ValueError with human-readable reason on failure.
        """
        if not isinstance(data, dict):
            raise ValidatieFout("Message must be a JSON object")

        msg_type = data.get("type")
        if msg_type not in cls.ALLOWED_TYPES:
            raise ValidatieFout(
                f"Invalid type '{msg_type}'. Allowed: {', '.join(sorted(cls.ALLOWED_TYPES))}"
            )

        payload = data.get("payload")
        if not isinstance(payload, dict):
            raise ValidatieFout("'payload' must be an object")

        # Flatten payload for storage; reject nested objects > 2 levels
        flat = cls._flatten(payload, max_depth=2)
        if len(json.dumps(flat)) > _MAX_MESSAGE_BYTES:
            raise ValidatieFout("Payload exceeds maximum size")

        return str(msg_type), flat

    @staticmethod
    def _flatten(
        obj: Any,  # TODO(TYPE): replace Any with concrete type
        max_depth: int,
        _depth: int = 0,  # TODO(TYPE): replace Any with concrete type
    ) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Flatten nested structures beyond max_depth to None."""
        if _depth > max_depth:
            return None
        if isinstance(obj, dict):
            return {
                k: _AwarenessMessageValidator._flatten(v, max_depth, _depth + 1)
                for k, v in obj.items()
            }
        if isinstance(obj, list):
            return [_AwarenessMessageValidator._flatten(v, max_depth, _depth + 1) for v in obj]
        return obj


def _awareness_key(tenant_id: int, workflow_id: str) -> str:
    return f"{_AWARENESS_KEY_PREFIX}:{tenant_id}:{workflow_id}"


async def _close_ws(websocket: WebSocket, code: int, reason: str) -> None:
    """Close websocket, swallowing errors on already-closed connections."""
    try:
        await websocket.close(code=code, reason=reason)
    except Exception:
        pass


@router.websocket("/ws/awareness/{workflow_id}")
async def awareness_websocket(websocket: WebSocket, workflow_id: str) -> None:
    """
    WebSocket endpoint for real-time awareness updates.

    Protocol:
        Client -> Server:
            {"type": "cursor",   "payload": {"x": 100, "y": 200, "color": "#ff0000"}}
            {"type": "selection","payload": {"node_ids": ["a", "b"]}}
            {"type": "presence", "payload": {"status": "active"}}

        Server -> Client:
            {"type": "ack", "ts": <epoch_ms>}
            {"type": "error", "message": "..."}

    Redis:
        HSET awareness:{tenant_id}:{workflow_id} {user_id} {json_string}
        EXPIRE awareness:{tenant_id}:{workflow_id} 30

    On disconnect the user's field is removed from the hash (HDEL).
    """
    # Subprotocol negotiation (match agentic_flow pattern)
    protocols = websocket.scope.get("subprotocols", [])
    selected = "json" if "json" in protocols else None

    # Authenticate before accept so we can reject with proper close code
    user = await _auth.authenticate(websocket)
    if user is None:
        return  # Connection closed by auth layer

    # Validate workflow_id
    if not _WORKFLOW_ID_RE.fullmatch(workflow_id):
        logger.warning(
            "awareness_ws_invalid_workflow: user=%s tenant=%s workflow=%s",
            user.user_id,
            user.tenant_id,
            workflow_id,
        )
        await _close_ws(websocket, 4003, "Invalid workflow_id format")
        return

    tenant_id = user.tenant_id
    user_id = user.user_id
    awareness_key = _awareness_key(tenant_id, workflow_id)

    logger.info(
        "awareness_ws_connected: tenant=%s workflow=%s user=%s",
        tenant_id,
        workflow_id,
        user_id,
    )

    redis = await get_redis_client()

    try:
        while True:
            try:
                message = await asyncio.wait_for(
                    websocket.receive_json(), timeout=_HEARTBEAT_INTERVAL_SECONDS
                )
            except asyncio.TimeoutError:
                # No message within heartbeat interval aEUR" send keepalive
                try:
                    await websocket.send_json({"type": "heartbeat"})
                except Exception:
                    # Connection likely dead; loop will exit on next iteration
                    break
                continue

            try:
                msg_type, payload = _AwarenessMessageValidator.validate(message)
            except ValidatieFout as exc:
                await websocket.send_json({"type": "error", "message": str(exc)})
                continue
            except ValueError as exc:
                logger.error("awareness_websocket mislukt: %s: %s", type(exc).__name__, exc, exc_info=True)
                await websocket.send_json({"type": "error", "message": "Er is een fout opgetreden."})
                continue

            # Build awareness entry
            entry = {
                "user_id": user_id,
                "type": msg_type,
                "payload": payload,
                "updated_at": _epoch_ms(),
            }

            # Write to Redis hash + set TTL on the whole key
            entry_json = json.dumps(entry, separators=(",", ":"))
            pipe = redis.pipeline()
            pipe.hset(awareness_key, user_id, entry_json)
            pipe.expire(awareness_key, _AWARENESS_TTL_SECONDS)
            await pipe.execute()

            await websocket.send_json({"type": "ack", "ts": entry["updated_at"]})

    except WebSocketDisconnect:
        logger.info(
            "awareness_ws_disconnect: tenant=%s workflow=%s user=%s",
            tenant_id,
            workflow_id,
            user_id,
        )
    except Exception as exc:
        logger.warning(
            "awareness_ws_error: tenant=%s workflow=%s user=%s %s: %s",
            tenant_id,
            workflow_id,
            user_id,
            type(exc).__name__,
            exc,
        )
        try:
            await websocket.send_json({"type": "error", "message": "Internal server error"})
        except Exception:
            pass
    finally:
        # Remove user's awareness entry on disconnect
        try:
            await redis.hdel(awareness_key, user_id)  # pyright: ignore
            logger.info(
                "awareness_ws_cleanup: removed user=%s from %s",
                user_id,
                awareness_key,
            )
        except Exception as exc:
            logger.warning(
                "awareness_ws_cleanup_failed: key=%s user=%s %s: %s",
                awareness_key,
                user_id,
                type(exc).__name__,
                exc,
            )

        # Close Redis connection to prevent resource leaks
        try:
            await redis.aclose()  # type: ignore[attr-defined]  # pyright: ignore[reportAttributeAccessIssue]
        except Exception:
            pass

        # Disconnect from auth tracker
        _auth.disconnect(user_id)
        await _close_ws(websocket, 1000, "")


def _epoch_ms() -> int:
    """Current UTC timestamp in milliseconds."""
    return int(time.time() * 1000)
