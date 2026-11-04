"""
Session Manager - Redis-backed session management for the agentic system.

Provides:
- Session creation and retrieval
- Message history management
- Session continuity detection
- TTL-based expiration
- Database backup for analytics
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, cast

from src.core.typing import AsyncRedisClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agentic.models import AgentSession, SessionMessage

logger = logging.getLogger(__name__)


@dataclass
class ChatMessage:
    """A single chat message."""

    role: str  # 'user', 'assistant', 'system'
    content: str
    feature_context: str | None = None
    tool_calls: list[dict[str, Any]] | None = None  # TODO(TYPE): replace Any with concrete type
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert to dictionary for serialization."""
        return {
            "role": self.role,
            "content": self.content,
            "feature_context": self.feature_context,
            "tool_calls": self.tool_calls,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> "ChatMessage":  # TODO(TYPE): replace Any with concrete type
        """Create from dictionary."""
        return cls(
            role=data["role"],
            content=data["content"],
            feature_context=data.get("feature_context"),
            tool_calls=data.get("tool_calls"),
            timestamp=(
                datetime.fromisoformat(data["timestamp"])
                if "timestamp" in data
                else datetime.now(timezone.utc)
            ),
            metadata=data.get("metadata"),
        )


@dataclass
class Session:
    """Agent session with message history."""

    id: str
    user_id: int
    tenant_id: int
    current_feature: str | None = None
    messages: list[ChatMessage] = field(default_factory=list)
    metadata: dict[str, Any] = field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert to dictionary for Redis storage."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "current_feature": self.current_feature,
            "messages": [m.to_dict() for m in self.messages],
            "metadata": self.metadata,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> "Session":  # TODO(TYPE): replace Any with concrete type
        """Create from dictionary."""
        return cls(
            id=data["id"],
            user_id=data["user_id"],
            tenant_id=data["tenant_id"],
            current_feature=data.get("current_feature"),
            messages=[ChatMessage.from_dict(m) for m in data.get("messages", [])],
            metadata=data.get("metadata", {}),
            created_at=(
                datetime.fromisoformat(data["created_at"])
                if "created_at" in data
                else datetime.now(timezone.utc)
            ),
            last_activity=(
                datetime.fromisoformat(data["last_activity"])
                if "last_activity" in data
                else datetime.now(timezone.utc)
            ),
        )


class AgenticSessionManager:
    """
    Redis-backed session manager for the agentic system.

    Sessions are stored in Redis with TTL for automatic expiration.
    Database backup is optional for analytics and recovery.
    """

    # Redis key prefixes
    KEY_PREFIX = "agent:session:"
    USER_SESSIONS_PREFIX = "agent:user_sessions:"

    # Default TTL
    DEFAULT_TTL_HOURS = 24
    MAX_MESSAGES_IN_MEMORY = 50

    def __init__(
        self,
        redis_client: AsyncRedisClient,
        ttl_hours: int = DEFAULT_TTL_HOURS,
        enable_db_backup: bool = False,
    ) -> None:
        """
        Initialize session manager.

        Args:
            redis_client: Async Redis client
            ttl_hours: Session TTL in hours
            enable_db_backup: Whether to backup sessions to database
        """
        self.redis = redis_client
        self.ttl = timedelta(hours=ttl_hours)
        self.enable_db_backup = enable_db_backup

    def _session_key(self, session_id: str) -> str:
        """Generate Redis key for a session."""
        return f"{self.KEY_PREFIX}{session_id}"

    def _user_sessions_key(self, user_id: int, tenant_id: int) -> str:
        """Generate Redis key for user's session list."""
        return f"{self.USER_SESSIONS_PREFIX}{tenant_id}:{user_id}"

    async def create_session(
        self,
        user_id: int,
        tenant_id: int,
        initial_feature: str | None = None,
        metadata: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> Session:
        """
        Create a new session.

        Args:
            user_id: User ID
            tenant_id: Tenant ID
            initial_feature: Initial feature context
            metadata: Additional metadata

        Returns:
            Created Session
        """
        session = Session(
            id=str(uuid.uuid4()),
            user_id=user_id,
            tenant_id=tenant_id,
            current_feature=initial_feature,
            metadata=metadata or {},
        )

        # Store in Redis
        await self.redis.setex(
            self._session_key(session.id),
            int(self.ttl.total_seconds()),
            json.dumps(session.to_dict()),
        )

        # Add to user's session list
        await self.redis.sadd(self._user_sessions_key(user_id, tenant_id), session.id)

        logger.info(f"Created session {session.id} for user {user_id}")
        return session

    async def get_session(self, session_id: str) -> Session | None:
        """
        Get a session by ID.

        Args:
            session_id: Session ID

        Returns:
            Session if found, None otherwise
        """
        data = await self.redis.get(self._session_key(session_id))

        if not data:
            return None

        try:
            return Session.from_dict(json.loads(data))
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to parse session {session_id}: {e}")
            return None

    async def update_session(self, session: Session) -> None:
        """
        Update a session in Redis.

        Args:
            session: Session to update
        """
        session.last_activity = datetime.now(timezone.utc)

        await self.redis.setex(
            self._session_key(session.id),
            int(self.ttl.total_seconds()),
            json.dumps(session.to_dict()),
        )

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        feature_context: str | None = None,
        tool_calls: (
            list[dict[str, Any]] | None  # TODO(TYPE): replace Any with concrete type
        ) = None,  # TODO(TYPE): replace Any with concrete type
        metadata: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> Session | None:
        """
        Add a message to a session.

        Args:
            session_id: Session ID
            role: Message role
            content: Message content
            feature_context: Feature context
            tool_calls: Tool calls if any
            metadata: Additional metadata

        Returns:
            Updated session
        """
        session = await self.get_session(session_id)

        if not session:
            logger.warning(f"Session {session_id} not found")
            return None

        message = ChatMessage(
            role=role,
            content=content,
            feature_context=feature_context,
            tool_calls=tool_calls,
            metadata=metadata,
        )

        session.messages.append(message)

        # Update current feature if provided
        if feature_context:
            session.current_feature = feature_context

        # Trim old messages if needed
        if len(session.messages) > self.MAX_MESSAGES_IN_MEMORY:
            session.messages = session.messages[-self.MAX_MESSAGES_IN_MEMORY :]

        await self.update_session(session)
        return session

    async def get_message_history(self, session_id: str, limit: int = 20) -> list[ChatMessage]:
        """
        Get recent message history for a session.

        Args:
            session_id: Session ID
            limit: Maximum messages to return

        Returns: list[Any] of messages (newest last)  # TODO(TYPE): replace Any with concrete type
        """
        session = await self.get_session(session_id)

        if not session:
            return []

        return session.messages[-limit:]

    async def get_context_for_llm(
        self, session_id: str, max_messages: int = 10
    ) -> list[dict[str, str]]:
        """
        Get message history formatted for LLM context.

        Args:
            session_id: Session ID
            max_messages: Maximum messages to include

        Returns: list[Any] of {role, content} dicts for LLM  # TODO(TYPE): replace Any with concrete type
        """
        messages = await self.get_message_history(session_id, max_messages)

        return [
            {"role": m.role, "content": m.content}
            for m in messages
            if m.role in ("user", "assistant")
        ]

    async def check_session_continuity(self, session_id: str, message: str) -> str | None:
        """
        Check if message continues the current session context.

        Args:
            session_id: Session ID
            message: New user message

        Returns:
            Current feature context if continuing, None if context switch detected
        """
        session = await self.get_session(session_id)

        if not session or not session.current_feature:
            return None

        # Check for explicit context switch signals
        context_switch_signals = [
            "switch to",
            "change to",
            "instead",
            "actually",
            "nu wil ik",
            "verander naar",
            "andere functie",
            "laat maar",
            "never mind",
        ]

        message_lower = message.lower()
        for signal in context_switch_signals:
            if signal in message_lower:
                logger.info(f"Context switch detected in session {session_id}")
                return None

        return session.current_feature

    async def delete_session(self, session_id: str) -> bool:
        """
        Delete a session.

        Args:
            session_id: Session ID

        Returns:
            True if deleted, False if not found
        """
        session = await self.get_session(session_id)

        if not session:
            return False

        # Remove from Redis
        await self.redis.delete(self._session_key(session_id))

        # Remove from user's session list
        await self.redis.srem(
            self._user_sessions_key(session.user_id, session.tenant_id), session_id
        )

        logger.info(f"Deleted session {session_id}")
        return True

    async def get_user_sessions(self, user_id: int, tenant_id: int) -> list[str]:
        """
        Get all session IDs for a user.

        Args:
            user_id: User ID
            tenant_id: Tenant ID

        Returns: list[Any] of session IDs  # TODO(TYPE): replace Any with concrete type
        """
        session_ids = await self.redis.smembers(self._user_sessions_key(user_id, tenant_id))
        return [sid.decode() if isinstance(sid, bytes) else sid for sid in session_ids]

    async def backup_to_database(self, session: Session, db: AsyncSession) -> None:
        """
        Backup session to database for analytics.

        Args:
            session: Session to backup
            db: Database session
        """
        if not self.enable_db_backup:
            return

        # Create or update AgentSession
        db_session = AgentSession(
            id=session.id,
            user_id=session.user_id,
            tenant_id=session.tenant_id,
            current_feature=session.current_feature,
            message_count=len(session.messages),
            extra_metadata=session.metadata,  # Map metadata -> extra_metadata
            created_at=session.created_at,
            last_activity_at=session.last_activity,
        )

        db.add(db_session)

        # Add new messages
        for msg in session.messages:
            db_msg = SessionMessage(
                session_id=session.id,
                role=msg.role,
                content=msg.content,
                detected_feature=msg.feature_context,  # Map feature_context -> detected_feature
                tools_used=msg.tool_calls,  # Map tool_calls -> tools_used
                extra_metadata=msg.metadata,  # Map metadata -> extra_metadata
                created_at=msg.timestamp,
            )
            db.add(db_msg)

        await db.commit()
        logger.debug(f"Backed up session {session.id} to database")


# Factory function
def create_session_manager(
    redis_url: str, ttl_hours: int = 24, enable_db_backup: bool = False
) -> AgenticSessionManager:
    """Create a session manager instance."""
    import redis.asyncio as _redis_mod

    redis_client = cast(AsyncRedisClient, _redis_mod.from_url(redis_url))
    return AgenticSessionManager(
        redis_client=redis_client,
        ttl_hours=ttl_hours,
        enable_db_backup=enable_db_backup,
    )
