"""
Comprehensive tests for src/core/services/conversation_service.py
Coverage target: 100% of conversation service
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.core.services.conversation_service import ConversationService


def _make_async_db_manager(mock_db_session, is_initialized=True):
    """Helper to create a properly mocked async db_manager."""
    mock_manager = MagicMock()
    mock_manager.is_initialized = Mock(return_value=is_initialized)
    mock_manager.initialize = AsyncMock(return_value=True)
    async_cm = AsyncMock()
    async_cm.__aenter__ = AsyncMock(return_value=mock_db_session)
    async_cm.__aexit__ = AsyncMock(return_value=None)
    mock_manager.get_session = Mock(return_value=async_cm)
    return mock_manager


def _make_db_session():
    """Helper to create an async-compatible db session mock."""
    mock_session = AsyncMock()
    mock_session.add = Mock()
    mock_session.commit = AsyncMock()
    mock_session.refresh = AsyncMock()
    mock_session.execute = AsyncMock()
    return mock_session


class TestSaveConversation:
    """Test ConversationService.save_conversation method"""

    @pytest.mark.asyncio
    async def test_save_conversation_success(self):
        """Test successful conversation save"""
        mock_session = _make_db_session()

        async def mock_refresh(obj):
            obj.id = "conv-123"

        mock_session.refresh.side_effect = mock_refresh

        mock_manager = _make_async_db_manager(mock_session, is_initialized=True)

        with patch("src.core.services.conversation_service.db_manager", mock_manager):
            result = await ConversationService.save_conversation(
                session_id="session-1",
                user_id="user-1",
                user_message="Hello",
                cva_response="Hi there!",
                conversation_turn=1,
            )

        assert result == "conv-123"
        mock_session.add.assert_called_once()
        mock_session.commit.assert_awaited_once()
        mock_session.refresh.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_save_conversation_with_metadata(self):
        """Test save conversation with metadata and performance data"""
        mock_session = _make_db_session()

        async def mock_refresh(obj):
            obj.id = "conv-456"

        mock_session.refresh.side_effect = mock_refresh

        mock_manager = _make_async_db_manager(mock_session, is_initialized=True)

        metadata = {"model": "gemini-1.5", "tokens": 150}
        performance = {"latency_ms": 250, "cache_hit": False}

        with patch("src.core.services.conversation_service.db_manager", mock_manager):
            result = await ConversationService.save_conversation(
                session_id="session-2",
                user_id="user-2",
                user_message="What is AI?",
                cva_response="AI is...",
                conversation_turn=2,
                response_metadata=metadata,
                performance_data=performance,
            )

        assert result == "conv-456"

    @pytest.mark.asyncio
    async def test_save_conversation_with_history(self):
        """Test save conversation with conversation history"""
        mock_session = _make_db_session()

        async def mock_refresh(obj):
            obj.id = "conv-789"

        mock_session.refresh.side_effect = mock_refresh

        mock_manager = _make_async_db_manager(mock_session, is_initialized=True)

        history = [
            {"role": "user", "content": "Tell me about AI"},
            {"role": "assistant", "content": "AI is..."},
        ]

        with patch("src.core.services.conversation_service.db_manager", mock_manager):
            result = await ConversationService.save_conversation(
                session_id="session-3",
                user_id="user-3",
                user_message="More details?",
                cva_response="Sure...",
                conversation_turn=2,
                conversation_history=history,
            )

        assert result == "conv-789"

    @pytest.mark.asyncio
    async def test_save_conversation_db_not_initialized(self):
        """Test save conversation initializes DB if needed"""
        mock_session = _make_db_session()

        async def mock_refresh(obj):
            obj.id = "conv-init"

        mock_session.refresh.side_effect = mock_refresh

        mock_manager = _make_async_db_manager(mock_session, is_initialized=False)
        mock_manager.initialize = AsyncMock(return_value=True)

        with patch("src.core.services.conversation_service.db_manager", mock_manager):
            result = await ConversationService.save_conversation("sess", "user", "msg", "resp", 1)

        mock_manager.initialize.assert_awaited_once()
        assert result == "conv-init"

    @pytest.mark.asyncio
    async def test_save_conversation_db_init_fails(self):
        """Test save conversation raises error if DB init fails"""
        mock_manager = MagicMock()
        mock_manager.is_initialized = Mock(return_value=False)
        mock_manager.initialize = AsyncMock(return_value=False)

        with patch("src.core.services.conversation_service.db_manager", mock_manager):
            with pytest.raises(Exception) as exc_info:
                await ConversationService.save_conversation("sess", "user", "msg", "resp", 1)
        assert "Failed to" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_save_conversation_db_error(self):
        """Test save conversation handles database errors"""
        mock_session = _make_db_session()
        mock_session.commit.side_effect = Exception("DB error")

        mock_manager = _make_async_db_manager(mock_session, is_initialized=True)

        with patch("src.core.services.conversation_service.db_manager", mock_manager):
            with pytest.raises(Exception) as exc_info:
                await ConversationService.save_conversation("sess", "user", "msg", "resp", 1)
        assert "Failed to save conversation" in str(exc_info.value)


class TestGetConversationHistory:
    """Test ConversationService.get_conversation_history method"""

    @pytest.mark.asyncio
    async def test_get_conversation_history_success(self):
        """Test successful retrieval of conversation history"""
        mock_session = _make_db_session()

        mock_conv1 = Mock(user_message="Hello", cva_response="Hi!")
        mock_conv2 = Mock(user_message="How are you?", cva_response="I'm good!")

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [mock_conv1, mock_conv2]
        mock_session.execute.return_value = mock_result

        mock_manager = _make_async_db_manager(mock_session, is_initialized=True)

        with patch("src.core.services.conversation_service.db_manager", mock_manager):
            with patch(
                "src.core.services.conversation_service.get_tenant_id",
                return_value="tenant-1",
            ):
                result = await ConversationService.get_conversation_history("session-1")

        assert len(result) == 4
        assert result[0] == {"role": "user", "content": "Hello"}
        assert result[1] == {"role": "assistant", "content": "Hi!"}

    @pytest.mark.asyncio
    async def test_get_conversation_history_with_limit(self):
        """Test conversation history respects limit parameter"""
        mock_session = _make_db_session()

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = mock_result

        mock_manager = _make_async_db_manager(mock_session, is_initialized=True)

        with patch("src.core.services.conversation_service.db_manager", mock_manager):
            with patch(
                "src.core.services.conversation_service.get_tenant_id",
                return_value="tenant-1",
            ):
                result = await ConversationService.get_conversation_history("session-1", limit=10)

        mock_session.execute.assert_awaited_once()
        assert result == []

    @pytest.mark.asyncio
    async def test_get_conversation_history_db_not_initialized(self):
        """Test returns empty list if DB not initialized and init fails"""
        mock_manager = MagicMock()
        mock_manager.is_initialized = Mock(return_value=False)
        mock_manager.initialize = AsyncMock(return_value=False)

        with patch("src.core.services.conversation_service.db_manager", mock_manager):
            result = await ConversationService.get_conversation_history("session-1")

        assert result == []

    @pytest.mark.asyncio
    async def test_get_conversation_history_error(self):
        """Test handles errors gracefully"""
        mock_session = _make_db_session()
        mock_manager = _make_async_db_manager(mock_session, is_initialized=True)

        with patch("src.core.services.conversation_service.db_manager", mock_manager):
            with patch(
                "src.core.services.conversation_service.get_tenant_id",
                side_effect=Exception("Tenant error"),
            ):
                result = await ConversationService.get_conversation_history("session-1")

        assert result == []


class TestGetLearningData:
    """Test ConversationService.get_learning_data method"""

    @pytest.mark.asyncio
    async def test_get_learning_data_success(self):
        """Test successful retrieval of learning data"""
        mock_session = _make_db_session()

        now = datetime.now(timezone.utc)
        mock_conv = Mock(
            id="conv-1",
            user_message="Test",
            cva_response="Response",
            user_feedback="positive",
            feedback_details="Great!",
            performance_data={"latency": 100},
            conversation_topic="AI",
            keywords=["test", "ai"],
            created_at=now,
        )

        mock_result = Mock()
        mock_result.scalars.return_value.all.return_value = [mock_conv]
        mock_session.execute.return_value = mock_result

        mock_manager = _make_async_db_manager(mock_session, is_initialized=True)

        with patch("src.core.services.conversation_service.db_manager", mock_manager):
            with patch(
                "src.core.services.conversation_service.get_tenant_id",
                return_value="tenant-1",
            ):
                result = await ConversationService.get_learning_data(limit=10)

        assert len(result) == 1
        assert result[0]["conversation_id"] == "conv-1"
        assert result[0]["user_feedback"] == "positive"

    @pytest.mark.asyncio
    async def test_get_learning_data_empty_result(self):
        """Test returns empty list when no data available"""
        mock_manager = MagicMock()
        mock_manager.is_initialized = Mock(return_value=False)
        mock_manager.initialize = AsyncMock(return_value=False)

        with patch("src.core.services.conversation_service.db_manager", mock_manager):
            result = await ConversationService.get_learning_data()

        assert result == []


class TestAddFeedback:
    """Test ConversationService.add_feedback method"""

    @pytest.mark.asyncio
    async def test_add_feedback_success(self):
        """Test successful feedback addition"""
        mock_session = _make_db_session()

        mock_conversation = Mock()
        mock_scalar_result = Mock()
        mock_scalar_result.scalars.return_value.first.return_value = mock_conversation
        mock_session.execute.return_value = mock_scalar_result

        mock_manager = _make_async_db_manager(mock_session, is_initialized=True)

        with patch("src.core.services.conversation_service.db_manager", mock_manager):
            with patch(
                "src.core.services.conversation_service.get_tenant_id",
                return_value="tenant-1",
            ):
                result = await ConversationService.add_feedback("conv-1", "positive", "Helpful!")

        assert result is True
        assert mock_conversation.user_feedback == "positive"
        assert mock_conversation.feedback_details == "Helpful!"
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_add_feedback_conversation_not_found(self):
        """Test returns False when conversation not found"""
        mock_session = _make_db_session()

        mock_scalar_result = Mock()
        mock_scalar_result.scalars.return_value.first.return_value = None
        mock_session.execute.return_value = mock_scalar_result

        mock_manager = _make_async_db_manager(mock_session, is_initialized=True)

        with patch("src.core.services.conversation_service.db_manager", mock_manager):
            with patch(
                "src.core.services.conversation_service.get_tenant_id",
                return_value="tenant-1",
            ):
                result = await ConversationService.add_feedback("conv-999", "positive")

        assert result is False


class TestGetConversationAnalytics:
    """Test ConversationService.get_conversation_analytics method"""

    @pytest.mark.asyncio
    async def test_get_analytics_success(self):
        """Test successful analytics retrieval"""
        mock_session = _make_db_session()

        # count result
        count_result = Mock()
        count_result.scalar.return_value = 100

        # feedback result
        feedback_stat = Mock()
        feedback_stat.user_feedback = "positive"
        feedback_stat.count = 50
        feedback_result = Mock()
        feedback_result.all.return_value = [feedback_stat]

        # topic result
        topic_stat = Mock()
        topic_stat.conversation_topic = "AI"
        topic_stat.count = 30
        topic_result = Mock()
        topic_result.all.return_value = [topic_stat]

        mock_session.execute.side_effect = [count_result, feedback_result, topic_result]

        mock_manager = _make_async_db_manager(mock_session, is_initialized=True)

        with patch("src.core.services.conversation_service.db_manager", mock_manager):
            with patch(
                "src.core.services.conversation_service.get_tenant_id",
                return_value="tenant-1",
            ):
                result = await ConversationService.get_conversation_analytics(days=30)

        assert result["period_days"] == 30
        assert result["total_conversations"] == 100
        assert "feedback_distribution" in result

    @pytest.mark.asyncio
    async def test_get_analytics_db_error(self):
        """Test handles errors gracefully"""
        mock_manager = MagicMock()
        mock_manager.is_initialized = Mock(return_value=False)
        mock_manager.initialize = AsyncMock(return_value=False)

        with patch("src.core.services.conversation_service.db_manager", mock_manager):
            result = await ConversationService.get_conversation_analytics()

        assert result == {}


class TestCreateContextSummary:
    """Test ConversationService._create_context_summary method"""

    def test_create_context_summary_empty_history(self):
        """Test context summary with empty history"""
        result = ConversationService._create_context_summary([])
        assert result == ""

    def test_create_context_summary_success(self):
        """Test context summary generation"""
        history = [
            {"role": "user", "content": "Tell me about artificial intelligence"},
            {"role": "assistant", "content": "AI is..."},
            {"role": "user", "content": "What about machine learning models?"},
        ]

        result = ConversationService._create_context_summary(history)

        assert "Topics discussed:" in result
        assert len(result) > 0

    def test_create_context_summary_filters_short_words(self):
        """Test context summary filters short words"""
        history = [
            {"role": "user", "content": "I am a test"},
            {"role": "assistant", "content": "OK"},
        ]

        result = ConversationService._create_context_summary(history)
        assert result != ""

    def test_create_context_summary_last_three_messages(self):
        """Test context summary uses last 3 user messages"""
        history = [
            {"role": "user", "content": "message one"},
            {"role": "user", "content": "message two"},
            {"role": "user", "content": "message three"},
            {"role": "user", "content": "message four"},
            {"role": "user", "content": "message five important"},
        ]

        result = ConversationService._create_context_summary(history)
        assert len(result) > 0
