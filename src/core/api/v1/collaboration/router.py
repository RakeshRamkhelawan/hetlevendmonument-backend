"""
WebSocket endpoint for real-time collaboration.
Feature 3: Multi-user presence and cursor tracking.
"""

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from src.core.auth.api_deps import AuthenticatedUser, get_ws_user
from .dependencies import (
    UserPresence,
    get_collaboration_manager,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["collaboration"])

# Track active connections per workspace
active_connections: dict[str, set[WebSocket]] = {}


async def broadcast_to_workspace(
    workspace_id: str,
    message: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    exclude: WebSocket | None = None,  # TODO(TYPE): replace Any with concrete type
) -> None:
    """Broadcast a message to all connections in a workspace."""
    if workspace_id in active_connections:
        disconnected = set()
        for ws in active_connections[workspace_id]:
            if exclude is not None and ws != exclude:
                try:
                    await ws.send_json(message)
                except Exception:
                    disconnected.add(ws)

        # Clean up disconnected sockets
        for ws in disconnected:
            active_connections[workspace_id].discard(ws)


@router.websocket("/ws/collaborate/{workspace_id}")
async def collaborate_ws(
    websocket: WebSocket,
    workspace_id: str,
    user: AuthenticatedUser = Depends(get_ws_user),
) -> None:
    """
    WebSocket endpoint for real-time collaboration in a workspace.

    Expected message format:
    {
        "type": "join" | "cursor_move" | "tool_select" | "leave",
        "data": { ... }
    }

    For "join":
        data: { "user_id": "...", "display_name": "...", "color": "#hex" }

    For "cursor_move":
        data: { "x": 100.0, "y": 200.0 }

    For "tool_select":
        data: { "tool_id": "..." }
    """
    # Connection already accepted by get_ws_user (WebSocketAuthenticator.authenticate)
    logger.info(f"Collaboration WebSocket connected for workspace: {workspace_id}")

    # Track this connection
    if workspace_id not in active_connections:
        active_connections[workspace_id] = set()
    active_connections[workspace_id].add(websocket)

    collab = await get_collaboration_manager()
    user_id: str | None = None

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            msg_data = data.get("data", {})

            if msg_type == "join":
                user_id = msg_data.get("user_id")
                display_name = msg_data.get("display_name", "Anonymous")
                color = msg_data.get("color", "#3B82F6")

                presence = UserPresence(
                    user_id=user_id or "", display_name=display_name, color=color
                )

                # Join workspace and get current users
                current_users = await collab.join_workspace(workspace_id, presence)

                # Send current users to the joining user
                await websocket.send_json(
                    {
                        "type": "users_list",
                        "data": {uid: vars(u) for uid, u in current_users.items()},
                    }
                )

                # Broadcast join to others
                await broadcast_to_workspace(
                    workspace_id,
                    {"type": "user_joined", "data": vars(presence)},
                    exclude=websocket,
                )

            elif msg_type == "cursor_move" and user_id:
                x = msg_data.get("x", 0)
                y = msg_data.get("y", 0)

                await collab.update_cursor(workspace_id, user_id, x, y)

                # Broadcast to others (not via Redis pubsub for performance, direct WS)
                await broadcast_to_workspace(
                    workspace_id,
                    {
                        "type": "cursor_update",
                        "data": {"user_id": user_id, "x": x, "y": y},
                    },
                    exclude=websocket,
                )

            elif msg_type == "tool_select" and user_id:
                tool_id = msg_data.get("tool_id")

                await collab.update_tool_selection(workspace_id, user_id, tool_id)

                await broadcast_to_workspace(
                    workspace_id,
                    {
                        "type": "tool_selected",
                        "data": {"user_id": user_id, "tool_id": tool_id},
                    },
                    exclude=websocket,
                )

    except WebSocketDisconnect:
        logger.info(
            f"Collaboration WebSocket disconnected for workspace: {workspace_id}, user: {user_id}"
        )
    except Exception as e:
        logger.error(f"Collaboration WebSocket error: {e}")
    finally:
        # Cleanup
        if workspace_id in active_connections:
            active_connections[workspace_id].discard(websocket)
            if not active_connections[workspace_id]:
                del active_connections[workspace_id]

        if user_id:
            await collab.leave_workspace(workspace_id, user_id)
            await broadcast_to_workspace(
                workspace_id, {"type": "user_left", "data": {"user_id": user_id}}
            )
