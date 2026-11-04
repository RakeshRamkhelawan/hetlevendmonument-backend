"""
SC-10.1: WebSocket Notification System
Real-time notifications via WebSocket connections.
"""

import json
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class NotificationType(str, Enum):
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    SYSTEM = "system"


@dataclass
class Notification:
    """Represents a notification message."""

    id: str
    type: NotificationType
    title: str
    message: str
    timestamp: str | None = None
    data: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    read: bool = False

    def __post_init__(self) -> None:
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc).isoformat()
        if self.data is None:
            self.data = {}

    def to_json(self) -> str:
        return json.dumps(asdict(self))


class ConnectionManager:
    """
    Manages WebSocket connections for real-time notifications.
    """

    def __init__(self) -> None:
        # user_id -> set of websocket connections
        self.active_connections: dict[str, set[WebSocket]] = {}
        # tenant_id -> set of user_ids
        self.tenant_users: dict[str, set[str]] = {}
        # Global broadcast connections
        self.global_connections: set[WebSocket] = set()

    async def connect(
        self,
        websocket: WebSocket,
        user_id: str | None = None,
        tenant_id: str | None = None,
    ) -> None:
        """Accept a new WebSocket connection."""
        await websocket.accept()

        if user_id:
            if user_id not in self.active_connections:
                self.active_connections[user_id] = set()
            self.active_connections[user_id].add(websocket)

            if tenant_id:
                if tenant_id not in self.tenant_users:
                    self.tenant_users[tenant_id] = set()
                self.tenant_users[tenant_id].add(user_id)
        else:
            self.global_connections.add(websocket)

        logger.info(f"WebSocket connected: user={user_id}, tenant={tenant_id}")

    def disconnect(self, websocket: WebSocket, user_id: str | None = None) -> None:
        """Remove a WebSocket connection."""
        if user_id and user_id in self.active_connections:
            self.active_connections[user_id].discard(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]

        self.global_connections.discard(websocket)
        logger.info(f"WebSocket disconnected: user={user_id}")

    async def send_to_user(self, user_id: str, notification: Notification) -> int:
        """Send notification to a specific user."""
        sent_count = 0

        if user_id in self.active_connections:
            message = notification.to_json()
            disconnected = set()

            for connection in self.active_connections[user_id]:
                try:
                    await connection.send_text(message)
                    sent_count += 1
                except Exception as e:
                    logger.error(f"Failed to send to user {user_id}: {e}")
                    disconnected.add(connection)

            # Clean up disconnected
            for conn in disconnected:
                self.active_connections[user_id].discard(conn)

        return sent_count

    async def send_to_tenant(self, tenant_id: str, notification: Notification) -> int:
        """Send notification to all users in a tenant."""
        sent_count = 0

        if tenant_id in self.tenant_users:
            for user_id in self.tenant_users[tenant_id]:
                sent_count += await self.send_to_user(user_id, notification)

        return sent_count

    async def broadcast(self, notification: Notification) -> int:
        """Broadcast notification to all connected clients."""
        sent_count = 0
        message = notification.to_json()
        disconnected = set()

        # Send to all user connections
        for user_id, connections in self.active_connections.items():
            for connection in connections:
                try:
                    await connection.send_text(message)
                    sent_count += 1
                except Exception:
                    disconnected.add((user_id, connection))

        # Send to global connections
        for connection in self.global_connections:
            try:
                await connection.send_text(message)
                sent_count += 1
            except Exception:
                pass

        return sent_count

    def get_connected_users(self) -> list[str]:
        """Get list of connected user IDs."""
        return list(self.active_connections.keys())

    def get_connection_count(self) -> int:
        """Get total number of active connections."""
        count = sum(len(conns) for conns in self.active_connections.values())
        count += len(self.global_connections)
        return count


class NotificationService:
    """
    SC-10.1: High-level notification service.

    Provides methods for sending various types of notifications.
    """

    def __init__(self, connection_manager: ConnectionManager | None = None) -> None:
        self.manager = connection_manager or ConnectionManager()
        self._notification_counter = 0

    def _generate_id(self) -> str:
        """Generate unique notification ID."""
        self._notification_counter += 1
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        return f"notif_{timestamp}_{self._notification_counter}"

    async def notify_user(
        self,
        user_id: str,
        title: str,
        message: str,
        type: NotificationType = NotificationType.INFO,
        data: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> bool:
        """Send notification to a user."""
        notification = Notification(
            id=self._generate_id(), type=type, title=title, message=message, data=data
        )

        count = await self.manager.send_to_user(user_id, notification)
        logger.info(f"Notification sent to user {user_id}: {title}")
        return count > 0

    async def notify_tenant(
        self,
        tenant_id: str,
        title: str,
        message: str,
        type: NotificationType = NotificationType.INFO,
    ) -> int:
        """Send notification to all users in a tenant."""
        notification = Notification(id=self._generate_id(), type=type, title=title, message=message)

        count = await self.manager.send_to_tenant(tenant_id, notification)
        logger.info(f"Notification sent to tenant {tenant_id}: {title} ({count} users)")
        return count

    async def broadcast_system(self, title: str, message: str) -> int:
        """Broadcast system-wide notification."""
        notification = Notification(
            id=self._generate_id(),
            type=NotificationType.SYSTEM,
            title=title,
            message=message,
        )

        count = await self.manager.broadcast(notification)
        logger.info(f"System broadcast: {title} ({count} connections)")
        return count

    async def notify_success(self, user_id: str, title: str, message: str) -> bool:
        """Send success notification."""
        return await self.notify_user(user_id, title, message, NotificationType.SUCCESS)

    async def notify_error(self, user_id: str, title: str, message: str) -> bool:
        """Send error notification."""
        return await self.notify_user(user_id, title, message, NotificationType.ERROR)


# Singleton instances
connection_manager = ConnectionManager()
notification_service = NotificationService(connection_manager)
