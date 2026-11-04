"""Context management for scheduling conversations.

Tracks conversation state to enable follow-up questions and clarifications.
Supports both in-memory and Redis-backed storage.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Optional, cast

from src.core.scheduling.nlp.entities import EntityType

logger = logging.getLogger(__name__)

# Optional Redis import
try:
    from src.core.typing import create_async_redis_client

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


@dataclass
class ConversationContext:
    """Context for a scheduling conversation.

    Maintains state across multiple turns to handle follow-up questions
    and incomplete information.
    """

    session_id: str
    user_id: str
    tenant_id: int
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Current intent being processed
    current_intent: str | None = None

    # Entities extracted so far
    extracted_entities: dict[EntityType, Any] = field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type

    # Missing required information
    pending_questions: list[str] = field(default_factory=list)

    # Conversation history
    messages: list[dict[str, Any]] = field(  # TODO(TYPE): replace Any with concrete type
        default_factory=list
    )  # TODO(TYPE): replace Any with concrete type

    # Current scheduling request being built
    draft_request: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type

    # Retry counter for clarification
    clarification_attempts: int = 0
    max_clarification_attempts: int = 3

    def update_activity(self) -> None:
        """Update the last activity timestamp."""
        self.last_activity = datetime.now(timezone.utc)

    def add_message(
        self,
        role: str,
        content: str,
        metadata: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Add a message to the conversation history.

        Args:
            role: 'user' or 'assistant'
            content: Message content
            metadata: Additional metadata about the message
        """
        self.messages.append(
            {
                "role": role,
                "content": content,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "metadata": metadata or {},
            }
        )
        self.update_activity()

    def add_entity(
        self,
        entity_type: EntityType,
        value: Any,  # TODO(TYPE): replace Any with concrete type
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        """Add or update an extracted entity.

        Args:
            entity_type: Type of entity
            value: Extracted value
        """
        self.extracted_entities[entity_type] = value
        logger.debug(f"Added entity {entity_type.name} to context: {value}")

    def get_entity(
        self, entity_type: EntityType
    ) -> Any | None:  # TODO(TYPE): replace Any with concrete type
        """Get an extracted entity by type.

        Args:
            entity_type: Type of entity to retrieve

        Returns:
            The entity value if found, None otherwise
        """
        return self.extracted_entities.get(entity_type)

    def has_entity(self, entity_type: EntityType) -> bool:
        """Check if an entity type has been extracted.

        Args:
            entity_type: Type of entity to check

        Returns:
            True if entity exists, False otherwise
        """
        return entity_type in self.extracted_entities

    def add_pending_question(self, question: str) -> None:
        """Add a question that needs to be asked.

        Args:
            question: The question to ask the user
        """
        if question not in self.pending_questions:
            self.pending_questions.append(question)

    def get_next_question(self) -> str | None:
        """Get the next pending question.

        Returns:
            The next question or None if no questions pending
        """
        if self.pending_questions:
            return self.pending_questions[0]
        return None

    def resolve_question(self, question: str | None = None) -> None:
        """Mark a question as resolved.

        Args:
            question: The question to mark as resolved.
                      If None, removes the first question.
        """
        if question and question in self.pending_questions:
            self.pending_questions.remove(question)
        elif self.pending_questions:
            self.pending_questions.pop(0)

    def increment_clarification_attempt(self) -> bool:
        """Increment the clarification attempt counter.

        Returns:
            True if max attempts not reached, False otherwise
        """
        self.clarification_attempts += 1
        return self.clarification_attempts < self.max_clarification_attempts

    def can_ask_clarification(self) -> bool:
        """Check if we can ask another clarification question.

        Returns:
            True if under max attempts, False otherwise
        """
        return self.clarification_attempts < self.max_clarification_attempts

    def is_expired(self, max_age_minutes: int = 30) -> bool:
        """Check if the conversation context has expired.

        Args:
            max_age_minutes: Maximum age in minutes before expiration

        Returns:
            True if expired, False otherwise
        """
        age = datetime.now(timezone.utc) - self.last_activity
        return age > timedelta(minutes=max_age_minutes)

    def reset_draft(self) -> None:
        """Reset the draft request and clear pending questions."""
        self.draft_request = None
        self.pending_questions.clear()
        self.clarification_attempts = 0

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert context to dictionary for serialization."""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "tenant_id": self.tenant_id,
            "created_at": self.created_at.isoformat(),
            "last_activity": self.last_activity.isoformat(),
            "current_intent": self.current_intent,
            "extracted_entities": {k.name: v for k, v in self.extracted_entities.items()},
            "pending_questions": self.pending_questions,
            "messages": self.messages,
            "draft_request": self.draft_request,
            "clarification_attempts": self.clarification_attempts,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> "ConversationContext":  # TODO(TYPE): replace Any with concrete type
        """Create context from dictionary."""
        context = cls(
            session_id=data["session_id"],
            user_id=data["user_id"],
            tenant_id=data["tenant_id"],
        )
        context.created_at = datetime.fromisoformat(data["created_at"])
        context.last_activity = datetime.fromisoformat(data["last_activity"])
        context.current_intent = data.get("current_intent")
        context.pending_questions = data.get("pending_questions", [])
        context.messages = data.get("messages", [])
        context.draft_request = data.get("draft_request")
        context.clarification_attempts = data.get("clarification_attempts", 0)

        # Restore entities
        entity_data = data.get("extracted_entities", {})
        for name, value in entity_data.items():
            try:
                entity_type = EntityType[name]
                context.extracted_entities[entity_type] = value
            except KeyError:
                logger.warning(f"Unknown entity type in saved context: {name}")

        return context


class ContextManager:
    """Manages conversation contexts for multiple sessions.

    Provides storage, retrieval, and cleanup of conversation contexts.
    Supports both in-memory and Redis-backed storage.
    """

    def __init__(
        self,
        max_context_age_minutes: int = 30,
        use_redis: bool = False,
        redis_url: str | None = None,
    ) -> None:
        """Initialize the context manager.

        Args:
            max_context_age_minutes: Maximum age before context is expired
            use_redis: Whether to use Redis for persistence
            redis_url: Redis connection URL (required if use_redis=True)
        """
        self._contexts: dict[str, ConversationContext] = {}
        self._max_age_minutes = max_context_age_minutes
        self._use_redis = use_redis and REDIS_AVAILABLE
        self._redis_url = redis_url
        self._redis: Any | None = None  # TODO(TYPE): replace Any with concrete type

        if self._use_redis:
            if not REDIS_AVAILABLE:
                logger.warning(
                    "Redis requested but redis package not installed. "
                    "Falling back to in-memory storage."
                )
                self._use_redis = False
            elif not redis_url:
                logger.warning(
                    "Redis requested but no URL provided. Falling back to in-memory storage."
                )
                self._use_redis = False
            else:
                logger.info(f"Context manager using Redis at {redis_url}")

    async def _get_redis(self) -> Any | None:  # TODO(TYPE): replace Any with concrete type
        """Get or create Redis connection."""
        if not self._use_redis:
            return None

        if self._redis is None:
            if not self._redis_url or not REDIS_AVAILABLE:
                return None
            try:
                self._redis = await create_async_redis_client(  # pyright: ignore[reportPossiblyUnboundVariable]
                    self._redis_url, decode_responses=True
                )
            except Exception as e:
                logger.error(f"Failed to connect to Redis: {e}")
                self._use_redis = False
                return None

        return self._redis

    def _get_redis_key(self, session_id: str) -> str:
        """Generate Redis key for session."""
        return f"scheduling:nlp:context:{session_id}"

    async def _load_from_redis(self, session_id: str) -> ConversationContext | None:
        """Load context from Redis."""
        r = await self._get_redis()
        if not r:
            return None

        try:
            data = await r.get(self._get_redis_key(session_id))
            if data:
                context = ConversationContext.from_dict(
                    cast(dict[str, object], json.loads(data))
                )
                # Check if expired
                if not context.is_expired(self._max_age_minutes):
                    return context
                else:
                    # Delete expired context
                    await r.delete(self._get_redis_key(session_id))
        except Exception as e:
            logger.error(f"Error loading context from Redis: {e}")

        return None

    async def _save_to_redis(self, context: ConversationContext) -> bool:
        """Save context to Redis."""
        r = await self._get_redis()
        if not r:
            return False

        try:
            key = self._get_redis_key(context.session_id)
            data = json.dumps(context.to_dict())
            # Set with expiration
            await r.setex(
                key,
                timedelta(minutes=self._max_age_minutes),
                data,
            )
            return True
        except Exception as e:
            logger.error(f"Error saving context to Redis: {e}")
            return False

    async def _delete_from_redis(self, session_id: str) -> bool:
        """Delete context from Redis."""
        r = await self._get_redis()
        if not r:
            return False

        try:
            result = await r.delete(self._get_redis_key(session_id))
            return cast(bool, result > 0)
        except Exception as e:
            logger.error(f"Error deleting context from Redis: {e}")
            return False

    async def get_or_create(
        self,
        session_id: str,
        user_id: str,
        tenant_id: int,
    ) -> ConversationContext:
        """Get existing context or create new one.

        Args:
            session_id: Unique session identifier
            user_id: User identifier
            tenant_id: Tenant identifier

        Returns:
            ConversationContext for the session
        """
        # Clean up expired contexts periodically
        if len(self._contexts) > 100:
            self._cleanup_expired()

        # Try Redis first if enabled
        if self._use_redis:
            context = await self._load_from_redis(session_id)
            if context:
                logger.debug(f"Loaded context from Redis for {session_id}")
                return context

        # Check in-memory
        if session_id in self._contexts:
            context = self._contexts[session_id]
            if not context.is_expired(self._max_age_minutes):
                context.update_activity()
                # Sync to Redis if enabled
                if self._use_redis:
                    await self._save_to_redis(context)
                return context
            else:
                # Expired, remove old context
                del self._contexts[session_id]
                if self._use_redis:
                    await self._delete_from_redis(session_id)

        # Create new context
        context = ConversationContext(
            session_id=session_id,
            user_id=user_id,
            tenant_id=tenant_id,
        )
        self._contexts[session_id] = context

        # Save to Redis if enabled
        if self._use_redis:
            await self._save_to_redis(context)

        logger.info(f"Created new conversation context for session {session_id}")
        return context

    async def get(self, session_id: str) -> ConversationContext | None:
        """Get existing context without creating.

        Args:
            session_id: Session identifier

        Returns:
            ConversationContext if exists and not expired, None otherwise
        """
        # Try Redis first if enabled
        if self._use_redis:
            context = await self._load_from_redis(session_id)
            if context:
                return context

        # Check in-memory
        context = self._contexts.get(session_id)
        if context and not context.is_expired(self._max_age_minutes):
            context.update_activity()
            return context
        elif context:
            # Expired, remove it
            del self._contexts[session_id]
            if self._use_redis:
                await self._delete_from_redis(session_id)

        return None

    async def save(self, context: ConversationContext) -> None:
        """Save/update a context.

        Args:
            context: Context to save
        """
        context.update_activity()
        self._contexts[context.session_id] = context

        if self._use_redis:
            await self._save_to_redis(context)

    async def delete(self, session_id: str) -> bool:
        """Delete a context.

        Args:
            session_id: Session identifier

        Returns:
            True if deleted, False if not found
        """
        found = False

        if session_id in self._contexts:
            del self._contexts[session_id]
            found = True

        if self._use_redis:
            redis_deleted = await self._delete_from_redis(session_id)
            found = found or redis_deleted

        if found:
            logger.info(f"Deleted conversation context for {session_id}")

        return found

    def _cleanup_expired(self) -> None:
        """Remove expired contexts from memory."""
        expired = [
            sid for sid, ctx in self._contexts.items() if ctx.is_expired(self._max_age_minutes)
        ]
        for sid in expired:
            del self._contexts[sid]
        if expired:
            logger.info(f"Cleaned up {len(expired)} expired conversation contexts")

    def clear_all(self) -> None:
        """Clear all in-memory contexts."""
        count = len(self._contexts)
        self._contexts.clear()
        logger.info(f"Cleared all {count} in-memory conversation contexts")

    def get_stats(self) -> dict[str, int]:
        """Get context statistics.

        Returns:
            Dict with total, active, and expired counts
        """
        total = len(self._contexts)
        expired = sum(1 for ctx in self._contexts.values() if ctx.is_expired(self._max_age_minutes))
        return {
            "total": total,
            "active": total - expired,
            "expired": expired,
        }
