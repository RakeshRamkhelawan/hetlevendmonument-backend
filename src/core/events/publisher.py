"""
Event Publisher - Publishes domain events via Redis Pub/Sub.
Vervangt de aio_pika/RabbitMQ implementatie conform ADR-006.
"""

from datetime import datetime, timezone
from typing import Any, Optional

from loguru import logger
from pydantic import BaseModel, Field

from .pubsub_manager import EventType, PubSubMessage, RedisPubSubManager, get_pubsub_manager


class DomainEvent(BaseModel):
    """Base domain event model"""

    event_id: str
    event_type: str
    aggregate_id: str
    aggregate_type: str
    data: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type


class EventPublisher:
    """
    Event Publisher voor domain events via Redis Pub/Sub.
    Vervangt de RabbitMQ-gebaseerde publisher (ADR-006).
    """

    def __init__(self, pubsub_manager: RedisPubSubManager | None = None) -> None:
        self._pubsub_manager = pubsub_manager
        self._connected = False

    async def connect(self) -> None:
        """Initialiseer via de gedeelde Redis pub/sub manager."""
        try:
            if self._pubsub_manager is None:
                self._pubsub_manager = await get_pubsub_manager()
            self._connected = True
            logger.info("[OK] Event Publisher verbonden via Redis Pub/Sub")
        except Exception as e:
            logger.error(
                "Event Publisher verbinding mislukt: %s: %s", type(e).__name__, e, exc_info=True
            )
            self._connected = False

    async def disconnect(self) -> None:
        """Verbreek verbinding (no-op: Redis manager is gedeeld)."""
        self._connected = False
        logger.info("Event Publisher verbroken")

    async def publish(self, event: DomainEvent, routing_key: str | None = None) -> None:
        """
        Publiceer een domain event naar Redis Pub/Sub.

        Args:
            event: Domain event om te publiceren
            routing_key: Optionele routing key (standaard event_type)
        """
        if not self._connected:
            await self.connect()

        if not self._connected or self._pubsub_manager is None:
            logger.warning("Kan event %s niet publiceren: niet verbonden", event.event_id)
            return

        try:
            event_type = self._map_to_pubsub_type(routing_key or event.event_type)
            message = PubSubMessage(
                event_type=event_type,
                data={
                    **event.data,
                    "event_id": event.event_id,
                    "aggregate_id": event.aggregate_id,
                    "aggregate_type": event.aggregate_type,
                    "timestamp": event.timestamp.isoformat(),
                },
                source="event_publisher",
                tenant_id=event.data.get("tenant_id"),
                user_id=event.data.get("user_id"),
            )
            await self._pubsub_manager.publish(message)
            logger.info("[OK] Event gepubliceerd: %s (ID: %s)", event.event_type, event.event_id)
        except Exception as e:
            logger.error(
                "Event publiceren mislukt voor %s: %s: %s",
                event.event_id,
                type(e).__name__,
                e,
                exc_info=True,
            )

    def _map_to_pubsub_type(self, event_type: str) -> EventType:
        """Map domain event type naar Redis Pub/Sub EventType."""
        mapping = {
            "agent.created": EventType.AGENT_REGISTERED,
            "agent.updated": EventType.AGENT_STATUS_CHANGED,
            "workflow.started": EventType.WORKFLOW_STARTED,
            "workflow.completed": EventType.WORKFLOW_COMPLETED,
            "workflow.failed": EventType.WORKFLOW_FAILED,
            "task.created": EventType.TASK_CREATED,
            "task.started": EventType.TASK_STARTED,
            "task.completed": EventType.TASK_COMPLETED,
            "task.failed": EventType.TASK_FAILED,
            "user.logged_in": EventType.USER_LOGGED_IN,
            "user.logged_out": EventType.USER_LOGGED_OUT,
            "tool.executed": EventType.TOOL_EXECUTED,
            "tool.failed": EventType.TOOL_FAILED,
        }
        return mapping.get(event_type, EventType.SYSTEM_ALERT)

    async def publish_agent_created(self, agent_id: str, agent_data: dict[str, Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        """Publiceer AgentCreated event"""
        event = DomainEvent(
            event_id=f"evt_{agent_id}_{datetime.now(timezone.utc).timestamp()}",
            event_type="agent.created",
            aggregate_id=agent_id,
            aggregate_type="Agent",
            data=agent_data,
        )
        await self.publish(event, routing_key="agent.created")

    async def publish_agent_updated(self, agent_id: str, agent_data: dict[str, Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        """Publiceer AgentUpdated event"""
        event = DomainEvent(
            event_id=f"evt_{agent_id}_{datetime.now(timezone.utc).timestamp()}",
            event_type="agent.updated",
            aggregate_id=agent_id,
            aggregate_type="Agent",
            data=agent_data,
        )
        await self.publish(event, routing_key="agent.updated")

    async def publish_workflow_started(
        self, workflow_id: str, workflow_data: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Publiceer WorkflowStarted event"""
        event = DomainEvent(
            event_id=f"evt_{workflow_id}_{datetime.now(timezone.utc).timestamp()}",
            event_type="workflow.started",
            aggregate_id=workflow_id,
            aggregate_type="Workflow",
            data=workflow_data,
        )
        await self.publish(event, routing_key="workflow.started")

    async def publish_workflow_completed(
        self, workflow_id: str, result_data: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Publiceer WorkflowCompleted event"""
        event = DomainEvent(
            event_id=f"evt_{workflow_id}_{datetime.now(timezone.utc).timestamp()}",
            event_type="workflow.completed",
            aggregate_id=workflow_id,
            aggregate_type="Workflow",
            data=result_data,
        )
        await self.publish(event, routing_key="workflow.completed")

    async def publish_prediction_requested(
        self, request_id: str, request_data: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Publiceer PredictionRequested event"""
        event = DomainEvent(
            event_id=f"evt_{request_id}_{datetime.now(timezone.utc).timestamp()}",
            event_type="ml.prediction_requested",
            aggregate_id=request_id,
            aggregate_type="MLPrediction",
            data=request_data,
        )
        await self.publish(event, routing_key="ml.prediction_requested")


# Globale publisher instance
_event_publisher: EventPublisher | None = None


async def get_event_publisher(
    redis_url: str = "", pubsub_manager: RedisPubSubManager | None = None
) -> EventPublisher:
    """Geef of maak de globale event publisher instantie.

    Args:
        redis_url: Niet meer gebruikt (backward-compat parameter, wordt genegeerd).
        pubsub_manager: Optionele RedisPubSubManager instantie.
    """
    global _event_publisher

    if _event_publisher is None:
        _event_publisher = EventPublisher(pubsub_manager)
        await _event_publisher.connect()

    return _event_publisher
