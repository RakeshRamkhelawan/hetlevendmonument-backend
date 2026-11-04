"""Tests for conversation context management."""

from datetime import datetime, timedelta, timezone

import pytest

from src.core.scheduling.nlp.context import ContextManager, ConversationContext
from src.core.scheduling.nlp.entities import EntityType


class TestConversationContext:
    """Test suite for ConversationContext."""

    @pytest.fixture
    def context(self):
        """Create a ConversationContext instance."""
        return ConversationContext(
            session_id="test-session-123",
            user_id="user-456",
            tenant_id=1,
        )

    def test_context_creation(self, context):
        """Test context initialization."""
        assert context.session_id == "test-session-123"
        assert context.user_id == "user-456"
        assert context.tenant_id == 1
        assert context.clarification_attempts == 0
        assert len(context.pending_questions) == 0

    def test_add_entity(self, context):
        """Test adding entities to context."""
        context.add_entity(EntityType.DATE, datetime(2026, 3, 20, tzinfo=timezone.utc))

        assert context.has_entity(EntityType.DATE)
        assert context.get_entity(EntityType.DATE) is not None

    def test_add_message(self, context):
        """Test adding messages to context."""
        context.add_message("user", "Schedule a meeting")
        context.add_message("assistant", "When would you like to meet?")

        assert len(context.messages) == 2
        assert context.messages[0]["role"] == "user"
        assert context.messages[1]["role"] == "assistant"

    def test_pending_questions(self, context):
        """Test managing pending questions."""
        context.add_pending_question("What time?")
        context.add_pending_question("Who should attend?")

        assert context.get_next_question() == "What time?"

        context.resolve_question()
        assert context.get_next_question() == "Who should attend?"

    def test_clarification_attempts(self, context):
        """Test clarification attempt tracking."""
        assert context.can_ask_clarification() is True

        context.increment_clarification_attempt()
        context.increment_clarification_attempt()
        context.increment_clarification_attempt()

        # Max is 3 by default
        assert context.can_ask_clarification() is False

    def test_is_expired(self, context):
        """Test expiration detection."""
        # Context just created should not be expired
        assert context.is_expired(max_age_minutes=30) is False

        # Manually set last activity to be old
        context.last_activity = datetime.now(timezone.utc) - timedelta(minutes=31)
        assert context.is_expired(max_age_minutes=30) is True

    def test_reset_draft(self, context):
        """Test resetting draft request."""
        context.add_pending_question("What time?")
        context.draft_request = {"title": "Test"}
        context.clarification_attempts = 2

        context.reset_draft()

        assert len(context.pending_questions) == 0
        assert context.draft_request is None
        assert context.clarification_attempts == 0

    def test_to_dict(self, context):
        """Test serialization to dict."""
        context.add_entity(EntityType.DATE, "2026-03-20")
        data = context.to_dict()

        assert data["session_id"] == "test-session-123"
        assert "extracted_entities" in data
        assert data["clarification_attempts"] == 0

    def test_from_dict(self):
        """Test deserialization from dict."""
        data = {
            "session_id": "test-session-123",
            "user_id": "user-456",
            "tenant_id": 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_activity": datetime.now(timezone.utc).isoformat(),
            "current_intent": "SCHEDULE",
            "extracted_entities": {"DATE": "2026-03-20"},
            "pending_questions": ["What time?"],
            "messages": [],
            "draft_request": None,
            "clarification_attempts": 1,
        }

        context = ConversationContext.from_dict(data)

        assert context.session_id == "test-session-123"
        assert context.current_intent == "SCHEDULE"
        assert context.clarification_attempts == 1


class TestContextManager:
    """Test suite for ContextManager."""

    @pytest.fixture
    def manager(self):
        """Create a ContextManager instance."""
        return ContextManager(max_context_age_minutes=30)

    @pytest.mark.asyncio
    async def test_get_or_create_new(self, manager):
        """Test creating new context."""
        context = await manager.get_or_create("session-1", "user-1", 1)

        assert context.session_id == "session-1"
        assert context.user_id == "user-1"

    @pytest.mark.asyncio
    async def test_get_or_create_existing(self, manager):
        """Test retrieving existing context."""
        context1 = await manager.get_or_create("session-1", "user-1", 1)
        context1.add_entity(EntityType.DATE, "2026-03-20")

        context2 = await manager.get_or_create("session-1", "user-1", 1)

        # Should be the same context
        assert context1 is context2
        assert context2.has_entity(EntityType.DATE)

    @pytest.mark.asyncio
    async def test_get_existing(self, manager):
        """Test getting existing context without creating."""
        await manager.get_or_create("session-1", "user-1", 1)

        context = await manager.get("session-1")
        assert context is not None
        assert context.session_id == "session-1"

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, manager):
        """Test getting non-existent context."""
        context = await manager.get("nonexistent-session")
        assert context is None

    @pytest.mark.asyncio
    async def test_delete_context(self, manager):
        """Test deleting context."""
        await manager.get_or_create("session-1", "user-1", 1)

        deleted = await manager.delete("session-1")
        assert deleted is True
        assert await manager.get("session-1") is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, manager):
        """Test deleting non-existent context."""
        deleted = await manager.delete("nonexistent-session")
        assert deleted is False

    @pytest.mark.asyncio
    async def test_cleanup_expired(self, manager):
        """Test cleanup of expired contexts."""
        # Create context
        context = await manager.get_or_create("session-1", "user-1", 1)

        # Manually expire it
        context.last_activity = datetime.now(timezone.utc) - timedelta(minutes=31)

        # Create another context that should trigger cleanup
        await manager.get_or_create("session-2", "user-2", 1)

        # First context should be gone (get() detects expiry and removes it)
        assert await manager.get("session-1") is None
        assert await manager.get("session-2") is not None

    @pytest.mark.asyncio
    async def test_clear_all(self, manager):
        """Test clearing all contexts."""
        await manager.get_or_create("session-1", "user-1", 1)
        await manager.get_or_create("session-2", "user-2", 1)

        manager.clear_all()

        assert await manager.get("session-1") is None
        assert await manager.get("session-2") is None

    @pytest.mark.asyncio
    async def test_get_stats(self, manager):
        """Test getting context statistics."""
        await manager.get_or_create("session-1", "user-1", 1)
        await manager.get_or_create("session-2", "user-2", 1)

        stats = manager.get_stats()

        assert stats["total"] == 2
        assert stats["active"] == 2
        assert stats["expired"] == 0
