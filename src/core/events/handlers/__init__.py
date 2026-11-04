"""Event handler compatibility exports for the monolith event system."""

from datetime import datetime, timezone
from typing import Any, Dict, List, overload
from collections.abc import Awaitable, Callable

from loguru import logger

from src.core.events.handlers.learning_event_handler import LearningEventHandler
from src.core.events.publisher import DomainEvent
from src.core.events.pubsub_manager import EventType, PubSubMessage, RedisPubSubManager

EventHandlerCallable = Callable[..., Awaitable[None]]


class BaseEventHandler:
    """Base class for event handlers."""

    def __init__(self, pubsub_manager: RedisPubSubManager) -> None:
        self.pubsub = pubsub_manager
        self._registered = False

    async def register_handlers(self) -> None:
        """Register the handler callbacks."""
        self._registered = True

    async def _forward_to_pubsub(self, event: DomainEvent, event_type: EventType) -> None:
        """Forward a domain event to the WebSocket pub/sub bus."""
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


class WorkflowEventHandler(BaseEventHandler):
    """Handle workflow events for broadcasting and orchestration."""

    async def register_handlers(self) -> None:
        await self.pubsub.subscribe("events:workflow:*", self._handle_workflow_event)
        self._registered = True
        logger.info("[OK] WorkflowEventHandler registered")

    async def _handle_workflow_event(self, message: PubSubMessage) -> None:
        workflow_id = message.data.get("workflow_id")
        if message.event_type == EventType.WORKFLOW_STARTED:
            logger.info(f"[GEAR] Workflow started: {workflow_id} (tenant={message.tenant_id})")
        elif message.event_type == EventType.WORKFLOW_COMPLETED:
            logger.info(f"[OK] Workflow completed: {workflow_id} (tenant={message.tenant_id})")
        elif message.event_type == EventType.WORKFLOW_FAILED:
            logger.error(f"[FAIL] Workflow failed: {workflow_id} (tenant={message.tenant_id})")

    async def handle_workflow_started(self, event: DomainEvent) -> None:
        await self._forward_to_pubsub(event, EventType.WORKFLOW_STARTED)

    async def handle_workflow_completed(self, event: DomainEvent) -> None:
        await self._forward_to_pubsub(event, EventType.WORKFLOW_COMPLETED)

    async def handle_workflow_failed(self, event: DomainEvent) -> None:
        await self._forward_to_pubsub(event, EventType.WORKFLOW_FAILED)


class AgentEventHandler(BaseEventHandler):
    """Handle agent events for broadcasting and status tracking."""

    async def register_handlers(self) -> None:
        await self.pubsub.subscribe("events:agent:*", self._handle_agent_event)
        self._registered = True
        logger.info("[OK] AgentEventHandler registered")

    async def _handle_agent_event(self, message: PubSubMessage) -> None:
        if message.event_type == EventType.AGENT_REGISTERED:
            logger.info(
                f"[ROBOT] Agent registered: {message.data.get('agent_id')} (tenant={message.tenant_id})"
            )
        elif message.event_type == EventType.AGENT_STATUS_CHANGED:
            logger.info(
                "[ROBOT] Agent status changed: "
                f"{message.data.get('agent_id')} -> {message.data.get('status')}"
            )

    async def handle_agent_created(self, event: DomainEvent) -> None:
        await self._forward_to_pubsub(event, EventType.AGENT_REGISTERED)

    async def handle_agent_updated(self, event: DomainEvent) -> None:
        await self._forward_to_pubsub(event, EventType.AGENT_STATUS_CHANGED)


class NotificationEventHandler(BaseEventHandler):
    """Handle notification-related user events."""

    async def register_handlers(self) -> None:
        await self.pubsub.subscribe("events:user:*", self._handle_user_event)
        self._registered = True
        logger.info("[OK] NotificationEventHandler registered")

    async def _handle_user_event(self, message: PubSubMessage) -> None:
        if message.event_type == EventType.USER_LOGGED_IN:
            logger.info(f"[U+0001F464] User logged in: {message.user_id} (tenant={message.tenant_id})")
        elif message.event_type == EventType.USER_LOGGED_OUT:
            logger.info(f"[U+0001F464] User logged out: {message.user_id}")

    async def handle_user_notification(self, event: DomainEvent, notification_type: str) -> None:
        logger.info(f"[EMAIL] Sending {notification_type} to user {event.data.get('user_id')}")


