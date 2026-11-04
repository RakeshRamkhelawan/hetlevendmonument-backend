# orphan:exempt -- legacy shim, superseded by v1/websocket/router.py
import asyncio
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.core.api.setup.app_state import app_state
from src.core.auth.api_deps import WebSocketAuthenticator
from src.core.shared.config import get_feature_flag

_auth = WebSocketAuthenticator()

logger = logging.getLogger(__name__)
router = APIRouter(tags=["WebSockets"])


@router.websocket("/ws/logs")
async def websocket_logs_endpoint(websocket: WebSocket) -> None:
    user = await _auth.authenticate(websocket)
    if not user:
        return
    # Initial logs
    for log_entry in app_state["log_entries"][-50:]:
        await websocket.send_json(log_entry)
    try:
        while True:
            while app_state["log_broadcast_queue"]:
                log_entry = app_state["log_broadcast_queue"].pop(0)
                await websocket.send_json(log_entry)
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    if not get_feature_flag("websocket_updates") or not app_state["websocket_manager"]:
        await websocket.close(code=1000)
        return
    await app_state["websocket_manager"].connect(websocket)
    user = await _auth.authenticate_connected_user(websocket)
    if not user:
        app_state["websocket_manager"].disconnect(websocket)
        return
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "ping":
                await websocket.send_json(
                    {
                        "type": "pong",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                )
    except WebSocketDisconnect:
        app_state["websocket_manager"].disconnect(websocket)
