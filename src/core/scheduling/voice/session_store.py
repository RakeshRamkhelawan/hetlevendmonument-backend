"""
Redis-based session store for voice interactions.

Replaces in-memory dictionary with Redis for:
- Distributed session storage across multiple servers
- Automatic TTL/expiration
- Persistence across restarts
- Scalability
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional, cast

from src.core.typing import AsyncRedisClient, create_async_redis_client

from src.core.scheduling.voice.intents import VoiceContext

logger = logging.getLogger(__name__)


class VoiceSessionStore:
    """
    Redis-backed session store for voice interactions.

    Sessions expire after 30 minutes of inactivity by default.
    """

    DEFAULT_TTL = 1800  # 30 minutes in seconds
    KEY_PREFIX = "voice:session:"

    def __init__(self, redis_client: AsyncRedisClient | None = None, ttl: int = 3600) -> None:
        """
        Initialize session store.

        Args:
            redis_client: Optional Redis client. If not provided,
                         will create from environment variables.
            ttl: Time-to-live in seconds (default: 3600 = 1 hour)
        """
        self._redis = redis_client
        self._local_fallback: dict[str, dict[str, Any]] = {}  # TODO(TYPE): replace Any with concrete type
        self._use_local = redis_client is None
        self._ttl = ttl

    async def _get_redis(self) -> AsyncRedisClient | None:
        """Get or create Redis connection."""
        if self._use_local:
            return None

        if self._redis is None:
            import os

            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
            try:
                self._redis = await create_async_redis_client(redis_url, decode_responses=True)
                await self._redis.ping()
                logger.info("VoiceSessionStore connected to Redis")
            except Exception as exc:
                logger.warning(f"Redis unavailable, using local fallback: {exc}")
                self._use_local = True
                return None

        return self._redis

    def _serialize_context(self, context: VoiceContext) -> str:
        """Serialize VoiceContext to JSON string."""
        # Handle dict input (from tests or cached data)
        if isinstance(context, dict):
            return json.dumps(context)

        return json.dumps(
            {
                "user_id": context.user_id,
                "tenant_id": context.tenant_id,
                "timezone": context.timezone,
                "conversation_history": context.conversation_history,
                "pending_intent": (
                    {
                        "intent_type": (
                            context.pending_intent.intent_type.value
                            if context.pending_intent
                            else None
                        ),
                        "confidence": (
                            context.pending_intent.confidence if context.pending_intent else None
                        ),
                        "participants": (
                            context.pending_intent.participants if context.pending_intent else []
                        ),
                        "date_expression": (
                            context.pending_intent.date_expression
                            if context.pending_intent
                            else None
                        ),
                        "time_expression": (
                            context.pending_intent.time_expression
                            if context.pending_intent
                            else None
                        ),
                        "duration_minutes": (
                            context.pending_intent.duration_minutes
                            if context.pending_intent
                            else None
                        ),
                        "meeting_title": (
                            context.pending_intent.meeting_title if context.pending_intent else None
                        ),
                    }
                    if context.pending_intent
                    else None
                ),
            }
        )

    def _deserialize_context(self, data: dict[str, Any]) -> VoiceContext:  # TODO(TYPE): replace Any with concrete type
        """Deserialize JSON dict to VoiceContext."""
        from src.core.scheduling.voice.intents import VoiceIntent, VoiceIntentType

        context = VoiceContext(
            user_id=data["user_id"],
            tenant_id=data["tenant_id"],
            timezone=data.get("timezone", "UTC"),
            conversation_history=data.get("conversation_history", []),
        )

        # Restore pending intent if present
        pending_data = data.get("pending_intent")
        if pending_data and pending_data.get("intent_type"):
            context.pending_intent = VoiceIntent(
                intent_type=VoiceIntentType(pending_data["intent_type"]),
                confidence=pending_data.get("confidence", 0.0),
                participants=pending_data.get("participants", []),
                date_expression=pending_data.get("date_expression"),
                time_expression=pending_data.get("time_expression"),
                duration_minutes=pending_data.get("duration_minutes"),
                meeting_title=pending_data.get("meeting_title"),
            )

        return context

    async def get(self, session_id: str) -> VoiceContext | None:
        """
        Retrieve session by ID.

        Args:
            session_id: The session identifier

        Returns:
            VoiceContext if found and not expired, None otherwise
        """
        redis_client = await self._get_redis()

        if redis_client:
            try:
                key = f"{self.KEY_PREFIX}{session_id}"
                data = await redis_client.get(key)
                if data:
                    # Refresh TTL on access
                    await redis_client.expire(key, self.DEFAULT_TTL)
                    return self._deserialize_context(json.loads(data))
                return None
            except Exception as exc:
                logger.error(f"Redis get error: {exc}")
                # Fall through to local

        # Local fallback
        if session_id in self._local_fallback:
            return self._deserialize_context(self._local_fallback[session_id])
        return None

    async def set(
        self,
        session_id: str,
        context: VoiceContext,
        ttl: int | None = None,
    ) -> None:
        """
        Store session with optional TTL.

        Args:
            session_id: The session identifier
            context: VoiceContext to store
            ttl: Time-to-live in seconds (default: 1800)
        """
        ttl = ttl or self.DEFAULT_TTL
        redis_client = await self._get_redis()

        if redis_client:
            try:
                key = f"{self.KEY_PREFIX}{session_id}"
                data = self._serialize_context(context)
                await redis_client.setex(key, ttl, data)
                return
            except Exception as exc:
                logger.error(f"Redis set error: {exc}")
                # Fall through to local

        # Local fallback
        self._local_fallback[session_id] = json.loads(self._serialize_context(context))

    async def delete(self, session_id: str) -> bool:
        """
        Delete session by ID.

        Args:
            session_id: The session identifier

        Returns:
            True if session existed and was deleted, False otherwise
        """
        redis_client = await self._get_redis()

        if redis_client:
            try:
                key = f"{self.KEY_PREFIX}{session_id}"
                return (await redis_client.delete(key)) > 0
            except Exception as exc:
                logger.error(f"Redis delete error: {exc}")

        # Local fallback
        if session_id in self._local_fallback:
            del self._local_fallback[session_id]
            return True
        return False

    async def exists(self, session_id: str) -> bool:
        """Check if session exists."""
        redis_client = await self._get_redis()

        if redis_client:
            try:
                key = f"{self.KEY_PREFIX}{session_id}"
                return (await redis_client.exists(key)) > 0
            except Exception as exc:
                logger.error(f"Redis exists error: {exc}")

        return session_id in self._local_fallback

    async def touch(self, session_id: str) -> bool:
        """
        Refresh session TTL without reading.

        Args:
            session_id: The session identifier

        Returns:
            True if session exists and was touched, False otherwise
        """
        redis_client = await self._get_redis()

        if redis_client:
            try:
                key = f"{self.KEY_PREFIX}{session_id}"
                return bool(await redis_client.expire(key, self.DEFAULT_TTL))
            except Exception as exc:
                logger.error(f"Redis touch error: {exc}")

        # Local fallback - no TTL support, just check existence
        return session_id in self._local_fallback

    async def cleanup_expired(self) -> int:
        """
        Clean up expired sessions.

        For Redis, this is automatic. For local fallback,
        this would need manual implementation.

        Returns:
            Number of sessions cleaned up
        """
        # Redis handles expiration automatically
        # Local fallback would need a background task
        if self._use_local:
            logger.warning("Local fallback does not support automatic cleanup")
        return 0


# Global instance for dependency injection
_session_store: VoiceSessionStore | None = None


def get_session_store() -> VoiceSessionStore:
    """Get or create global session store instance."""
    global _session_store
    if _session_store is None:
        _session_store = VoiceSessionStore()
    return _session_store


def init_session_store(redis_client: AsyncRedisClient) -> VoiceSessionStore:
    """Initialize session store with Redis client."""
    global _session_store
    _session_store = VoiceSessionStore(redis_client)
    return _session_store
