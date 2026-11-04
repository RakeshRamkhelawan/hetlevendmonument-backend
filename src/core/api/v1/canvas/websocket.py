"""
Canvas WebSocket Handler with Operational Transformation

Real-time collaboration WebSocket for canvas editing.
Uses Operational Transformation for conflict resolution.
"""

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, Set, cast
from uuid import UUID

from fastapi import WebSocket, WebSocketDisconnect
from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.canvas.ot_engine import Operation, OperationType, TransformedOperation, ot_engine
from src.domains.canvas.revision_manager import Revision, RevisionManager
from src.domains.canvas.schemas import (
    BlockSelectMessage,
    CanvasSession,
    CursorMoveMessage,
    OperationAckMessage,
    OperationBroadcastMessage,
    OperationMessage,
    Position,
    PresenceMessage,
    Viewport,
    WSMessageType,
)
from src.domains.canvas.service import CanvasService


class CanvasConnectionManager:
    """
    Manages WebSocket connections for canvas collaboration.

    Features:
    - Multi-user session tracking
    - Cursor position broadcasting
    - Operation broadcasting with OT
    - Presence indicators
    """

    def __init__(self) -> None:
        # canvas_id -> {client_id: WebSocket}
        self.canvas_connections: dict[UUID, dict[str, WebSocket]] = {}

        # canvas_id -> {client_id: CanvasSession}
        self.canvas_sessions: dict[UUID, dict[str, CanvasSession]] = {}

        # client_id -> canvas_id
        self.client_canvas: dict[str, UUID] = {}

        # Revision managers per canvas
        self.revision_managers: dict[UUID, RevisionManager] = {}

    async def connect(
        self,
        websocket: WebSocket,
        canvas_id: UUID,
        client_id: str,
        user_id: UUID,
        user_name: str,
        revision_manager: RevisionManager,
    ) -> None:
        """Accept and register a new WebSocket connection."""
        await websocket.accept()

        # Initialize canvas room if needed
        if canvas_id not in self.canvas_connections:
            self.canvas_connections[canvas_id] = {}
            self.canvas_sessions[canvas_id] = {}

        # Register connection
        self.canvas_connections[canvas_id][client_id] = websocket
        self.client_canvas[client_id] = canvas_id
        self.revision_managers[canvas_id] = revision_manager

        # Register with revision manager
        revision_manager.register_client(client_id, canvas_id)

        # Create session
        session = CanvasSession(
            session_id=client_id,
            user_id=user_id,
            user_name=user_name,
            viewport=Viewport(x=Decimal("0"), y=Decimal("0"), zoom=Decimal("1.0")),
            joined_at=datetime.now(timezone.utc),
        )
        self.canvas_sessions[canvas_id][client_id] = session

        logger.info(f"Client {client_id} joined canvas {canvas_id}")

        # Send current revision to client
        latest_revision = await revision_manager.get_latest_revision(canvas_id)
        await websocket.send_json(
            {
                "type": "init",
                "client_id": "server",
                "revision": latest_revision,
                "message": "Connected to canvas",
            }
        )

        # Broadcast presence to others
        await self.broadcast_presence(canvas_id, exclude_client=client_id)

    def disconnect(self, client_id: str) -> None:
        """Remove a WebSocket connection."""
        canvas_id = self.client_canvas.get(client_id)

        if canvas_id:
            # Unregister from revision manager
            if canvas_id in self.revision_managers:
                self.revision_managers[canvas_id].unregister_client(client_id)

            # Remove from connections
            if canvas_id in self.canvas_connections:
                self.canvas_connections[canvas_id].pop(client_id, None)

                # Clean up empty canvas room
                if not self.canvas_connections[canvas_id]:
                    del self.canvas_connections[canvas_id]
                    del self.canvas_sessions[canvas_id]
                    del self.revision_managers[canvas_id]

            # Remove from sessions
            if canvas_id in self.canvas_sessions:
                self.canvas_sessions[canvas_id].pop(client_id, None)

            # Remove from client mapping
            del self.client_canvas[client_id]

            logger.info(f"Client {client_id} left canvas {canvas_id}")

    async def broadcast_presence(
        self, canvas_id: UUID, exclude_client: str | None = None
    ) -> None:
        """Broadcast presence update to all clients in canvas."""
        if canvas_id not in self.canvas_sessions:
            return

        sessions = list(self.canvas_sessions[canvas_id].values())

        message = PresenceMessage(
            type=WSMessageType.PRESENCE,
            client_id="server",
            sessions=sessions,
        )

        await self.broadcast_to_canvas(
            canvas_id,
            message.model_dump(),
            exclude_client=exclude_client,
        )

    async def broadcast_cursor_move(
        self,
        canvas_id: UUID,
        client_id: str,
        position: Position,
        viewport: Viewport | None = None,
    ) -> None:
        """Broadcast cursor position to other clients."""
        # Update session
        if canvas_id in self.canvas_sessions:
            session = self.canvas_sessions[canvas_id].get(client_id)
            if session:
                session.cursor_position = position
                if viewport:
                    session.viewport = viewport

        # Broadcast to others
        message = CursorMoveMessage(
            type=WSMessageType.CURSOR_MOVE,
            client_id=client_id,
            position=position,
            viewport=viewport,
        )

        await self.broadcast_to_canvas(
            canvas_id,
            message.model_dump(),
            exclude_client=client_id,
        )

    async def broadcast_block_select(
        self,
        canvas_id: UUID,
        client_id: str,
        block_id: UUID | None,
    ) -> None:
        """Broadcast block selection to other clients."""
        # Update session
        if canvas_id in self.canvas_sessions:
            session = self.canvas_sessions[canvas_id].get(client_id)
            if session:
                session.selected_block_id = block_id

        # Broadcast to others
        message = BlockSelectMessage(
            type=WSMessageType.BLOCK_SELECT,
            client_id=client_id,
            block_id=block_id,
        )

        await self.broadcast_to_canvas(
            canvas_id,
            message.model_dump(),
            exclude_client=client_id,
        )

    async def process_operation(
        self,
        canvas_id: UUID,
        client_id: str,
        operation: Operation,
        client_revision: int,
    ) -> None:
        """
        Process an operation with OT.

        This:
        1. Transforms operation against concurrent server operations
        2. Stores the transformed operation
        3. Broadcasts to all clients
        """
        revision_manager = self.revision_managers.get(canvas_id)
        if not revision_manager:
            logger.error(f"No revision manager for canvas {canvas_id}")
            return

        # Process the operation
        new_revision, server_operations = await revision_manager.process_client_operation(
            canvas_id=canvas_id,
            client_id=client_id,
            operation=operation,
            client_revision=client_revision,
        )

        # Send ACK to original client
        ack_message = {
            "type": WSMessageType.OPERATION_ACK,
            "client_id": "server",
            "operation_id": f"{client_id}_{client_revision}",
            "revision": new_revision,
        }

        if client_id in self.canvas_connections.get(canvas_id, {}):
            await self.canvas_connections[canvas_id][client_id].send_json(ack_message)

        # Broadcast to all clients (including sender for consistency)
        broadcast_message = OperationBroadcastMessage(
            type=WSMessageType.OPERATION_BROADCAST,
            client_id=client_id,
            operation_type=operation.type.value,
            target_type="block" if "block" in operation.type.value else "connection",
            target_id=operation.target_id,
            data=operation.data,
            revision=new_revision.revision_number,
        )

        await self.broadcast_to_canvas(
            canvas_id,
            broadcast_message.model_dump(),
        )

        logger.debug(f"Operation processed: revision {new_revision} on canvas {canvas_id}")

    async def send_missed_operations(
        self,
        canvas_id: UUID,
        client_id: str,
        from_revision: int,
    ) -> None:
        """Send operations client missed since last sync."""
        revision_manager = self.revision_managers.get(canvas_id)
        if not revision_manager:
            return

        operations = await revision_manager.get_operations_since(canvas_id, from_revision)

        for revision in operations:
            message = OperationBroadcastMessage(
                type=WSMessageType.OPERATION_BROADCAST,
                client_id=revision.client_id,
                operation_type=revision.operation.type.value,
                target_type="block" if "block" in revision.operation.type.value else "connection",
                target_id=revision.operation.target_id,
                data=revision.operation.data,
                revision=revision.revision_number,
            )

            if client_id in self.canvas_connections.get(canvas_id, {}):
                await self.canvas_connections[canvas_id][client_id].send_json(message.model_dump())

    async def broadcast_to_canvas(
        self,
        canvas_id: UUID,
        message: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        exclude_client: str | None = None,
    ) -> None:
        """Broadcast message to all clients in a canvas."""
        if canvas_id not in self.canvas_connections:
            return

        disconnected: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for client_id, websocket in self.canvas_connections[canvas_id].items():
            if client_id == exclude_client:
                continue

            try:
                await websocket.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send to client {client_id}: {e}")
                disconnected.append(client_id)

        # Clean up disconnected clients
        for client_id in disconnected:
            self.disconnect(client_id)

    def get_active_sessions(self, canvas_id: UUID) -> list[CanvasSession]:
        """Get all active sessions for a canvas."""
        return list(self.canvas_sessions.get(canvas_id, {}).values())

    def get_connection_count(self, canvas_id: UUID) -> int:
        """Get number of active connections for a canvas."""
        return len(self.canvas_connections.get(canvas_id, {}))


