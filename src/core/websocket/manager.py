"""
WebSocket Connection Manager for Real-time Communication

Provides connection management for multiple channels/rooms with
JWT authentication support and tenant isolation.
"""

import asyncio
from collections import defaultdict
from collections.abc import Mapping
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, cast

from fastapi import WebSocket, status
from starlette.websockets import WebSocketState

from src.core.auth.types import VerifiedJWTPayload

logger = logging.getLogger(__name__)


@dataclass
class ChannelConnection:
    """WebSocket connection within a channel."""

    websocket: WebSocket
    channel: str
    user_id: str | None = None
    # None = bij geen enkele tenant. Hier stond `= 1`: een verbinding zonder token hoorde dan
    # standaard bij tenant 1 en kreeg elke `broadcast_to_tenant(1)` te zien (2026-10-05).
    tenant_id: int | None = None
    connected_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )

    def __hash__(self) -> int:
        return id(self)

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ChannelConnection):
            return id(self) == id(other)
        return NotImplemented


def _tenant_uit_token(payload: VerifiedJWTPayload) -> int | None:
    """De tenant uit de claim, of None als die ontbreekt of geen positief geheel getal is."""
    from src.core.auth.websocket_auth import tenant_from_claim

    return tenant_from_claim(payload.get("tenant_id"))


