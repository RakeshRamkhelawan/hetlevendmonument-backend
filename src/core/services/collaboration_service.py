from __future__ import annotations

"""
Real-time Collaboration Service using Redis[Any] Pub/Sub.  # TODO(TYPE): replace Any with concrete type
Feature 3: Multi-user presence and cursor tracking.
"""

import json
import logging
from dataclasses import asdict, dataclass
from typing import Any, Optional
from collections.abc import AsyncGenerator

from src.core.typing import AsyncRedisClient

logger = logging.getLogger(__name__)


@dataclass
class UserPresence:
    """Represents a user's presence in a workspace."""

    user_id: str
    display_name: str
    cursor_x: float | None = None
    cursor_y: float | None = None
    selected_tool: str | None = None
    color: str = "#3B82F6"  # Default blue


class CollaborationManager:
    """
    Manages real-time collaboration state using Redis[Any] Pub/Sub.  # TODO(TYPE): replace Any with concrete type
    Each workspace has its own channel for broadcasting updates.
    """

    def __init__(self) -> None:
        self.redis: AsyncRedisClient | None = None
        self.pubsub: Any | None = None  # TODO(TYPE): replace Any with concrete type
        self._local_presence: dict[
            str, dict[str, UserPresence]
        ] = {}  # workspace_id -> {user_id -> presence}

    async def initialize(self) -> None:
        """Initialize Redis[Any] connection."""
        if self.redis is None:
            from src.core.typing import create_async_redis_client
            from src.core.config.config import get_settings
            settings = get_settings()
            client = await create_async_redis_client(settings.redis_url, decode_responses=True)
            self.redis = client
            self.pubsub = client.pubsub()

    def _channel_name(self, workspace_id: str) -> str:
        """Get the Redis[Any] channel name for a workspace."""
        return f"collab:{workspace_id}"

    def _presence_key(self, workspace_id: str) -> str:
        """Get the Redis[Any] key for workspace presence data."""
        return f"presence:{workspace_id}"

    async def join_workspace(
        self, workspace_id: str, user: UserPresence
    ) -> dict[str, UserPresence]:
        """
        User joins a workspace. Returns current list of users.
        """
        await self.initialize()
        if self.redis is None:
            raise RuntimeError("Redis not available")

        # Store user presence in Redis hash
        presence_key = self._presence_key(workspace_id)
        await self.redis.hset(presence_key, user.user_id, json.dumps(asdict(user)))
        await self.redis.expire(presence_key, 3600)  # 1 hour TTL

        # Publish join event
        await self.publish_event(workspace_id, "join", asdict(user))

        # Return all current users
        return await self.get_workspace_users(workspace_id)

    async def leave_workspace(self, workspace_id: str, user_id: str) -> None:
        """User leaves a workspace."""
        await self.initialize()
        if self.redis is None:
            raise RuntimeError("Redis not available")

        # Remove from Redis
        presence_key = self._presence_key(workspace_id)
        await self.redis.hdel(presence_key, user_id)

        # Publish leave event
        await self.publish_event(workspace_id, "leave", {"user_id": user_id})

    async def update_cursor(self, workspace_id: str, user_id: str, x: float, y: float) -> None:
        """Update user's cursor position."""
        await self.initialize()
        if self.redis is None:
            raise RuntimeError("Redis not available")

        # Update presence in Redis
        presence_key = self._presence_key(workspace_id)
        user_data = await self.redis.hget(presence_key, user_id)

        if user_data:
            presence = json.loads(user_data)
            presence["cursor_x"] = x
            presence["cursor_y"] = y
            await self.redis.hset(presence_key, user_id, json.dumps(presence))

            # Publish cursor update (lightweight event)
            await self.publish_event(
                workspace_id, "cursor_move", {"user_id": user_id, "x": x, "y": y}
            )

    async def update_tool_selection(self, workspace_id: str, user_id: str, tool_id: str) -> None:
        """Update user's selected tool."""
        await self.initialize()
        if self.redis is None:
            raise RuntimeError("Redis not available")

        presence_key = self._presence_key(workspace_id)
        user_data = await self.redis.hget(presence_key, user_id)

        if user_data:
            presence = json.loads(user_data)
            presence["selected_tool"] = tool_id
            await self.redis.hset(presence_key, user_id, json.dumps(presence))

            await self.publish_event(
                workspace_id, "tool_select", {"user_id": user_id, "tool_id": tool_id}
            )

    async def get_workspace_users(self, workspace_id: str) -> dict[str, UserPresence]:
        """Get all users currently in a workspace."""
        await self.initialize()
        if self.redis is None:
            raise RuntimeError("Redis not available")

        presence_key = self._presence_key(workspace_id)
        users_data = await self.redis.hgetall(presence_key)

        result: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for user_id, data in users_data.items():
            try:
                presence_dict = json.loads(data)
                result[user_id] = UserPresence(**presence_dict)
            except Exception as e:
                logger.warning(f"Failed to parse presence data for {user_id}: {e}")

        return result

    async def publish_event(self, workspace_id: str, event_type: str, data: dict[str, Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        """Publish an event to the workspace channel."""
        await self.initialize()
        if self.redis is None:
            raise RuntimeError("Redis not available")

        channel = self._channel_name(workspace_id)
        message = json.dumps({"type": event_type, "data": data})
        await self.redis.publish(channel, message)

    async def subscribe(self, workspace_id: str) -> AsyncGenerator[dict[str, Any], None]:  # TODO(TYPE): replace Any with concrete type
        """Subscribe to a workspace channel. Returns async generator of events."""
        await self.initialize()
        if self.pubsub is None:
            raise RuntimeError("PubSub not available")

        channel = self._channel_name(workspace_id)
        await self.pubsub.subscribe(channel)

        async for message in self.pubsub.listen():
            if message["type"] == "message":
                try:
                    yield json.loads(message["data"])
                except Exception as e:
                    logger.error(f"Failed to parse pubsub message: {e}")

    async def unsubscribe(self, workspace_id: str) -> None:
        """Unsubscribe from a workspace channel."""
        if self.pubsub:
            channel = self._channel_name(workspace_id)
            await self.pubsub.unsubscribe(channel)


# Singleton instance
_collaboration_manager: CollaborationManager | None = None


async def get_collaboration_manager() -> CollaborationManager:
    """Get the singleton CollaborationManager instance."""
    global _collaboration_manager
    if _collaboration_manager is None:
        _collaboration_manager = CollaborationManager()
        await _collaboration_manager.initialize()
    return _collaboration_manager
