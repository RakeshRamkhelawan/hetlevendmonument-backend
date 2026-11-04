"""
Redis-backed Conversation Memory for CVA

Provides tenant-isolated conversation history with TTL.
Security: Uses json for serialization/deserialization. Never uses eval().
"""

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ConversationMemory:
    """Redis-backed conversation history with TTL support.

    Keys are tenant-isolated: assistant:history:{tenant_id}:{user_id}
    """

    def __init__(self, redis_client: Any, tenant_id: int) -> None:  # TODO(TYPE): replace Any with concrete type
        self.redis = redis_client
        self.tenant_id = tenant_id
        self.ttl = 3600  # 1 hour default

    def _get_key(self, user_id: int) -> str:
        """Generate tenant-isolated Redis key"""
        return f"assistant:history:{self.tenant_id}:{user_id}"

    async def add_message(self, user_id: int, message: dict[str, Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        """Add a message to the user's conversation history"""
        key = self._get_key(user_id)
        message_json = json.dumps(message)

        # PUSH to list and set TTL
        await self.redis.rpush(key, message_json)
        await self.redis.expire(key, self.ttl)

        # Keep only last 50 messages to prevent unbounded growth
        await self.redis.ltrim(key, -50, -1)

    async def get_history(self, user_id: int, limit: int | None = None) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Retrieve conversation history for the user"""
        key = self._get_key(user_id)

        # Range logic for limits
        start = -limit if limit else 0
        end = -1

        history_json = await self.redis.lrange(key, start, end)

        # Deserialization with security check (json.loads only)
        history: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for item in history_json:
            try:
                history.append(json.loads(item))
            except (json.JSONDecodeError, TypeError) as e:
                logger.error(f"Failed to deserialize history item: {e}")

        return history

    async def clear(self, user_id: int) -> None:
        """Clear conversation history for the user"""
        key = self._get_key(user_id)
        await self.redis.delete(key)