class ConnectionManager:
    """
    Manages WebSocket connections across multiple channels/rooms.

    Features:
    - Multi-channel support (rooms/topics)
    - JWT authentication integration
    - Tenant isolation
    - Broadcast to channel or all connections
    - Connection tracking and metadata
    """

    def __init__(
        self, redis_client: Any | None = None  # TODO(TYPE): replace Any with concrete type
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        # channel -> set of connections
        self._channels: dict[str, set[ChannelConnection]] = {}
        # user_id -> set of connections (for user-specific messaging)
        self._user_connections: dict[str, set[ChannelConnection]] = {}
        # All active connections
        self._all_connections: set[ChannelConnection] = set()

        # Redis pub/sub subscriptions for proactive signals
        self._subscriptions: dict[int, list[Any]] = defaultdict(  # TODO(TYPE): replace Any with concrete type
            list
        )  # TODO(TYPE): replace Any with concrete type
        self._redis = redis_client
        self._listener_tasks: dict[int, asyncio.Task[None]] = {}

    async def connect(
        self,
        websocket: WebSocket,
        channel: str,
        token: str | None = None,
        require_auth: bool = True,
    ) -> ChannelConnection | None:
        """
        Connect a WebSocket to a channel.

        Args:
            websocket: The WebSocket connection
            channel: Channel/room name to join
            token: JWT token; laat leeg zodat de token uit de websocket zelf komt
                (cookie, Sec-WebSocket-Protocol subprotocol of Authorization-header)
            require_auth: Whether authentication is required

        Returns:
            ChannelConnection if successful, None if auth failed
        """
        user_id: str | None = None
        tenant_id: int | None = None

        # SEC-AGT-004: de endpoints hadden hiervoor een `token: str = Query(...)`
        # parameter, waardoor het JWT in de URL belandde (en dus in access logs,
        # browsergeschiedenis, proxy logs en de Referer-header). De extractie gebeurt nu
        # hier -- de manager heeft al een auth-afhankelijkheid, dus dit voegt geen nieuwe
        # architectuurrand toe aan core_api (DSM fan-out-budget). Afgedwongen door
        # tests/architecture/test_websocket_no_query_param_token.py.
        if token is None:
            from src.core.auth.websocket_auth import WebSocketAuthenticator

            token = WebSocketAuthenticator().extract_token(websocket)

        # Authenticate if token provided or required
        if token or require_auth:
            from src.core.auth.jwt_handler import jwt_handler

            if token:
                payload: VerifiedJWTPayload | None = jwt_handler.verify_token(token)
                if payload:
                    tenant_id = _tenant_uit_token(payload)
                    if tenant_id is None:
                        # Nooit een standaardtenant kiezen. Hier stond
                        # `int(payload.get("tenant_id", 1))`: een geldig token zonder tenant
                        # kwam binnen als tenant 1 (acceptant scenario 5, 2026-10-05).
                        logger.warning("WebSocket refused: token has no usable tenant_id claim")
                        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                        return None
                    user_id = str(payload.get("sub") or payload.get("user_id", ""))
                    from src.core.auth.websocket_auth import token_mag_op_een_websocket

                    # Geen portaaltoken, account ingeschakeld (uitgeschakeld is uitgeschakeld).
                    if not await token_mag_op_een_websocket(cast(Mapping[str, object], payload)):
                        logger.warning("WebSocket refused: token not allowed on a websocket")
                        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                        return None
                elif require_auth:
                    await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                    return None
            elif require_auth:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
                return None

        # Exactly one accept per socket: get_ws_user / WebSocketAuthenticator.authenticate
        # already accepts, and a second accept raises a RuntimeError in Starlette that
        # closed the HITL socket right after it opened (meetlat scenario 5).
        if websocket.client_state == WebSocketState.CONNECTING:
            await websocket.accept()

        # Create channel connection
        conn = ChannelConnection(
            websocket=websocket,
            channel=channel,
            user_id=user_id,
            tenant_id=tenant_id,
        )

        # Add to channel
        if channel not in self._channels:
            self._channels[channel] = set()
        self._channels[channel].add(conn)

        # Add to user connections if authenticated
        if user_id:
            if user_id not in self._user_connections:
                self._user_connections[user_id] = set()
            self._user_connections[user_id].add(conn)

        # Add to all connections
        self._all_connections.add(conn)

        logger.info(
            f"WebSocket connected: channel={channel}, user={user_id}, "
            f"tenant={tenant_id}, total={len(self._all_connections)}"
        )

        # Send connection confirmation
        await self.send_to_connection(
            conn,
            {
                "type": "connected",
                "channel": channel,
                "authenticated": user_id is not None,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

        return conn

    def disconnect(
        self, user_id: Any, websocket: Any | None = None  # TODO(TYPE): replace Any with concrete type
    ) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Disconnect a WebSocket connection or unsubscribe a Redis subscriber."""
        if isinstance(user_id, ChannelConnection):
            conn = user_id
            # Remove from channel
            if conn.channel in self._channels:
                self._channels[conn.channel].discard(conn)
                if not self._channels[conn.channel]:
                    del self._channels[conn.channel]

            # Remove from user connections
            if conn.user_id and conn.user_id in self._user_connections:
                self._user_connections[conn.user_id].discard(conn)
                if not self._user_connections[conn.user_id]:
                    del self._user_connections[conn.user_id]

            # Remove from all connections
            self._all_connections.discard(conn)

            logger.info(
                f"WebSocket disconnected: channel={conn.channel}, "
                f"user={conn.user_id}, total={len(self._all_connections)}"
            )
        else:
            norm_user_id: int = cast(
                int,
                int(user_id)
                if isinstance(user_id, (int, str)) and str(user_id).isdigit()
                else user_id,
            )
            conns = self._subscriptions.get(norm_user_id, [])
            if websocket in conns:
                conns.remove(websocket)
            if not conns:
                self._subscriptions.pop(norm_user_id, None)
                task = self._listener_tasks.pop(norm_user_id, None)
                if task:
                    task.cancel()

        class AwaitableNone:
            def __await__(self) -> Any:  # TODO(TYPE): replace Any with concrete type
                if False:
                    yield
                return None

        return AwaitableNone()

    async def subscribe_user(
        self, user_id: Any, websocket: Any  # TODO(TYPE): replace Any with concrete type
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        """Subscribe user to their specific Redis channel for proactive signals."""
        norm_user_id: int = cast(
            int,
            int(user_id) if isinstance(user_id, (int, str)) and str(user_id).isdigit() else user_id,
        )
        self._subscriptions[norm_user_id].append(websocket)
        if norm_user_id not in self._listener_tasks and self._redis:
            task = asyncio.create_task(self._redis_listener(norm_user_id))
            self._listener_tasks[norm_user_id] = task

    async def on_redis_message(
        self, user_id: Any, message: str  # TODO(TYPE): replace Any with concrete type
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        """Forward Redis message to all connected WebSockets for user_id."""
        norm_user_id: int = cast(
            int,
            int(user_id) if isinstance(user_id, (int, str)) and str(user_id).isdigit() else user_id,
        )
        dead: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for ws in list(self._subscriptions.get(norm_user_id, [])):
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(norm_user_id, ws)

    async def _redis_listener(
        self, user_id: Any  # TODO(TYPE): replace Any with concrete type
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        """Background listener task for a specific user_id Redis pub/sub channel."""
        norm_user_id = (
            int(user_id) if isinstance(user_id, (int, str)) and str(user_id).isdigit() else user_id
        )
        if not self._redis:
            return
        channel = f"ws:user:{norm_user_id}"
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(channel)
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = message["data"]
                    if isinstance(data, bytes):
                        data = data.decode("utf-8")
                    await self.on_redis_message(norm_user_id, data)
        except asyncio.CancelledError:
            pass
        finally:
            try:
                await pubsub.unsubscribe(channel)
            except Exception as e:
                logger.warning(f"Error unsubscribing channel {channel}: {e}")
            try:
                await pubsub.close()
            except Exception as e:
                logger.warning(f"Error closing pubsub client: {e}")

    async def send_to_connection(
        self,
        conn: ChannelConnection,
        message: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> bool:  # TODO(TYPE): replace Any with concrete type
        """Send a message to a specific connection."""
        try:
            if conn.websocket.client_state == WebSocketState.DISCONNECTED:
                self.disconnect(conn)
                return False

            await conn.websocket.send_text(json.dumps(message))
            conn.last_activity = datetime.now(timezone.utc)
            return True
        except Exception as e:
            logger.warning(f"Failed to send message: {e}")
            self.disconnect(conn)
            return False

    async def send_to_user(
        self,
        user_id: str,
        message: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> int:  # TODO(TYPE): replace Any with concrete type
        """Send a message to all connections of a user."""
        if user_id not in self._user_connections:
            return 0

        sent_count = 0
        disconnected = []

        for conn in list(self._user_connections[user_id]):
            if await self.send_to_connection(conn, message):
                sent_count += 1
            else:
                disconnected.append(conn)

        # Cleanup disconnected
        for conn in disconnected:
            self.disconnect(conn)

        return sent_count

    async def broadcast_to_channel(
        self,
        channel: str,
        message: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        exclude: set[ChannelConnection] | None = None,
    ) -> int:
        """Broadcast a message to all connections in a channel."""
        if channel not in self._channels:
            return 0

        # Add timestamp
        message["timestamp"] = datetime.now(timezone.utc).isoformat()

        sent_count = 0
        disconnected = []
        exclude_set = exclude or set()

        for conn in list(self._channels[channel]):
            if conn in exclude_set:
                continue

            if await self.send_to_connection(conn, message):
                sent_count += 1
            else:
                disconnected.append(conn)

        # Cleanup disconnected
        for conn in disconnected:
            self.disconnect(conn)

        logger.debug(f"Broadcast to {channel}: {sent_count} connections")
        return sent_count

    async def broadcast_to_tenant(
        self,
        tenant_id: int,
        message: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> int:  # TODO(TYPE): replace Any with concrete type
        """Broadcast a message to all connections of a tenant."""
        message["timestamp"] = datetime.now(timezone.utc).isoformat()

        sent_count = 0
        disconnected = []

        for conn in list(self._all_connections):
            if conn.tenant_id == tenant_id:
                if await self.send_to_connection(conn, message):
                    sent_count += 1
                else:
                    disconnected.append(conn)

        for conn in disconnected:
            self.disconnect(conn)

        return sent_count

    async def broadcast(
        self,
        message: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> int:  # TODO(TYPE): replace Any with concrete type
        """Broadcast a message to all connected clients."""
        message["timestamp"] = datetime.now(timezone.utc).isoformat()

        sent_count = 0
        disconnected = []

        for conn in list(self._all_connections):
            if await self.send_to_connection(conn, message):
                sent_count += 1
            else:
                disconnected.append(conn)

        for conn in disconnected:
            self.disconnect(conn)

        return sent_count

    def get_channel_connections(self, channel: str) -> set[ChannelConnection]:
        """Get all connections in a channel."""
        return self._channels.get(channel, set()).copy()

    def get_user_connections(self, user_id: str) -> set[ChannelConnection]:
        """Get all connections for a user."""
        return self._user_connections.get(user_id, set()).copy()

    def get_channel_count(self, channel: str) -> int:
        """Get number of connections in a channel."""
        return len(self._channels.get(channel, set()))

    def get_user_connection_count(self, user_id: str) -> int:
        """Get number of connections for a user."""
        return len(self._user_connections.get(user_id, set()))

    @property
    def total_connections(self) -> int:
        """Total number of active connections."""
        return len(self._all_connections)

    @property
    def channel_names(self) -> list[str]:
        """List of active channel names."""
        return list(self._channels.keys())

    def get_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get connection statistics."""
        return {
            "total_connections": self.total_connections,
            "channels": {name: len(conns) for name, conns in self._channels.items()},
            "authenticated_users": len(self._user_connections),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


# Global connection manager instance
connection_manager = ConnectionManager()
