"""
Event Handlers - Domain event handler classes via Redis Pub/Sub (ADR-006).
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from .publisher import DomainEvent
from .pubsub_manager import EventType, PubSubMessage, RedisPubSubManager


class BaseEventHandler(ABC):
    """Base class for event handlers"""

    def __init__(self, pubsub_manager: RedisPubSubManager) -> None:
        self.pubsub = pubsub_manager
        self._registered = False

    @abstractmethod
    async def register_handlers(self) -> None:
        """Register all event handlers for this handler type"""
        pass

    async def _forward_to_pubsub(self, event: DomainEvent, event_type: EventType) -> None:
        """Forward event to Redis pub/sub for WebSocket broadcasting"""
        try:
            tenant_id = event.data.get("tenant_id")
            user_id = event.data.get("user_id")

            message = PubSubMessage(
                event_type=event_type,
                data={
                    **event.data,
                    "event_id": event.event_id,
                    "aggregate_id": event.aggregate_id,
                    "timestamp": event.timestamp.isoformat() if event.timestamp else None,
                },
                source=self.__class__.__name__,
                tenant_id=tenant_id,
                user_id=user_id,
            )

            await self.pubsub.publish(message)
            logger.debug("[OK] Forwarded %s to Redis pub/sub", event.event_type)
        except Exception as e:
            logger.error("Failed to forward to pub/sub: %s: %s", type(e).__name__, e, exc_info=True)


class WorkflowEventHandler(BaseEventHandler):
    """Handler for workflow-related events"""

    async def register_handlers(self) -> None:
        """Register workflow event handlers"""
        await self.pubsub.subscribe("events:workflow:*", self._handle_workflow_event)
        self._registered = True
        logger.info("[OK] WorkflowEventHandler registered")

    async def _handle_workflow_event(self, message: PubSubMessage) -> None:
        """Handle workflow events from pub/sub"""
        event_type = message.event_type
        workflow_id = message.data.get("workflow_id")
        tenant_id = message.tenant_id

        if event_type == EventType.WORKFLOW_STARTED:
            logger.info("[RUN] Workflow started: %s (tenant=%s)", workflow_id, tenant_id)
            # TODO: Update workflow status, notify clients

        elif event_type == EventType.WORKFLOW_COMPLETED:
            logger.info("[OK] Workflow completed: %s (tenant=%s)", workflow_id, tenant_id)
            # TODO: Store results, send notifications

        elif event_type == EventType.WORKFLOW_FAILED:
            logger.error("[FAIL] Workflow failed: %s (tenant=%s)", workflow_id, tenant_id)
            # TODO: Log error, trigger retry if needed

    async def handle_workflow_started(self, event: DomainEvent) -> None:
        """Handle workflow.started event via Redis Pub/Sub"""
        logger.info("[RUN] Workflow started: %s", event.aggregate_id)
        await self._forward_to_pubsub(event, EventType.WORKFLOW_STARTED)

        # TODO: Implement business logic
        # - Update workflow status in DB
        # - Send notification to user
        # - Start monitoring

    async def handle_workflow_completed(self, event: DomainEvent) -> None:
        """Handle workflow.completed event via Redis Pub/Sub"""
        logger.info("[OK] Workflow completed: %s", event.aggregate_id)
        await self._forward_to_pubsub(event, EventType.WORKFLOW_COMPLETED)

        # TODO: Implement business logic
        # - Store results
        # - Send completion notification
        # - Update analytics

    async def handle_workflow_failed(self, event: DomainEvent) -> None:
        """Handle workflow.failed event via Redis Pub/Sub"""
        logger.error("[FAIL] Workflow failed: %s", event.aggregate_id)
        await self._forward_to_pubsub(event, EventType.WORKFLOW_FAILED)

        # TODO: Implement business logic
        # - Log error details
        # - Send failure notification
        # - Trigger retry if applicable


class AgentEventHandler(BaseEventHandler):
    """Handler for agent-related events"""

    async def register_handlers(self) -> None:
        """Register agent event handlers"""
        await self.pubsub.subscribe("events:agent:*", self._handle_agent_event)
        self._registered = True
        logger.info("[OK] AgentEventHandler registered")

    async def _handle_agent_event(self, message: PubSubMessage) -> None:
        """Handle agent events from pub/sub"""
        event_type = message.event_type
        agent_id = message.data.get("agent_id")
        tenant_id = message.tenant_id

        if event_type == EventType.AGENT_REGISTERED:
            logger.info("[OK] Agent registered: %s (tenant=%s)", agent_id, tenant_id)

        elif event_type == EventType.AGENT_STATUS_CHANGED:
            status = message.data.get("status")
            logger.info("[OK] Agent status changed: %s -> %s", agent_id, status)

    async def handle_agent_created(self, event: DomainEvent) -> None:
        """Handle agent.created event via Redis Pub/Sub"""
        logger.info("[OK] Agent created: %s", event.aggregate_id)
        await self._forward_to_pubsub(event, EventType.AGENT_REGISTERED)

        # TODO: Implement business logic
        # - Send welcome notification
        # - Initialize agent state
        # - Log to audit trail

    async def handle_agent_updated(self, event: DomainEvent) -> None:
        """Handle agent.updated event via Redis Pub/Sub"""
        logger.info("[OK] Agent updated: %s", event.aggregate_id)
        await self._forward_to_pubsub(event, EventType.AGENT_STATUS_CHANGED)

        # TODO: Implement business logic
        # - Invalidate caches
        # - Update search index


class NotificationEventHandler(BaseEventHandler):
    """Handler for notification-related events"""

    async def register_handlers(self) -> None:
        """Register notification event handlers"""
        await self.pubsub.subscribe("events:user:*", self._handle_user_event)
        self._registered = True
        logger.info("[OK] NotificationEventHandler registered")

    async def _handle_user_event(self, message: PubSubMessage) -> None:
        """Handle user events for notifications"""
        event_type = message.event_type
        user_id = message.user_id
        tenant_id = message.tenant_id

        if event_type == EventType.USER_LOGGED_IN:
            logger.info("[OK] User logged in: %s (tenant=%s)", user_id, tenant_id)
            # TODO: Send login notification, update presence

        elif event_type == EventType.USER_LOGGED_OUT:
            logger.info("[OK] User logged out: %s", user_id)
            # TODO: Clear sessions, update presence

    async def handle_user_notification(self, event: DomainEvent, notification_type: str) -> None:
        """Generic notification handler"""
        user_id = event.data.get("user_id")
        tenant_id = event.data.get("tenant_id")

        logger.info(
            "[SEND] Sending %s to user %s (tenant=%s)", notification_type, user_id, tenant_id
        )

        # TODO: Implement notification logic
        # - Push notification
        # - Email notification
        # - In-app notification
        # - WebSocket broadcast


class TaskEventHandler(BaseEventHandler):
    """Handler for task-related events"""

    async def register_handlers(self) -> None:
        """Register task event handlers"""
        await self.pubsub.subscribe("events:task:*", self._handle_task_event)
        self._registered = True
        logger.info("[OK] TaskEventHandler registered")

    async def _handle_task_event(self, message: PubSubMessage) -> None:
        """Handle task events from pub/sub"""
        event_type = message.event_type
        task_id = message.data.get("task_id")
        workflow_id = message.data.get("workflow_id")
        tenant_id = message.tenant_id

        if event_type == EventType.TASK_CREATED:
            logger.info("[OK] Task created: %s (workflow=%s)", task_id, workflow_id)

        elif event_type == EventType.TASK_STARTED:
            logger.info("[RUN] Task started: %s", task_id)

        elif event_type == EventType.TASK_COMPLETED:
            logger.info("[OK] Task completed: %s", task_id)

        elif event_type == EventType.TASK_FAILED:
            logger.error("[FAIL] Task failed: %s (tenant=%s)", task_id, tenant_id)


class AuditEventHandler(BaseEventHandler):
    """Handler for audit logging - captures all events"""

    async def register_handlers(self) -> None:
        """Register audit handler for all events"""
        await self.pubsub.subscribe("events:*", self._handle_audit)
        self._registered = True
        logger.info("[OK] AuditEventHandler registered")

    async def _handle_audit(self, message: PubSubMessage) -> None:
        """Log all events to audit trail"""
        audit_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": message.event_type.value,
            "source": message.source,
            "tenant_id": message.tenant_id,
            "user_id": message.user_id,
            "data_summary": {
                k: v for k, v in message.data.items() if k not in ["password", "token", "secret"]
            },
        }

        logger.debug("[AUDIT] %s", audit_entry)
        # TODO: Persist to audit log database


def register_legacy_handlers(consumer: Any) -> None:  # TODO(TYPE): replace Any with concrete type
    """
    Register legacy function-based handlers with the event consumer.

    Args:
        consumer: EventConsumer instance
    """
    consumer.register_handler("agent.created", _handle_agent_created_legacy)
    consumer.register_handler("agent.updated", _handle_agent_updated_legacy)
    consumer.register_handler("workflow.started", _handle_workflow_started_legacy)
    consumer.register_handler("workflow.completed", _handle_workflow_completed_legacy)
    consumer.register_handler("workflow.failed", _handle_workflow_failed_legacy)


# Legacy handlers
async def _handle_agent_created_legacy(event: DomainEvent) -> None:
    """Legacy handler for agent.created"""
    logger.info("[Legacy] Agent created: %s", event.aggregate_id)


async def _handle_agent_updated_legacy(event: DomainEvent) -> None:
    """Legacy handler for agent.updated"""
    logger.info("[Legacy] Agent updated: %s", event.aggregate_id)


async def _handle_workflow_started_legacy(event: DomainEvent) -> None:
    """Legacy handler for workflow.started"""
    logger.info("[Legacy] Workflow started: %s", event.aggregate_id)


async def _handle_workflow_completed_legacy(event: DomainEvent) -> None:
    """Legacy handler for workflow.completed"""
    logger.info("[Legacy] Workflow completed: %s", event.aggregate_id)


async def _handle_workflow_failed_legacy(event: DomainEvent) -> None:
    """Legacy handler for workflow.failed"""
    logger.error("[Legacy] Workflow failed: %s", event.aggregate_id)