# Global connection manager instance
connection_manager = CanvasConnectionManager()


async def handle_canvas_websocket(
    websocket: WebSocket,
    canvas_id: UUID,
    client_id: str,
    user_id: UUID,
    user_name: str,
    db: AsyncSession,
    tenant_id: int,
) -> None:
    """
    Main WebSocket handler for canvas collaboration with OT.

    Message protocol:
    - Client -> Server: {"type": "operation", "revision": N, "operation": {...}}
    - Server -> Client: {"type": "operation_ack", "revision": N}
    - Server -> All: {"type": "operation_broadcast", "revision": N, ...}
    """
    # Check canvas access
    service = CanvasService(db=db, tenant_id=tenant_id, user_id=user_id)

    try:
        canvas = await service.get_canvas(canvas_id)
    except Exception as e:
        logger.warning(f"WebSocket connection rejected for canvas {canvas_id}: {e}")
        await websocket.close(code=4004, reason="Canvas not found or access denied")
        return

    # Create revision manager for this canvas
    revision_manager = RevisionManager(db=db)

    # Register connection
    await connection_manager.connect(
        websocket=websocket,
        canvas_id=canvas_id,
        client_id=client_id,
        user_id=user_id,
        user_name=user_name,
        revision_manager=revision_manager,
    )

    try:
        while True:
            # Receive message
            data = await websocket.receive_text()

            try:
                message_data = json.loads(data)
                message_type = message_data.get("type")

                if message_type == WSMessageType.CURSOR_MOVE:
                    # Handle cursor move
                    pos_data = message_data.get("position", {})
                    position = Position(x=pos_data.get("x", 0), y=pos_data.get("y", 0))

                    viewport_data = message_data.get("viewport")
                    viewport = None
                    if viewport_data:
                        viewport = Viewport(
                            x=viewport_data.get("x", 0),
                            y=viewport_data.get("y", 0),
                            zoom=viewport_data.get("zoom", 1.0),
                        )

                    await connection_manager.broadcast_cursor_move(
                        canvas_id, client_id, position, viewport
                    )

                elif message_type == WSMessageType.BLOCK_SELECT:
                    # Handle block selection
                    block_id = message_data.get("block_id")
                    if block_id:
                        block_id = UUID(block_id)

                    await connection_manager.broadcast_block_select(canvas_id, client_id, block_id)

                elif message_type == WSMessageType.OPERATION:
                    # Handle operation with OT
                    operation = Operation(
                        type=OperationType(message_data.get("operation_type")),
                        target_id=(
                            UUID(message_data["target_id"])
                            if message_data.get("target_id")
                            else None
                        ),
                        data=message_data.get("data", {}),
                    )

                    client_revision = message_data.get("revision", 0)

                    # Process with OT
                    await connection_manager.process_operation(
                        canvas_id, client_id, operation, client_revision
                    )

                elif message_type == "sync_request":
                    # Client requests missed operations
                    from_revision = message_data.get("from_revision", 0)
                    await connection_manager.send_missed_operations(
                        canvas_id, client_id, from_revision
                    )

                else:
                    logger.warning(f"Unknown message type: {message_type}")

            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON received from client {client_id}")
            except Exception as e:
                logger.error(f"Error handling message: {e}")

    except WebSocketDisconnect:
        logger.info(f"Client {client_id} disconnected")
    finally:
        # Cleanup
        connection_manager.disconnect(client_id)

        # Broadcast updated presence
        await connection_manager.broadcast_presence(canvas_id)
