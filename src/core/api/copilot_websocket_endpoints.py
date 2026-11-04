# orphan:exempt reason: nog niet gemigreerd naar v1/; TODO(SP-VOLGENDE): migreer naar v1/<domein>/
"""
AI Copilot WebSocket Endpoints - Stats Only

NOTE: The /ws/copilot/chat handler was REMOVED on 2026-05-24 to resolve a
path-collision with the new Sprint 4 Day 2 implementation in
src/core/copilot/api/chat_websocket.py.

Only /ws/copilot/stats remains here for backwards compatibility with the
dashboard. Migrate that too when the new copilot WebSocket protocol is
stable.
"""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends

from src.core.api.websocket_manager import WebSocketManager
from src.core.auth.api_deps import websocket_auth, get_current_user_ws
from src.core.shared.production_logging import SafeLogger
from src.core.websocket.manager import ConnectionManager

logger = SafeLogger(__name__)

# Initialize router and WebSocket manager
router = APIRouter()
_ws_manager: WebSocketManager | None = None


def get_ws_manager() -> WebSocketManager:
    """Lazy factory for WebSocketManager."""
    global _ws_manager
    if _ws_manager is None:
        _ws_manager = WebSocketManager()
    return _ws_manager


def get_connection_manager() -> ConnectionManager:
    """Dependency helper to get the connection manager."""
    from src.core.websocket.manager import connection_manager

    return connection_manager


def __getattr__(name: str) -> Any:  # TODO(TYPE): replace with concrete type
    """Backwards compatibility: allow external code to access ws_manager."""
    if name == "ws_manager":
        return get_ws_manager()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ============================================================================
# WEBSOCKET COPILOT ENDPOINTS
# ============================================================================
#
# /ws/copilot/chat moved to src/core/copilot/api/chat_websocket.py (Sprint 4 Day 2).
# This file now only hosts /ws/copilot/stats.


@router.websocket("/ws/copilot/stats")
async def copilot_stats_websocket(websocket: WebSocket) -> None:
    logger.info("COPILOT_DEBUG: Stats WS Request")
    """
    WebSocket endpoint for real-time copilot statistics
    Broadcasts connection stats every 5 seconds
    """
    await get_ws_manager().connect(websocket)
    stats_user = await websocket_auth.authenticate_connected_user(websocket)
    if not stats_user:
        get_ws_manager().disconnect(websocket)
        return

    try:
        import asyncio

        while True:
            # Send stats
            stats = get_ws_manager().get_connection_stats()
            await websocket.send_json(
                {
                    "type": "stats",
                    "data": stats,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )

            # Wait 5 seconds
            await asyncio.sleep(5)

    except WebSocketDisconnect:
        get_ws_manager().disconnect(websocket)


@router.websocket("/ws/copilot/signals")
async def copilot_signals_websocket(
    websocket: WebSocket,
    current_user: Any = Depends(get_current_user_ws),  # TODO(TYPE): replace Any with concrete type
    connection_manager: ConnectionManager = Depends(get_connection_manager),
) -> None:
    """
    WebSocket endpoint for proactieve signalen (Sprint 5 monitors).
    Subscriber-kant van WSPusher (ADR-008 + ADR-027).
    """
    await websocket.accept()
    user_id = current_user.id
    await connection_manager.subscribe_user(user_id=user_id, websocket=websocket)
    try:
        while True:
            # Houd verbinding open; server pusht via Redis subscriber
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await connection_manager.disconnect(user_id=user_id, websocket=websocket)
