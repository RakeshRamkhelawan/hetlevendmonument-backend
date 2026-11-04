"""
WebSocket Manager for Real-time Communication
Handles WebSocket connections and broadcasting for the Mission Control interface
"""

import json
import logging
from datetime import datetime, timezone
from typing import TypedDict

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class _ConnectionMetadata(TypedDict):
    """Internal runtime metadata tracked per active WebSocket connection."""

    connected_at: datetime
    messages_sent: int
    last_activity: datetime


class ConnectionMetadata(TypedDict):
    """Serialized metadata returned via connection stats."""

    connected_at: str
    messages_sent: int
    last_activity: str


class ConnectionStats(TypedDict):
    """Aggregated connection statistics returned by get_connection_stats."""

    total_connections: int
    active_connections: int
    total_messages_sent: int
    connections_metadata: list[ConnectionMetadata]


class WebSocketManager:
    """Manages WebSocket connections and message broadcasting"""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []
        self.connection_metadata: dict[WebSocket, _ConnectionMetadata] = {}

    async def connect(self, websocket: WebSocket) -> None:
        """Accept WebSocket connection"""
        logger.info("COPILOT_DEBUG: WS Manager connect called")
        await websocket.accept()
        logger.info("COPILOT_DEBUG: WS Manager accepted")
        self.active_connections.append(websocket)
        self.connection_metadata[websocket] = {
            "connected_at": datetime.now(timezone.utc),
            "messages_sent": 0,
            "last_activity": datetime.now(timezone.utc),
        }

        logger.info(f"WebSocket connected. Total connections: {len(self.active_connections)}")

        # Send welcome message
        await self.send_personal_message(
            {
                "type": "connection_established",
                "message": "Connected to Sanskriti Setu",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            websocket,
        )

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove WebSocket connection"""
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            self.connection_metadata.pop(websocket, None)
            logger.info(
                f"WebSocket disconnected. Total connections: {len(self.active_connections)}"
            )

    async def send_personal_message(self, message: dict[str, object], websocket: WebSocket) -> None:
        """Send message to specific WebSocket connection"""
        try:
            await websocket.send_text(json.dumps(message))

            # Update metadata
            if websocket in self.connection_metadata:
                metadata: _ConnectionMetadata = self.connection_metadata[websocket]
                metadata["messages_sent"] += 1
                metadata["last_activity"] = datetime.now(timezone.utc)

        except Exception as e:
            logger.error(f"Failed to send personal message: {e}")
            self.disconnect(websocket)

    async def broadcast(self, message: dict[str, object]) -> None:
        """Broadcast message to all connected clients"""
        if not self.active_connections:
            return

        # Add timestamp to message
        message["timestamp"] = datetime.now(timezone.utc).isoformat()

        message_text: str = json.dumps(message)
        disconnected_sockets: list[WebSocket] = []
        for connection in self.active_connections:
            try:
                await connection.send_text(message_text)

                # Update metadata
                if connection in self.connection_metadata:
                    metadata: _ConnectionMetadata = self.connection_metadata[connection]
                    metadata["messages_sent"] += 1
                    metadata["last_activity"] = datetime.now(timezone.utc)

            except Exception as e:
                logger.error(f"Failed to send broadcast message: {e}")
                disconnected_sockets.append(connection)

        # Clean up disconnected sockets
        for socket in disconnected_sockets:
            self.disconnect(socket)

        logger.info(f"Broadcasted message to {len(self.active_connections)} connections")

    async def broadcast_system_event(self, event_type: str, data: dict[str, object]) -> None:
        """Broadcast system event with standardized format"""
        await self.broadcast(
            {
                "type": "system_event",
                "event_type": event_type,
                "data": data,
                "source": "system",
            }
        )

    async def broadcast_task_update(
        self, task_id: str, status: str, data: dict[str, object] | None = None
    ) -> None:
        """Broadcast task status update"""
        await self.broadcast(
            {
                "type": "task_update",
                "task_id": task_id,
                "status": status,
                "data": data or {},
                "source": "task_manager",
            }
        )

    async def broadcast_agent_status(self, agent_id: str, status: dict[str, object]) -> None:
        """Broadcast agent status update"""
        await self.broadcast(
            {
                "type": "agent_status",
                "agent_id": agent_id,
                "status": status,
                "source": "agent_manager",
            }
        )

    def get_connection_stats(self) -> ConnectionStats:
        """Get connection statistics"""
        if not self.active_connections:
            return {
                "total_connections": 0,
                "active_connections": 0,
                "total_messages_sent": 0,
                "connections_metadata": [],
            }

        total_messages = sum(
            metadata.get("messages_sent", 0) for metadata in self.connection_metadata.values()
        )

        connections_metadata: list[ConnectionMetadata] = [
            {
                "connected_at": metadata["connected_at"].isoformat(),
                "messages_sent": metadata["messages_sent"],
                "last_activity": metadata["last_activity"].isoformat(),
            }
            for metadata in self.connection_metadata.values()
        ]

        return ConnectionStats(
            total_connections=len(self.active_connections),
            active_connections=len(self.active_connections),
            total_messages_sent=total_messages,
            connections_metadata=connections_metadata,
        )

    async def ping_all_connections(self) -> None:
        """Send ping to all connections to keep them alive"""
        await self.broadcast({"type": "ping", "message": "keep_alive"})
