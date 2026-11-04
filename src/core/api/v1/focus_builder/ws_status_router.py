"""
# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
FocusBuilder WebSocket status sub-router (ADR-033 Laag 1).

Routes:
- WS /flows/{flow_id}/status
"""

from typing import cast

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.v1.focus_builder.shared import WSUser
from src.core.api.v1.focus_builder.dependencies import get_db  # own-domain -- ADR-033
from src.core.api.v1.focus_builder.ws_dependencies import (
    FlowVerifier,
    WebSocketAuthHandler,
    WebSocketManager,
    get_flow_verifier,
    get_ws_auth,
    get_ws_manager,
)
from src.core.middleware.tenant_context import set_tenant_id

ws_status_router = APIRouter()


@ws_status_router.websocket("/flows/{flow_id}/status")
async def flow_status_websocket(
    websocket: WebSocket,
    flow_id: int,
    db: AsyncSession = Depends(get_db),
    manager: WebSocketManager = Depends(get_ws_manager),
    auth_handler: WebSocketAuthHandler = Depends(get_ws_auth),
    flow_verifier: FlowVerifier = Depends(get_flow_verifier),
) -> None:
    """
    WebSocket endpoint for real-time flow status updates.

    Connection:
    - ws://localhost:8000/api/v1/focus-builder/flows/{flow_id}/status

    Authentication: de HTTP-only ``access_token``-cookie.

    SEC-011 introduceerde de cookie als voorkeurspad; SEC-AGT-004 heeft het
    ``?token={jwt}``-alternatief nu volledig verwijderd (2026-07-31) -- zolang het
    naast de cookie bleef bestaan, kon een client alsnog een token in de URL zetten en
    daarmee in access logs, browsergeschiedenis en de Referer-header. De frontend
    (frontend/src/hooks/useFlowStatusWebSocket.ts::buildWebSocketUrl) gebruikte al geen
    token in de URL. Afgedwongen door
    tests/architecture/test_websocket_no_query_param_token.py.
    """
    effective_token = websocket.cookies.get("access_token")

    if not effective_token:
        await websocket.close(code=4001, reason="Missing token")
        logger.warning("ws_status_rejected_no_token flow_id=%s", flow_id)
        return

    try:
        user = cast(WSUser, await auth_handler.validate_token(effective_token))
    except Exception as e:
        await websocket.close(code=4003, reason="Invalid token")
        logger.warning("ws_status_rejected_invalid_token flow_id=%s: %s", flow_id, e, exc_info=True)
        return

    flow_exists = await flow_verifier.flow_exists(flow_id, db, user.tenant_id)
    if not flow_exists:
        await websocket.close(code=4004, reason="Flow not found")
        logger.warning("ws_status_rejected_flow_not_found flow_id=%s user_id=%s", flow_id, user.id)
        return

    set_tenant_id(user.tenant_id)
    await manager.connect(websocket, flow_id)
    logger.info(
        "ws_status_connected flow_id=%s user_id=%s tenant_id=%s",
        flow_id,
        user.id,
        user.tenant_id,
    )

    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")

    except WebSocketDisconnect:
        manager.disconnect(websocket, flow_id)
        logger.info("ws_status_disconnected flow_id=%s user_id=%s", flow_id, user.id)
    except Exception as e:
        logger.error("ws_status_error: %s: %s", type(e).__name__, e, exc_info=True)
        manager.disconnect(websocket, flow_id)
