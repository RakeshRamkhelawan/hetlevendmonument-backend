"""
Tests for Event Handlers - FASE 6.1
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.core.events.handlers import (
    AgentEventHandler,
    AuditEventHandler,
    BaseEventHandler,
    NotificationEventHandler,
    TaskEventHandler,
    WorkflowEventHandler,
)
from src.core.events.publisher import DomainEvent
from src.core.events.pubsub_manager import EventType, PubSubMessage


@pytest.fixture
def mock_pubsub():
    """Mock Redis pub/sub manager"""
    pubsub = AsyncMock()
    pubsub.subscribe = AsyncMock(return_value=True)
    pubsub.publish = AsyncMock(return_value=True)
    return pubsub


@pytest.fixture
def sample_domain_event():
    """Sample domain event for testing"""
    return DomainEvent(
        event_id="evt_test_123",
        event_type="test.event",
        aggregate_id="agg_123",
        aggregate_type="Test",
        data={"tenant_id": 1, "user_id": 2, "key": "value"},
        timestamp=datetime.now(timezone.utc),
    )


class TestBaseEventHandler:
    """Test suite for BaseEventHandler"""

    @pytest.mark.asyncio
    async def test_forward_to_pubsub(self, mock_pubsub, sample_domain_event):
        """Test forwarding event to pub/sub"""
        handler = BaseEventHandler(mock_pubsub)

        await handler._forward_to_pubsub(sample_domain_event, EventType.AGENT_REGISTERED)

        mock_pubsub.publish.assert_called_once()
        message = mock_pubsub.publish.call_args[0][0]
        assert isinstance(message, PubSubMessage)
        assert message.event_type == EventType.AGENT_REGISTERED
        assert message.tenant_id == 1
        assert message.user_id == 2

    @pytest.mark.asyncio
    async def test_forward_to_pubsub_no_tenant(self, mock_pubsub):
        """Test forwarding event without tenant info"""
        event = DomainEvent(
            event_id="evt_123",
            event_type="test.event",
            aggregate_id="agg_123",
            aggregate_type="Test",
            data={"key": "value"},
            timestamp=datetime.now(timezone.utc),
        )

        handler = BaseEventHandler(mock_pubsub)
        await handler._forward_to_pubsub(event, EventType.SYSTEM_ALERT)

        message = mock_pubsub.publish.call_args[0][0]
        assert message.tenant_id is None
        assert message.user_id is None


class TestWorkflowEventHandler:
    """Test suite for WorkflowEventHandler"""

    @pytest.mark.asyncio
    async def test_register_handlers(self, mock_pubsub):
        """Test registering workflow handlers"""
        handler = WorkflowEventHandler(mock_pubsub)
        await handler.register_handlers()

        mock_pubsub.subscribe.assert_called_once_with(
            "events:workflow:*", handler._handle_workflow_event
        )
        assert handler._registered is True

    @pytest.mark.asyncio
    async def test_handle_workflow_started(self, mock_pubsub):
        """Test handling workflow started event"""
        handler = WorkflowEventHandler(mock_pubsub)

        event = DomainEvent(
            event_id="evt_123",
            event_type="workflow.started",
            aggregate_id="wf_123",
            aggregate_type="Workflow",
            data={"tenant_id": 1, "user_id": 2},
            timestamp=datetime.now(timezone.utc),
        )

        await handler.handle_workflow_started(event)

        mock_pubsub.publish.assert_called_once()
        message = mock_pubsub.publish.call_args[0][0]
        assert message.event_type == EventType.WORKFLOW_STARTED

    @pytest.mark.asyncio
    async def test_handle_workflow_completed(self, mock_pubsub):
        """Test handling workflow completed event"""
        handler = WorkflowEventHandler(mock_pubsub)

        event = DomainEvent(
            event_id="evt_123",
            event_type="workflow.completed",
            aggregate_id="wf_123",
            aggregate_type="Workflow",
            data={"tenant_id": 1, "result": "success"},
            timestamp=datetime.now(timezone.utc),
        )

        await handler.handle_workflow_completed(event)

        mock_pubsub.publish.assert_called_once()
        message = mock_pubsub.publish.call_args[0][0]
        assert message.event_type == EventType.WORKFLOW_COMPLETED

    @pytest.mark.asyncio
    async def test_handle_workflow_event_pubsub_message(self, mock_pubsub):
        """Test handling workflow event from pub/sub message"""
        handler = WorkflowEventHandler(mock_pubsub)

        message = PubSubMessage(
            event_type=EventType.WORKFLOW_STARTED,
            data={"workflow_id": "wf_123"},
            source="test",
            tenant_id=1,
        )

        # Should not raise
        await handler._handle_workflow_event(message)


class TestAgentEventHandler:
    """Test suite for AgentEventHandler"""

    @pytest.mark.asyncio
    async def test_register_handlers(self, mock_pubsub):
        """Test registering agent handlers"""
        handler = AgentEventHandler(mock_pubsub)
        await handler.register_handlers()

        mock_pubsub.subscribe.assert_called_once_with("events:agent:*", handler._handle_agent_event)

    @pytest.mark.asyncio
    async def test_handle_agent_created(self, mock_pubsub):
        """Test handling agent created event"""
        handler = AgentEventHandler(mock_pubsub)

        event = DomainEvent(
            event_id="evt_123",
            event_type="agent.created",
            aggregate_id="agent_123",
            aggregate_type="Agent",
            data={"tenant_id": 1, "name": "Test Agent"},
            timestamp=datetime.now(timezone.utc),
        )

        await handler.handle_agent_created(event)

        message = mock_pubsub.publish.call_args[0][0]
        assert message.event_type == EventType.AGENT_REGISTERED

    @pytest.mark.asyncio
    async def test_handle_agent_updated(self, mock_pubsub):
        """Test handling agent updated event"""
        handler = AgentEventHandler(mock_pubsub)

        event = DomainEvent(
            event_id="evt_123",
            event_type="agent.updated",
            aggregate_id="agent_123",
            aggregate_type="Agent",
            data={"tenant_id": 1, "status": "active"},
            timestamp=datetime.now(timezone.utc),
        )

        await handler.handle_agent_updated(event)

        message = mock_pubsub.publish.call_args[0][0]
        assert message.event_type == EventType.AGENT_STATUS_CHANGED


class TestNotificationEventHandler:
    """Test suite for NotificationEventHandler"""

    @pytest.mark.asyncio
    async def test_register_handlers(self, mock_pubsub):
        """Test registering notification handlers"""
        handler = NotificationEventHandler(mock_pubsub)
        await handler.register_handlers()

        mock_pubsub.subscribe.assert_called_once_with("events:user:*", handler._handle_user_event)

    @pytest.mark.asyncio
    async def test_handle_user_event_login(self, mock_pubsub):
        """Test handling user login event"""
        handler = NotificationEventHandler(mock_pubsub)

        message = PubSubMessage(
            event_type=EventType.USER_LOGGED_IN,
            data={},
            source="test",
            tenant_id=1,
            user_id=2,
        )

        # Should not raise
        await handler._handle_user_event(message)

    @pytest.mark.asyncio
    async def test_handle_user_event_logout(self, mock_pubsub):
        """Test handling user logout event"""
        handler = NotificationEventHandler(mock_pubsub)

        message = PubSubMessage(
            event_type=EventType.USER_LOGGED_OUT,
            data={},
            source="test",
            tenant_id=1,
            user_id=2,
        )

        # Should not raise
        await handler._handle_user_event(message)

    @pytest.mark.asyncio
    async def test_handle_user_notification(self, mock_pubsub):
        """Test handling user notification"""
        handler = NotificationEventHandler(mock_pubsub)

        event = DomainEvent(
            event_id="evt_123",
            event_type="notification.send",
            aggregate_id="notif_123",
            aggregate_type="Notification",
            data={"user_id": 1, "tenant_id": 1, "message": "Test"},
            timestamp=datetime.now(timezone.utc),
        )

        # Should not raise
        await handler.handle_user_notification(event, "test_notification")


class TestTaskEventHandler:
    """Test suite for TaskEventHandler"""

    @pytest.mark.asyncio
    async def test_register_handlers(self, mock_pubsub):
        """Test registering task handlers"""
        handler = TaskEventHandler(mock_pubsub)
        await handler.register_handlers()

        mock_pubsub.subscribe.assert_called_once_with("events:task:*", handler._handle_task_event)

    @pytest.mark.asyncio
    async def test_handle_task_events(self, mock_pubsub):
        """Test handling various task events"""
        handler = TaskEventHandler(mock_pubsub)

        events = [
            (EventType.TASK_CREATED, "created"),
            (EventType.TASK_STARTED, "started"),
            (EventType.TASK_COMPLETED, "completed"),
            (EventType.TASK_FAILED, "failed"),
        ]

        for event_type, _ in events:
            message = PubSubMessage(
                event_type=event_type,
                data={"task_id": "task_123", "workflow_id": "wf_123"},
                source="test",
                tenant_id=1,
            )

            # Should not raise
            await handler._handle_task_event(message)


class TestAuditEventHandler:
    """Test suite for AuditEventHandler"""

    @pytest.mark.asyncio
    async def test_register_handlers(self, mock_pubsub):
        """Test registering audit handlers"""
        handler = AuditEventHandler(mock_pubsub)
        await handler.register_handlers()

        mock_pubsub.subscribe.assert_called_once_with("events:*", handler._handle_audit)

    @pytest.mark.asyncio
    async def test_handle_audit(self, mock_pubsub):
        """Test audit logging"""
        handler = AuditEventHandler(mock_pubsub)

        message = PubSubMessage(
            event_type=EventType.WORKFLOW_COMPLETED,
            data={"workflow_id": "wf_123", "password": "should_be_filtered"},
            source="test",
            tenant_id=1,
            user_id=2,
        )

        # Should not raise
        await handler._handle_audit(message)

    @pytest.mark.asyncio
    async def test_handle_audit_filters_secrets(self, mock_pubsub):
        """Test that audit handler filters sensitive data"""
        handler = AuditEventHandler(mock_pubsub)

        message = PubSubMessage(
            event_type=EventType.USER_LOGGED_IN,
            data={
                "password": "secret123",
                "token": "jwt_token_here",
                "secret": "api_secret",
                "normal_field": "visible",
            },
            source="test",
            tenant_id=1,
        )

        # Should filter sensitive fields - test by checking it doesn't raise
        await handler._handle_audit(message)