class TaskEventHandler(BaseEventHandler):
    """Handle task lifecycle events."""

    async def register_handlers(self) -> None:
        await self.pubsub.subscribe("events:task:*", self._handle_task_event)
        self._registered = True
        logger.info("[OK] TaskEventHandler registered")

    async def _handle_task_event(self, message: PubSubMessage) -> None:
        task_id = message.data.get("task_id")
        if message.event_type == EventType.TASK_CREATED:
            logger.info(f"[LIST] Task created: {task_id}")
        elif message.event_type == EventType.TASK_STARTED:
            logger.info(f"> Task started: {task_id}")
        elif message.event_type == EventType.TASK_COMPLETED:
            logger.info(f"[OK] Task completed: {task_id}")
        elif message.event_type == EventType.TASK_FAILED:
            logger.error(f"[FAIL] Task failed: {task_id}")


class AuditEventHandler(BaseEventHandler):
    """Handle audit logging for all events."""

    async def register_handlers(self) -> None:
        await self.pubsub.subscribe("events:*", self._handle_audit)
        self._registered = True
        logger.info("[OK] AuditEventHandler registered")

    async def _handle_audit(self, message: PubSubMessage) -> None:
        audit_entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": message.event_type.value,
            "source": message.source,
            "tenant_id": message.tenant_id,
            "user_id": message.user_id,
            "data_summary": {
                key: value
                for key, value in message.data.items()
                if key not in {"password", "token", "secret"}
            },
        }
        logger.debug(f"[NOTE] Audit: {audit_entry}")


_event_handlers: dict[str, list[EventHandlerCallable]] = {}


@overload
def register_handler(
    event_type: str,
) -> Callable[[EventHandlerCallable], EventHandlerCallable]: ...

@overload
def register_handler(
    event_type: str, handler: EventHandlerCallable
) -> EventHandlerCallable: ...

def register_handler(
    event_type: str, handler: EventHandlerCallable | None = None
) -> EventHandlerCallable | Callable[[EventHandlerCallable], EventHandlerCallable]:
    """Register a function handler directly or via decorator syntax."""

    def decorator(callback: EventHandlerCallable) -> EventHandlerCallable:
        _event_handlers.setdefault(event_type, []).append(callback)
        logger.info(f"Registered handler for event: {event_type}")
        return callback

    if handler is not None:
        return decorator(handler)

    return decorator


def get_handlers(event_type: str) -> list[EventHandlerCallable]:
    """Return registered function handlers for an event type."""
    return _event_handlers.get(event_type, [])


def register_event_handlers() -> None:
    """Register built-in function handlers during application startup."""

    @register_handler("agent.created")
    async def on_agent_created(event_data: dict[str, Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        logger.info(f"Handler: Agent created - {event_data.get('agent_id')}")

    @register_handler("agent.updated")
    async def on_agent_updated(event_data: dict[str, Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        logger.info(f"Handler: Agent updated - {event_data.get('agent_id')}")

    @register_handler("workflow.started")
    async def on_workflow_started(event_data: dict[str, Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        logger.info(f"Handler: Workflow started - {event_data.get('workflow_id')}")

    @register_handler("workflow.completed")
    async def on_workflow_completed(event_data: dict[str, Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        logger.info(f"Handler: Workflow completed - {event_data.get('workflow_id')}")

    logger.info("[OK] All event handlers registered")


def register_legacy_handlers(consumer: Any) -> None:  # TODO(TYPE): replace Any with concrete type
    """Register RabbitMQ-compatible legacy handlers."""
    consumer.register_handler("agent.created", _handle_agent_created_legacy)
    consumer.register_handler("agent.updated", _handle_agent_updated_legacy)
    consumer.register_handler("workflow.started", _handle_workflow_started_legacy)
    consumer.register_handler("workflow.completed", _handle_workflow_completed_legacy)
    consumer.register_handler("workflow.failed", _handle_workflow_failed_legacy)


async def _handle_agent_created_legacy(event: DomainEvent) -> None:
    logger.info(f"[Legacy] Agent created: {event.aggregate_id}")


async def _handle_agent_updated_legacy(event: DomainEvent) -> None:
    logger.info(f"[Legacy] Agent updated: {event.aggregate_id}")


async def _handle_workflow_started_legacy(event: DomainEvent) -> None:
    logger.info(f"[Legacy] Workflow started: {event.aggregate_id}")


async def _handle_workflow_completed_legacy(event: DomainEvent) -> None:
    logger.info(f"[Legacy] Workflow completed: {event.aggregate_id}")


async def _handle_workflow_failed_legacy(event: DomainEvent) -> None:
    logger.error(f"[Legacy] Workflow failed: {event.aggregate_id}")


__all__ = [
    "AgentEventHandler",
    "AuditEventHandler",
    "BaseEventHandler",
    "LearningEventHandler",
    "NotificationEventHandler",
    "TaskEventHandler",
    "WorkflowEventHandler",
    "get_handlers",
    "register_event_handlers",
    "register_handler",
    "register_legacy_handlers",
]
