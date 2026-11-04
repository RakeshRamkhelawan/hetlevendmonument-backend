import json
import logging
from typing import Any

from src.core.typing import AsyncRedisClient

from src.core.config.unified_config import config
from src.core.llm.llm_client import LLMMessage

logger = logging.getLogger(__name__)


class RedisChatHistory:
    """
    Manages chat history using Redis for persistence.
    Key format: "chat_history:{session_id}"
    """

    def __init__(self, session_id: str, ttl_seconds: int = 3600) -> None:
        self.session_id = session_id
        self.ttl_seconds = ttl_seconds
        self.redis: AsyncRedisClient | None = None
        self.key = f"chat_history:{session_id}"

    async def _ensure_redis(self) -> AsyncRedisClient:
        if self.redis is None:
            from src.core.typing import create_async_redis_client
            self.redis = await create_async_redis_client(
                config.redis_url, decode_responses=True
            )
        return self.redis

    async def add_message(self, role: str, content: str) -> None:
        """Append a message to the history list"""
        redis = await self._ensure_redis()
        message = LLMMessage(role=role, content=content)
        # Store as JSON string
        await redis.rpush(self.key, json.dumps({"role": message.role, "content": message.content}))
        # Refresh TTL
        await redis.expire(self.key, self.ttl_seconds)

    async def get_messages(self, limit: int = 20) -> list[LLMMessage]:
        """Get recent messages (up to limit)"""
        redis = await self._ensure_redis()
        # Get all messages
        # LROFL (Last Result of List) - actually Redis lists are 0-indexed
        # range(0, -1) gets everything.
        # But we might want only last N.

        # Determine start index
        total = await redis.llen(self.key)
        start = max(0, total - limit)

        raw_messages = await redis.lrange(self.key, start, -1)
        messages: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for raw in raw_messages:
            try:
                data = json.loads(raw)
                messages.append(LLMMessage(**data))
            except Exception as e:
                logger.error(f"Failed to parse history message: {e}")

        return messages

    async def clear(self) -> None:
        """Clear history for this session"""
        redis = await self._ensure_redis()
        await redis.delete(self.key)

    async def close(self) -> None:
        """Close connection"""
        if self.redis is not None:
            await self.redis.close()
