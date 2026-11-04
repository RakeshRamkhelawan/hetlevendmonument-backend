"""Learning-specific RabbitMQ event handlers."""

from __future__ import annotations

import logging
from typing import Optional

from src.core.agents.learning_loop import LearningSource, LearningType
from src.core.events.publisher import DomainEvent
from src.core.learning.services.observation_service import ObservationService

logger = logging.getLogger(__name__)


class LearningEventHandler:
    """Convert ToolBroker events into learning observations."""

    def __init__(
        self, observation_service: ObservationService | None = None, tenant_id: int | None = None
    ) -> None:
        self._observation_service = observation_service
        self._tenant_id = tenant_id

    @property
    def observation_service(self) -> ObservationService:
        """Return the configured observation service or create a tenant-scoped one."""
        if self._observation_service is None:
            tenant_id = self._tenant_id if self._tenant_id is not None and self._tenant_id > 0 else 1
            self._observation_service = ObservationService(tenant_id=tenant_id)
        return self._observation_service

    async def handle_tool_executed(self, event: DomainEvent) -> str | None:
        """Record a successful tool execution as a learning observation."""
        return await self._record_tool_event(
            event=event,
            learning_type=LearningType.PERFORMANCE_OPTIMIZATION,
        )

    async def handle_tool_failed(self, event: DomainEvent) -> str | None:
        """Record a failed tool execution as an error-correction observation."""
        return await self._record_tool_event(
            event=event,
            learning_type=LearningType.ERROR_CORRECTION,
        )

    async def _record_tool_event(
        self,
        event: DomainEvent,
        learning_type: LearningType,
    ) -> str | None:
        try:
            return await self.observation_service.record(
                source=LearningSource.TASK_EXECUTION,
                learning_type=learning_type,
                context={
                    "agent_id": event.data.get("agent_id"),
                    "agent_type": event.metadata.get("agent_type") if event.metadata else None,
                    "task_type": "tool_execution",
                    "tool_name": event.data.get("tool_name"),
                },
                observation_data={
                    "tool_name": event.data.get("tool_name"),
                    "payload": event.data.get("payload", {}),
                    "result": event.data.get("result"),
                    "error": event.data.get("error"),
                    "success": event.data.get("success", False),
                },
                outcome_metrics={
                    "execution_time": float(event.data.get("duration_seconds", 0.0) or 0.0),
                    "success": 1.0 if event.data.get("success") else 0.0,
                    "error_count": 0.0 if event.data.get("success") else 1.0,
                },
            )
        except Exception as exc:
            logger.warning(
                "Failed to convert tool event %s into observation: %s", event.event_id, exc
            )
            return None
