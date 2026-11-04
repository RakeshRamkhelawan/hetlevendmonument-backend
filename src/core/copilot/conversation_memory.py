"""
Tenant-scoped, sliding-window conversation memory in Redis.

Per CLAUDE.md M-1 mitigation: hard cap of 20 messages via ltrim.
Key format: copilot:session:{tenant_id}:{session_id} (tenant-keyed).
TTL: 3600 seconds (matching CVA convention).

Per CLAUDE.md regel 10: ASCII-only in source code.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from src.core.typing.redis_protocol import AsyncRedisClient

logger = logging.getLogger(__name__)

MAX_MESSAGES = 20  # CLAUDE.md M-1 mitigation
TTL_SECONDS = 3600


@dataclass(frozen=True)
class ConversationMessage:
    """Single message in a conversation."""

    role: str  # "user" | "assistant" | "system"
    content: str
    timestamp: float

    def to_json(self) -> str:
        return json.dumps(
            {
                "role": self.role,
                "content": self.content,
                "timestamp": self.timestamp,
            }
        )

    @classmethod
    def from_json(cls, raw: str) -> "ConversationMessage":
        data = json.loads(raw)
        return cls(
            role=data["role"],
            content=data["content"],
            timestamp=data["timestamp"],
        )


class ConversationMemory:
    """Tenant-scoped, sliding-window conversation memory in Redis."""

    def __init__(self, redis: AsyncRedisClient) -> None:
        self._redis = redis

    def _key(self, tenant_id: int, session_id: UUID) -> str:
        return f"copilot:session:{tenant_id}:{session_id}"

    def _user_sessions_key(self, tenant_id: int, user_id: int) -> str:
        # GDPR-A17: index a user's copilot sessions so DSAR erasure can target exactly
        # those sessions (the session key itself carries no user_id).
        return f"copilot:user_sessions:{tenant_id}:{user_id}"

    async def add(
        self,
        tenant_id: int,
        session_id: UUID,
        role: str,
        content: str,
        user_id: int | None = None,
    ) -> None:
        key = self._key(tenant_id, session_id)
        msg = ConversationMessage(role=role, content=content, timestamp=time.time())
        await self._redis.rpush(key, msg.to_json())  # pyright: ignore
        await self._redis.ltrim(key, -MAX_MESSAGES, -1)  # pyright: ignore
        await self._redis.expire(key, TTL_SECONDS)
        if user_id is not None:
            index_key = self._user_sessions_key(tenant_id, user_id)
            await self._redis.sadd(index_key, str(session_id))  # pyright: ignore
            await self._redis.expire(index_key, TTL_SECONDS)

    async def get_user_sessions(self, tenant_id: int, user_id: int) -> list[str]:
        """Return the session ids indexed for a user (tenant-scoped)."""
        index_key = self._user_sessions_key(tenant_id, user_id)
        raw = await self._redis.smembers(index_key)  # pyright: ignore
        return [item.decode() if isinstance(item, bytes) else item for item in raw]

    async def clear_user_sessions(self, tenant_id: int, user_id: int) -> int:
        """Delete every copilot session of a user + the index (GDPR-A17 erasure).

        Returns the number of session keys removed. Only touches keys under the given
        tenant_id -- never cross-tenant.
        """
        sessions = await self.get_user_sessions(tenant_id, user_id)
        for sid in sessions:
            # Reuse _key so a future key-format change cannot silently break erasure.
            await self._redis.delete(self._key(tenant_id, UUID(sid)))
        await self._redis.delete(self._user_sessions_key(tenant_id, user_id))
        return len(sessions)

    async def get_history(
        self,
        tenant_id: int,
        session_id: UUID,
    ) -> list[ConversationMessage]:
        key = self._key(tenant_id, session_id)
        raw = await self._redis.lrange(key, 0, -1)  # pyright: ignore
        return [
            ConversationMessage.from_json(item.decode() if isinstance(item, bytes) else item)
            for item in raw
        ]

    async def clear(
        self,
        tenant_id: int,
        session_id: UUID,
    ) -> None:
        await self._redis.delete(self._key(tenant_id, session_id))
