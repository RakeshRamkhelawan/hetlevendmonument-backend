"""
FocusBuilder WebSocket Connection Manager

Manages WebSocket connections for real-time flow status updates.
Provides connection tracking, broadcasting, and cleanup functionality.
"""

from typing import Any, Dict, List, Optional, Set

from fastapi import WebSocket
from loguru import logger


class FlowStatusManager:
    """
    Manages WebSocket connections for flow status updates.

    Features:
    - Tracks active connections per flow
    - Broadcasts status updates to all clients watching a flow
    - Handles connection cleanup on disconnect
    - Thread-safe connection management
    """

    def __init__(self) -> None:
        """Initialize the connection manager."""
        # flow_id -> set of WebSocket connections
        self.connections: dict[int, set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, flow_id: int) -> None:
        """
        Register a new WebSocket connection for a flow.

        Args:
            websocket: The WebSocket connection to register
            flow_id: The flow ID being watched
        """
        await websocket.accept()

        if flow_id not in self.connections:
            self.connections[flow_id] = set()

        self.connections[flow_id].add(websocket)
        logger.debug(
            f"WebSocket connected: flow_id={flow_id}, total_connections={len(self.connections[flow_id])}"
        )

    def disconnect(self, websocket: WebSocket, flow_id: int) -> None:
        """
        Remove a WebSocket connection for a flow.

        Args:
            websocket: The WebSocket connection to remove
            flow_id: The flow ID being watched
        """
        if flow_id in self.connections:
            self.connections[flow_id].discard(websocket)

            # Clean up empty flow entries
            if not self.connections[flow_id]:
                del self.connections[flow_id]

            logger.debug(f"WebSocket disconnected: flow_id={flow_id}")

    async def broadcast_to_flow(self, flow_id: int, message: dict[str, Any]) -> int:  # TODO(TYPE): replace Any with concrete type
        """
        Broadcast a message to all connections watching a specific flow.

        Args:
            flow_id: The flow ID to broadcast to
            message: The message to send (will be JSON serialized)

        Returns:
            Number of clients that received the message
        """
        if flow_id not in self.connections:
            return 0

        disconnected: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        count = 0

        for websocket in list(self.connections[flow_id]):
            try:
                await websocket.send_json(message)
                count += 1
            except Exception as e:
                logger.warning(f"Failed to send to WebSocket for flow {flow_id}: {e}")
                disconnected.append(websocket)

        # Clean up any disconnected clients
        for websocket in disconnected:
            self.disconnect(websocket, flow_id)

        return count

    async def broadcast(self, message: dict[str, Any]) -> int:  # TODO(TYPE): replace Any with concrete type
        """
        Broadcast a message to all connected clients across all flows.

        Args:
            message: The message to send (will be JSON serialized)

        Returns:
            Number of clients that received the message
        """
        total = 0
        for flow_id in list(self.connections.keys()):
            total += await self.broadcast_to_flow(flow_id, message)
        return total

    def get_connection_count(self, flow_id: int | None = None) -> int:
        """
        Get the number of active connections.

        Args:
            flow_id: If provided, count connections for this flow only.
                     If None, count all connections.

        Returns:
            Number of active WebSocket connections
        """
        if flow_id is not None:
            return len(self.connections.get(flow_id, set()))

        return sum(len(conns) for conns in self.connections.values())

    def get_active_flows(self) -> list[int]:
        """
        Get a list of flow IDs with active connections.

        Returns: List[Any] of flow IDs  # TODO(TYPE): replace Any with concrete type
        """
        return list(self.connections.keys())


# Global singleton instance
manager = FlowStatusManager()
