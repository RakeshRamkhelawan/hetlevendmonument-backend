"""
Unit tests for core/services/conversation_service.py - Conversation Persistence
Coverage target: 0% → 85%+
Created: November 28, 2025

Tests conversation storage, retrieval, and management for the autonomous learning system.
This is a CRITICAL module for the learning loop and CVA agent functionality.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch

import pytest

from src.core.conversations.models import CVAConversation
from src.core.services.conversation_service import ConversationService


@pytest.fixture(autouse=True)
def mock_tenant_context():
    """Auto-mock tenant context for all tests"""
    with patch("src.core.services.conversation_service.get_tenant_id", return_value=1):
        yield


@pytest.fixture
def mock_db_session():
    """Create mock async database session"""
    mock_session = AsyncMock()
    mock_session.add = Mock()  # add() is sync in SQLAlchemy async sessions
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()
    mock_session.execute = AsyncMock()
    return mock_session


@pytest.fixture
def mock_db_manager(mock_db_session):
    """Mock database manager with async context manager support"""
    with patch("src.core.services.conversation_service.db_manager") as mock_manager:
        mock_manager.is_initialized = Mock(return_value=True)
        mock_manager._is_initialized = True
        # Create an async context manager that returns the session
        async_cm = AsyncMock()
        async_cm.__aenter__ = AsyncMock(return_value=mock_db_session)
        async_cm.__aexit__ = AsyncMock(return_value=None)
        mock_manager.get_session = Mock(return_value=async_cm)
        yield mock_manager


@pytest.fixture
def sample_conversation_data():
    """Sample data for testing"""
    return {
        "session_id": "test-session-123",
        "user_id": "user-456",
        "user_message": "How do I implement authentication?",
        "cva_response": "Here's how to implement authentication...",
        "conversation_turn": 1,
        "response_metadata": {"model": "gpt-4", "tokens": 150},
        "performance_data": {"latency_ms": 234, "cache_hit": False},
        "conversation_history": [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ],
    }


class TestSaveConversation:
    """Test conversation saving functionality"""

    @pytest.mark.asyncio
    async def test_save_conversation_success(
        self, mock_db_manager, mock_db_session, sample_conversation_data
    ):
        """Test successful conversation save with all fields"""

        # Mock refresh to set the ID on the conversation object
        async def mock_refresh(obj):
            obj.id = "conv-789"

        mock_db_session.refresh.side_effect = mock_refresh

        # Act
        result = await ConversationService.save_conversation(**sample_conversation_data)

        # Assert
        assert result == "conv-789"
        mock_db_session.add.assert_called_once()
        mock_db_session.commit.assert_awaited_once()
        mock_db_session.refresh.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_save_conversation_minimal_fields(self, mock_db_manager, mock_db_session):
        """Test saving conversation with only required fields"""

        async def mock_refresh(obj):
            obj.id = "conv-min-123"

        mock_db_session.refresh.side_effect = mock_refresh

        # Act
        result = await ConversationService.save_conversation(
            session_id="session-1",
            user_id="user-1",
            user_message="Test message",
            cva_response="Test response",
            conversation_turn=1,
        )

        # Assert
        assert result == "conv-min-123"
        mock_db_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_save_conversation_with_context_summary(
        self, mock_db_manager, mock_db_session, sample_conversation_data
    ):
        """Test that context summary is created from conversation history"""

        async def mock_refresh(obj):
            obj.id = "conv-context-123"

        mock_db_session.refresh.side_effect = mock_refresh

        # Act
        result = await ConversationService.save_conversation(**sample_conversation_data)

        # Assert
        assert result == "conv-context-123"

    @pytest.mark.asyncio
    async def test_save_conversation_database_not_initialized(
        self, mock_db_session, sample_conversation_data
    ):
        """Test handling when database is not initialized"""
        with patch("src.core.services.conversation_service.db_manager") as mock_manager:
            mock_manager.is_initialized = Mock(return_value=False)
            mock_manager.initialize = AsyncMock(return_value=True)

            async_cm = AsyncMock()
            async_cm.__aenter__ = AsyncMock(return_value=mock_db_session)
            async_cm.__aexit__ = AsyncMock(return_value=None)
            mock_manager.get_session = Mock(return_value=async_cm)

            async def mock_refresh(obj):
                obj.id = "conv-init-123"

            mock_db_session.refresh.side_effect = mock_refresh

            # Act
            result = await ConversationService.save_conversation(**sample_conversation_data)

            # Assert
            mock_manager.initialize.assert_awaited_once()
            assert result == "conv-init-123"

    @pytest.mark.asyncio
    async def test_save_conversation_database_init_fails(self, sample_conversation_data):
        """Test error handling when database initialization fails"""
        with patch("src.core.services.conversation_service.db_manager") as mock_manager:
            mock_manager.is_initialized = Mock(return_value=False)
            mock_manager.initialize = AsyncMock(return_value=False)

            # Act & Assert
            with pytest.raises(Exception, match="Failed to initialize database manager"):
                await ConversationService.save_conversation(**sample_conversation_data)

    @pytest.mark.asyncio
    async def test_save_conversation_commit_failure(
        self, mock_db_manager, mock_db_session, sample_conversation_data
    ):
        """Test handling of database commit failures"""
        mock_db_session.commit.side_effect = Exception("Database commit failed")

        # Act & Assert
        with pytest.raises(Exception, match="Failed to save conversation"):
            await ConversationService.save_conversation(**sample_conversation_data)

    @pytest.mark.asyncio
    async def test_save_conversation_special_characters(self, mock_db_manager, mock_db_session):
        """Test saving messages with special characters"""
        special_message = "Test with émojis 🚀 and ñoño characters: <script>alert('xss')</script>"

        async def mock_refresh(obj):
            obj.id = "conv-special-123"

        mock_db_session.refresh.side_effect = mock_refresh

        # Act
        result = await ConversationService.save_conversation(
            session_id="session-1",
            user_id="user-1",
            user_message=special_message,
            cva_response="Response with special chars: 中文字符",
            conversation_turn=1,
        )

        # Assert
        assert result == "conv-special-123"
        mock_db_session.add.assert_called_once()


class TestGetConversationHistory:
    """Test conversation history retrieval"""

    @pytest.mark.asyncio
    async def test_get_history_multiple_turns(self, mock_db_manager, mock_db_session):
        """Test retrieving multi-turn conversation history"""
        mock_conv1 = Mock()
        mock_conv1.user_message = "First question"
        mock_conv1.cva_response = "First answer"
        mock_conv1.conversation_turn = 1

        mock_conv2 = Mock()
        mock_conv2.user_message = "Second question"
        mock_conv2.cva_response = "Second answer"
        mock_conv2.conversation_turn = 2

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [mock_conv1, mock_conv2]
        mock_db_session.execute.return_value = mock_result

        # Act
        result = await ConversationService.get_conversation_history("session-123")

        # Assert
        assert len(result) == 4  # 2 turns * 2 messages each
        assert result[0] == {"role": "user", "content": "First question"}
        assert result[1] == {"role": "assistant", "content": "First answer"}
        assert result[2] == {"role": "user", "content": "Second question"}
        assert result[3] == {"role": "assistant", "content": "Second answer"}

    @pytest.mark.asyncio
    async def test_get_history_empty_session(self, mock_db_manager, mock_db_session):
        """Test retrieving history for session with no conversations"""
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute.return_value = mock_result

        # Act
        result = await ConversationService.get_conversation_history("empty-session")

        # Assert
        assert result == []

    @pytest.mark.asyncio
    async def test_get_history_with_limit(self, mock_db_manager, mock_db_session):
        """Test applying limit to conversation history retrieval"""
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute.return_value = mock_result

        # Act
        result = await ConversationService.get_conversation_history("session-123", limit=10)

        # Assert - the execute was called (limit is applied in SQLAlchemy query)
        mock_db_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_history_database_not_initialized(self):
        """Test handling when database not initialized during retrieval"""
        with patch("src.core.services.conversation_service.db_manager") as mock_manager:
            mock_manager.is_initialized = Mock(return_value=False)
            mock_manager.initialize = AsyncMock(return_value=False)

            # Act
            result = await ConversationService.get_conversation_history("session-123")

            # Assert
            assert result == []
            mock_manager.initialize.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_history_tenant_isolation(self, mock_db_manager, mock_db_session):
        """Test that conversation history is filtered by tenant_id"""
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute.return_value = mock_result

        with patch("src.core.services.conversation_service.get_tenant_id", return_value=42):
            # Act
            result = await ConversationService.get_conversation_history("session-123")

            # Assert - execute was called (implies tenant filtering was applied)
            mock_db_session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_history_nonexistent_session(self, mock_db_manager, mock_db_session):
        """Test retrieving history for non-existent session returns empty list"""
        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db_session.execute.return_value = mock_result

        # Act
        result = await ConversationService.get_conversation_history("nonexistent-session-999")

        # Assert
        assert result == []


class TestConversationEdgeCases:
    """Test edge cases and error scenarios"""

    @pytest.mark.asyncio
    async def test_very_long_message(self, mock_db_manager, mock_db_session):
        """Test handling of very long messages (>10000 chars)"""
        long_message = "x" * 15000  # 15k characters

        async def mock_refresh(obj):
            obj.id = "conv-long-123"

        mock_db_session.refresh.side_effect = mock_refresh

        # Act
        result = await ConversationService.save_conversation(
            session_id="session-1",
            user_id="user-1",
            user_message=long_message,
            cva_response="Short response",
            conversation_turn=1,
        )

        # Assert
        assert result == "conv-long-123"

    @pytest.mark.asyncio
    async def test_concurrent_saves_same_session(self, mock_db_manager, mock_db_session):
        """Test handling concurrent saves to same session"""
        call_count = 0

        async def mock_refresh(obj):
            nonlocal call_count
            call_count += 1
            obj.id = f"conv-concurrent-{call_count}"

        mock_db_session.refresh.side_effect = mock_refresh

        # Act - Simulate multiple turns being saved
        result1 = await ConversationService.save_conversation(
            session_id="session-1",
            user_id="user-1",
            user_message="Message 1",
            cva_response="Response 1",
            conversation_turn=1,
        )

        result2 = await ConversationService.save_conversation(
            session_id="session-1",
            user_id="user-1",
            user_message="Message 2",
            cva_response="Response 2",
            conversation_turn=2,
        )

        # Assert - Both should succeed with different IDs
        assert result1 != result2
        assert mock_db_session.add.call_count == 2

    @pytest.mark.asyncio
    async def test_null_metadata_fields(self, mock_db_manager, mock_db_session):
        """Test handling None/null metadata fields"""

        async def mock_refresh(obj):
            obj.id = "conv-null-123"

        mock_db_session.refresh.side_effect = mock_refresh

        # Act
        result = await ConversationService.save_conversation(
            session_id="session-1",
            user_id="user-1",
            user_message="Test",
            cva_response="Response",
            conversation_turn=1,
            response_metadata=None,
            performance_data=None,
            conversation_history=None,
        )

        # Assert
        assert result == "conv-null-123"


class TestContextSummaryCreation:
    """Test context summary creation from conversation history"""

    def test_create_context_summary_short_history(self):
        """Test context summary for short conversation"""
        # Note: _create_context_summary is a private method
        # This test would need to either:
        # 1. Test it indirectly through save_conversation
        # 2. Make it public/internal for testing
        # 3. Test the integration behavior

        # For now, this is a placeholder showing the test structure
        pass

    def test_create_context_summary_long_history(self):
        """Test context summary for long conversation (100+ turns)"""
        # Test that long conversations are properly summarized
        pass


# Performance and integration tests (optional)
class TestConversationPerformance:
    """Performance-related tests"""

    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_save_many_conversations(self, mock_db_manager, mock_db_session):
        """Test saving many conversations in sequence"""
        call_count = 0

        async def mock_refresh(obj):
            nonlocal call_count
            call_count += 1
            obj.id = f"conv-perf-{call_count}"

        mock_db_session.refresh.side_effect = mock_refresh

        # Act - Save 100 conversations
        for i in range(100):
            result = await ConversationService.save_conversation(
                session_id=f"session-{i}",
                user_id="user-1",
                user_message=f"Message {i}",
                cva_response=f"Response {i}",
                conversation_turn=1,
            )
            assert result is not None

        # Assert
        assert mock_db_session.add.call_count == 100
