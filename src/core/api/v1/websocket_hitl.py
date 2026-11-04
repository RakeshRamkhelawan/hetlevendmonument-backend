"""
WebSocket HITL Endpoint - Real-time Human-in-the-Loop Updates

Provides WebSocket endpoint for real-time HITL ticket updates
with JWT authentication and tenant isolation.
"""

import json
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, status
from loguru import logger
from starlette.websockets import WebSocketState

from src.core.auth.api_deps import AuthenticatedUser, get_ws_user
from src.core.ratelimit.websocket_limiter import WebSocketLimiter
from src.core.websocket.manager import ChannelConnection, connection_manager

router = APIRouter(tags=["HITL WebSocket"])

# Initialize rate limiter (10 requests per 60 seconds for HITL)
limiter = WebSocketLimiter(rate_limit=10, time_window=60)


async def _send_json_message(websocket: WebSocket, message: dict[str, Any]) -> bool:  # TODO(TYPE): replace Any with concrete type
    """Send JSON message to WebSocket."""
    try:
        if websocket.client_state == WebSocketState.DISCONNECTED:
            return False
        await websocket.send_text(json.dumps(message))
        return True
    except Exception as e:
        logger.debug(f"Failed to send WebSocket message: {e}")
        return False


@router.websocket("/ws/hitl/{tenant_id}")
async def websocket_hitl_endpoint(
    websocket: WebSocket,
    tenant_id: int,
    user: AuthenticatedUser = Depends(get_ws_user),
) -> None:
    """
    WebSocket endpoint for HITL real-time updates.

    Connects to channel "hitl:{tenant_id}" for receiving
    real-time notifications about HITL ticket updates.

    **Authentication:**
    - JWT token required in query parameter: ?token=<jwt>
    - User must belong to the requested tenant

    **Protocol:**
    - Server sends: {"type": "connected", "channel": "hitl:1", ...}
    - Client sends: {"type": "ping"} -> Server responds: {"type": "pong", ...}

    **Rate Limiting:**
    - 10 messages per 60 seconds per user

    **Channels:**
    - hitl:{tenant_id} - Broadcasts all HITL ticket updates for tenant

    Args:
        websocket: WebSocket connection
        tenant_id: Tenant ID from URL path (must match user.tenant_id)
        user: Authenticated user from JWT token
    """
    logger.info(f"HITL WebSocket connection attempt: tenant_id={tenant_id}, user={user.user_id}")

    # CRITICAL: Tenant isolation check
    if user.tenant_id != tenant_id:
        logger.warning(
            f"WebSocket connection rejected: tenant mismatch "
            f"(user_tenant={user.tenant_id}, requested={tenant_id})"
        )
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # Connect using the connection manager
    channel_name = f"hitl:{tenant_id}"
    conn: ChannelConnection | None = await connection_manager.connect(
        websocket=websocket,
        channel=channel_name,
        token=None,  # Already authenticated via get_ws_user
        require_auth=False,
    )

    if conn is None:
        logger.error(f"Failed to establish WebSocket connection for user={user.user_id}")
        return

    # Update connection with user info from authenticated user
    conn.user_id = user.user_id
    conn.tenant_id = user.tenant_id

    logger.info(
        f"HITL WebSocket connection established: channel={channel_name}, "
        f"user={user.user_id}, tenant={tenant_id}"
    )

    # Main message loop for ping/pong and command handling
    try:
        while True:
            # Receive message
            raw_message = await websocket.receive_text()
            logger.debug(f"HITL WebSocket received message from user={user.user_id}")

            # Rate limit check
            if not limiter.check_limit(str(user.user_id)):
                await _send_json_message(
                    websocket,
                    {
                        "type": "error",
                        "message": "Rate limit exceeded. Please wait.",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
                continue

            # Input sanitization
            if len(raw_message) > 2000:
                await _send_json_message(
                    websocket,
                    {
                        "type": "error",
                        "message": "Input too long (max 2000 chars).",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
                continue

            # Prevent script injection
            if "<script>" in raw_message.lower():
                await _send_json_message(
                    websocket,
                    {
                        "type": "error",
                        "message": "Invalid input detected.",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
                continue

            # Parse message
            try:
                message = json.loads(raw_message)
            except json.JSONDecodeError:
                logger.debug(f"Received invalid JSON from user={user.user_id}")
                await _send_json_message(
                    websocket,
                    {
                        "type": "error",
                        "message": "Invalid JSON format",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
                continue

            message_type = message.get("type", "").lower()

            # Handle ping/pong keepalive
            if message_type == "ping":
                await _send_json_message(
                    websocket,
                    {
                        "type": "pong",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
                continue

            # Log unhandled message types for debugging
            logger.debug(
                f"Received unhandled message type '{message_type}' from user={user.user_id}"
            )

    except WebSocketDisconnect:
        logger.info(f"HITL WebSocket disconnected: channel={channel_name}, user={user.user_id}")
    except Exception as e:
        logger.error(
            f"HITL WebSocket error: {type(e).__name__}: {e}",
            exc_info=True,
        )
    finally:
        # Clean up connection
        connection_manager.disconnect(conn)
        logger.info(
            f"HITL WebSocket connection closed: channel={channel_name}, user={user.user_id}"
        )
