"""Canvas WebSocket sub-router (ADR-033 Laag 1)."""
# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, WebSocket
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.dependencies import get_current_user
from src.core.api.v1.canvas.dependencies import get_db, get_current_tenant_id

canvas_ws_router = APIRouter()


@canvas_ws_router.websocket("/ws/{canvas_id}")
async def canvas_websocket_endpoint(
    websocket: WebSocket,
    canvas_id: UUID,
    client_id: str = Query(..., description="Unique client ID"),
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(get_current_tenant_id),
    current_user: Any = Depends(get_current_user),  # TODO(TYPE): replace Any with concrete type
) -> None:
    """
    WebSocket endpoint for real-time canvas collaboration.

    Features:
    - Multi-user cursor tracking
    - Block selection sync
    - Operational Transformation for conflict resolution
    - Live presence indicators

    Connection URL: /api/v1/canvas/ws/{canvas_id}?client_id={unique_id}
    """
    from src.core.api.v1.canvas.websocket import handle_canvas_websocket

    user_name = f"User {current_user.id}"
    await handle_canvas_websocket(
        websocket=websocket,
        canvas_id=canvas_id,
        client_id=client_id,
        user_id=current_user.id,
        user_name=user_name,
        db=db,
        tenant_id=tenant_id,
    )
