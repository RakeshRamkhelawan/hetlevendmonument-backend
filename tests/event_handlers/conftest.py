"""Fixtures for Event Handler tests."""

from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from src.core.events.handlers.agent_handler import AgentEventHandler
from src.core.events.handlers.notification_handler import NotificationEventHandler
from src.core.events.handlers.workflow_handler import WorkflowEventHandler
from src.core.events.pubsub_manager import EventType, PubSubMessage, RedisPubSubManager


@pytest_asyncio.fixture
async def mock_pubsub():
    """Mock PubSub manager for isolated tests."""
    pubsub = MagicMock(spec=RedisPubSubManager)
    pubsub.publish = AsyncMock()
    pubsub.subscribe = AsyncMock()
    return pubsub


@pytest_asyncio.fixture
async def workflow_handler(mock_pubsub):
    """Workflow handler with mock pubsub."""
    return WorkflowEventHandler(mock_pubsub)


@pytest_asyncio.fixture
async def notification_handler(mock_pubsub):
    """Notification handler with mock pubsub."""
    return NotificationEventHandler(mock_pubsub)


@pytest_asyncio.fixture
async def agent_handler(mock_pubsub):
    """Agent handler with mock pubsub."""
    return AgentEventHandler(mock_pubsub)


@pytest.fixture
def sample_workflow_message():
    """Sample workflow event message."""
    return PubSubMessage(
        event_type=EventType.WORKFLOW_STARTED,
        data={
            "workflow_id": "wf_test_123",
            "workflow_type": "campaign",
            "initiated_by": "user_456",
        },
        source="test",
        tenant_id=1,
    )


@pytest.fixture
def sample_task_message():
    """Sample task event message."""
    return PubSubMessage(
        event_type=EventType.TASK_CREATED,
        data={
            "task_id": "task_789",
            "workflow_id": "wf_test_123",
            "name": "Design brief",
            "department": "product_innovation",
            "assignee": "user_789",
        },
        source="test",
        tenant_id=1,
    )


@pytest.fixture
def sample_notification_message():
    """Sample notification event message."""
    return PubSubMessage(
        event_type=EventType.USER_LOGGED_IN,
        data={"user_id": "user_123", "email": "test@example.com", "is_first_login": True},
        source="test",
        tenant_id=1,
    )


@pytest.fixture
def sample_agent_message():
    """Sample agent event message."""
    return PubSubMessage(
        event_type=EventType.AGENT_MESSAGE,
        data={"action": "route_task", "task_id": "task_001", "department": "finance"},
        source="test",
        tenant_id=1,
    )
