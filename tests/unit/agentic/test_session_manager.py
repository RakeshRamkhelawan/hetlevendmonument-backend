"""
Unit tests for AgenticSessionManager.
"""

import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.agentic.models import AgentSession, SessionMessage
from src.domains.agentic.services.session_manager import AgenticSessionManager, ChatMessage, Session


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    mock = MagicMock()
    mock.setex = AsyncMock()
    mock.get = AsyncMock()
    mock.sadd = AsyncMock()
    mock.srem = AsyncMock()
    mock.delete = AsyncMock()
    mock.smembers = AsyncMock()
    return mock


@pytest.fixture
def session_manager(mock_redis):
    """AgenticSessionManager instance with mocked Redis."""
    return AgenticSessionManager(redis_client=mock_redis, ttl_hours=24, enable_db_backup=True)


@pytest.mark.asyncio
async def test_create_session(session_manager, mock_redis):
    """Test creating a new session."""
    user_id = 123
    tenant_id = 456
    initial_feature = "workflow_builder"
    metadata = {"source": "web"}

    session = await session_manager.create_session(
        user_id=user_id,
        tenant_id=tenant_id,
        initial_feature=initial_feature,
        metadata=metadata,
    )

    assert isinstance(session, Session)
    assert session.user_id == user_id
    assert session.tenant_id == tenant_id
    assert session.current_feature == initial_feature
    assert session.metadata == metadata
    assert len(session.messages) == 0

    # Verify Redis interactions
    mock_redis.setex.assert_called_once()
    mock_redis.sadd.assert_called_once_with(
        session_manager._user_sessions_key(user_id, tenant_id), session.id
    )


@pytest.mark.asyncio
async def test_get_session_found(session_manager, mock_redis):
    """Test retrieving an existing session."""
    session_id = "test-session-id"
    stored_session = Session(
        id=session_id,
        user_id=1,
        tenant_id=1,
        messages=[ChatMessage(role="user", content="hello")],
    )

    # Mock Redis return value
    mock_redis.get.return_value = json.dumps(stored_session.to_dict())

    result = await session_manager.get_session(session_id)

    assert result is not None
    assert result.id == session_id
    assert len(result.messages) == 1
    assert result.messages[0].content == "hello"


@pytest.mark.asyncio
async def test_get_session_not_found(session_manager, mock_redis):
    """Test retrieving a non-existent session."""
    mock_redis.get.return_value = None

    result = await session_manager.get_session("non-existent")

    assert result is None


@pytest.mark.asyncio
async def test_add_message(session_manager, mock_redis):
    """Test adding a message to a session."""
    session_id = "test-session-id"
    initial_session = Session(id=session_id, user_id=1, tenant_id=1)

    # Mock retrieval
    mock_redis.get.return_value = json.dumps(initial_session.to_dict())

    updated_session = await session_manager.add_message(
        session_id=session_id,
        role="user",
        content="Hello world",
        feature_context="chat",
    )

    assert updated_session is not None
    assert len(updated_session.messages) == 1
    assert updated_session.messages[0].content == "Hello world"
    assert updated_session.messages[0].role == "user"
    assert updated_session.current_feature == "chat"

    # Verify update called
    mock_redis.setex.assert_called()


@pytest.mark.asyncio
async def test_check_session_continuity_switch_detected(session_manager, mock_redis):
    """Test detecting context switch."""
    session_id = "test-session-id"
    session = Session(id=session_id, user_id=1, tenant_id=1, current_feature="workflow")

    mock_redis.get.return_value = json.dumps(session.to_dict())

    # Should detect switch
    context = await session_manager.check_session_continuity(
        session_id, "I want to switch to analytics"
    )
    assert context is None

    # Should maintain context
    context = await session_manager.check_session_continuity(session_id, "add a nice step")
    assert context == "workflow"


@pytest.mark.asyncio
async def test_delete_session(session_manager, mock_redis):
    """Test deleting a session."""
    session_id = "test-session-id"
    session = Session(id=session_id, user_id=1, tenant_id=1)

    mock_redis.get.return_value = json.dumps(session.to_dict())

    success = await session_manager.delete_session(session_id)

    assert success is True
    mock_redis.delete.assert_called_once_with(session_manager._session_key(session_id))
    mock_redis.srem.assert_called_once()


@pytest.mark.asyncio
async def test_backup_to_database(session_manager):
    """Test backing up session to database."""
    mock_db = MagicMock(spec=AsyncSession)
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()

    session = Session(
        id="backup-id",
        user_id=1,
        tenant_id=1,
        messages=[ChatMessage(role="user", content="hi")],
    )

    await session_manager.backup_to_database(session, mock_db)

    # Should add Session and 1 Message
    assert mock_db.add.call_count == 2
    mock_db.commit.assert_called_once()
