"""TwinEventBridge -- Bridge between TwinEventBus and RedisPubSubManager.

Subscribes to twin events on the singleton TwinEventBus and forwards them
to Redis Pub/Sub so other services (AgenticFlowService, WebSocket consumers)
can react to twin state changes.

Usage:
    from src.core.learning.wiring.twin_event_bridge import TwinEventBridge

    bridge = TwinEventBridge()
    await bridge.start()
    # ... events are now forwarded
    await bridge.stop()
"""

from typing import Any
from uuid import uuid4

from loguru import logger
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from src.core.events.pubsub_manager import EventType, PubSubMessage, RedisPubSubManager
from src.core.learning.events.event_bus import EventHandler, TwinEventBus, get_twin_event_bus
from src.core.learning.events.twin_events import (
    ConsentChanged,
    CritiqueScoreLow,
    InterventionSuggested,
    ProfileUpdated,
    TwinEvent,
    UserBehaviorTracked,
)
from src.core.shared.config import get_feature_flag
from src.core.utils.best_effort import best_effort


class TwinEventBridge:
    """Bridge that forwards twin events to Redis Pub/Sub and agentic flows.

    The bridge is fail-safe: any forwarding error is logged but does not
    break the twin event bus.
    """

    _REDIS_EVENT_TYPE_MAP: dict[str, EventType] = {
        "twin.user_behavior.tracked": EventType.USER_ACTIVITY,
        "twin.profile.updated": EventType.USER_ACTIVITY,
        "twin.intervention.suggested": EventType.AGENT_MESSAGE,
        "twin.consent.changed": EventType.USER_ACTIVITY,
        "twin.hard_delete.requested": EventType.USER_ACTIVITY,
        "twin.critique.score_low": EventType.AGENT_MESSAGE,
    }

    def __init__(
        self,
        event_bus: TwinEventBus | None = None,
        pubsub: RedisPubSubManager | None = None,
        session_factory: async_sessionmaker[AsyncSession] | None = None,
    ) -> None:
        self._bus = event_bus or get_twin_event_bus()
        self._pubsub = pubsub
        self._handlers: list[tuple[str, EventHandler]] = []
        self._started = False
        self._session_factory = session_factory

    async def _get_pubsub(self) -> RedisPubSubManager | None:
        """Lazy-initialize RedisPubSubManager."""
        if self._pubsub is None:
            try:
                from src.core.events.pubsub_manager import get_pubsub_manager

                self._pubsub = await get_pubsub_manager()
            except Exception as exc:
                logger.warning(
                    "twin_bridge_pubsub_unavailable: %s",
                    exc,
                )
        return self._pubsub

    async def start(self) -> None:
        """Register all bridge handlers on the TwinEventBus."""
        if self._started:
            return

        handlers: list[tuple[str, EventHandler]] = [
            ("twin.user_behavior.tracked", self._on_behavior_tracked),
            ("twin.profile.updated", self._on_profile_updated),
            ("twin.intervention.suggested", self._on_intervention_suggested),
            ("twin.consent.changed", self._on_consent_changed),
            ("twin.hard_delete.requested", self._on_hard_delete_requested),
            ("twin.critique.score_low", self._on_critique_score_low),
            # NOTE: second subscriber on same event -- separate concern (learning persistence).
            # Feature flag is checked per-event inside the handler so it can be toggled at
            # runtime via set_feature_flag("agent_learning") without restarting the bridge.
            ("twin.intervention.suggested", self._on_intervention_suggested_learning),
            ("twin.critique.score_low", self._on_critique_score_low_learning),
        ]

        for event_type, handler in handlers:
            self._bus.subscribe(event_type, handler)
            self._handlers.append((event_type, handler))

        self._started = True
        logger.info(
            "twin_event_bridge_started",
            handler_count=len(handlers),
        )

    async def stop(self) -> None:
        """Unregister all bridge handlers."""
        if not self._started:
            return

        for event_type, handler in self._handlers:
            self._bus.unsubscribe(event_type, handler)

        self._handlers.clear()
        self._started = False
        logger.info("twin_event_bridge_stopped")

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    async def _on_behavior_tracked(self, event: TwinEvent) -> None:
        """Forward behavior tracking events to Redis."""
        await self._forward_to_pubsub(event)

    async def _on_profile_updated(self, event: TwinEvent) -> None:
        """Forward profile update events to Redis and log for agentic flows."""
        await self._forward_to_pubsub(event)
        if isinstance(event, ProfileUpdated):
            logger.debug(
                "twin_profile_updated_for_flows",
                user_id=event.user_id,
                tenant_id=event.tenant_id,
                confidence_level=event.confidence_level,
            )

    async def _on_intervention_suggested(self, event: TwinEvent) -> None:
        """Forward intervention suggestions to Redis and trigger flow awareness."""
        await self._forward_to_pubsub(event)
        if isinstance(event, InterventionSuggested):
            async with best_effort("twin intervention flow trigger"):
                logger.info(
                    "twin_intervention_flow_trigger",
                    user_id=event.user_id,
                    tenant_id=event.tenant_id,
                    intervention_type=event.intervention_type,
                    confidence=event.confidence,
                )

    async def _on_consent_changed(self, event: TwinEvent) -> None:
        """Forward consent changes to Redis."""
        await self._forward_to_pubsub(event)
        if isinstance(event, ConsentChanged):
            logger.info(
                "twin_consent_changed",
                user_id=event.user_id,
                tenant_id=event.tenant_id,
                new_status=event.new_status,
            )

    async def _on_hard_delete_requested(self, event: TwinEvent) -> None:
        """Forward GDPR hard-delete requests to Redis for audit propagation."""
        await self._forward_to_pubsub(event)

    async def _on_critique_score_low(self, event: TwinEvent) -> None:
        """Forward critique-score-low events to Redis for agentic flows."""
        await self._forward_to_pubsub(event)

    async def _on_intervention_suggested_learning(self, event: TwinEvent) -> None:
        """Persist InterventionSuggested as LearningExperience (ADR-025, Task 3.1).

        Gated by FEATURE_AGENT_LEARNING env var / "agent_learning" flag.
        Checked per-event so the flag can be toggled at runtime.
        """
        if not isinstance(event, InterventionSuggested):
            return
        if not get_feature_flag("agent_learning"):
            return
        if not isinstance(event.tenant_id, int) or event.tenant_id <= 0:
            logger.warning(
                "twin_learning_persist_skipped",
                reason="invalid_tenant_id",
                tenant_id=event.tenant_id,
            )
            return

        sf = self._session_factory
        if sf is None:
            from src.core.database.database import db_manager

            sf = db_manager.async_session_maker
        if sf is None:
            logger.warning(
                "twin_learning_persist_skipped",
                reason="no_session_factory",
                tenant_id=event.tenant_id,
                trace_id=event.trace_id,
            )
            return

        async with sf() as session:
            safe_tid = int(event.tenant_id)
            # Set RLS tenant context -- mirrors get_db() pattern in database.py
            await session.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(safe_tid)})
            async with best_effort("twin intervention learning persist", db_session=session):
                from src.core.learning.models import LearningExperience

                experience = LearningExperience(
                    tenant_id=event.tenant_id,
                    event_id=str(uuid4()),
                    event_type="twin.intervention.suggested",
                    agent_id="twin_service",
                    task_type=event.intervention_type,
                    success=True,
                    context={
                        "intervention_type": event.intervention_type,
                        "trace_id": event.trace_id,
                        # NOTE: message excluded -- may contain user-facing PII
                    },
                    metrics={"confidence": event.confidence},
                    confidence=event.confidence,
                )
                session.add(experience)
                await session.commit()
                logger.info(
                    "twin_learning_experience_persisted",
                    tenant_id=event.tenant_id,
                    intervention_type=event.intervention_type,
                )

    async def _on_critique_score_low_learning(self, event: TwinEvent) -> None:
        """Persist CritiqueScoreLow as LearningExperience (ADR-025 gap #2, SP-AGT-009).

        Gated by "agent_learning" feature flag -- runtime-togglebaar, identiek patroon
        aan _on_intervention_suggested_learning.
        """
        if not isinstance(event, CritiqueScoreLow):
            return
        if not get_feature_flag("agent_learning"):
            return
        if not isinstance(event.tenant_id, int) or event.tenant_id <= 0:
            logger.warning(
                "twin_critique_learning_persist_skipped",
                reason="invalid_tenant_id",
                tenant_id=event.tenant_id,
            )
            return

        sf = self._session_factory
        if sf is None:
            from src.core.database.database import db_manager  # noqa: PLC0415

            sf = db_manager.async_session_maker
        if sf is None:
            logger.warning(
                "twin_critique_learning_persist_skipped",
                reason="no_session_factory",
                tenant_id=event.tenant_id,
            )
            return

        async with sf() as session:
            safe_tid = int(event.tenant_id)
            # Set RLS tenant context -- mirrors get_db() pattern in database.py
            await session.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(safe_tid)})
            async with best_effort("twin critique learning persist", db_session=session):
                from src.core.learning.models import LearningExperience  # noqa: PLC0415

                experience = LearningExperience(
                    tenant_id=event.tenant_id,
                    event_id=str(uuid4()),
                    event_type="twin.critique.score_low",
                    agent_id=event.agent_name,
                    task_type="critique_signal",
                    success=False,
                    context={"agent_name": event.agent_name, "trace_id": event.trace_id},
                    metrics={"score": event.score},
                    confidence=event.score,
                )
                session.add(experience)
                await session.commit()
                logger.info(
                    "twin_critique_learning_experience_persisted",
                    tenant_id=event.tenant_id,
                    agent_name=event.agent_name,
                    score=event.score,
                )

    # ------------------------------------------------------------------
    # Forwarding helper
    # ------------------------------------------------------------------

    async def _forward_to_pubsub(self, event: TwinEvent) -> None:
        """Forward a twin event to Redis Pub/Sub (best-effort)."""
        pubsub = await self._get_pubsub()
        if pubsub is None:
            return

        redis_event_type = self._REDIS_EVENT_TYPE_MAP.get(event.event_type, EventType.USER_ACTIVITY)

        data: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "twin_event_type": event.event_type,
            "user_id": event.user_id,
            "trace_id": event.trace_id,
            "timestamp": event.timestamp.isoformat() if event.timestamp else None,
        }

        # Add event-specific fields
        if isinstance(event, UserBehaviorTracked):
            data["behavior_type"] = event.behavior_type
            data["context"] = event.context
        elif isinstance(event, ProfileUpdated):
            data["profile_id"] = event.profile_id
            data["confidence_level"] = event.confidence_level
            data["observation_count"] = event.observation_count
        elif isinstance(event, InterventionSuggested):
            data["intervention_type"] = event.intervention_type
            data["message"] = event.message
            data["confidence"] = event.confidence
        elif isinstance(event, ConsentChanged):
            data["new_status"] = event.new_status

        async with best_effort(f"twin bridge forward {event.event_type}"):
            message = PubSubMessage(
                event_type=redis_event_type,
                data=data,
                source="TwinEventBridge",
                tenant_id=event.tenant_id,
            )
            await pubsub.publish(message)


# Module-level singleton instance
_twin_event_bridge_instance: TwinEventBridge | None = None


async def get_twin_event_bridge(
    event_bus: TwinEventBus | None = None,
    pubsub: RedisPubSubManager | None = None,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> TwinEventBridge:
    """Return the singleton TwinEventBridge instance, creating it if needed."""
    global _twin_event_bridge_instance
    if _twin_event_bridge_instance is None:
        _twin_event_bridge_instance = TwinEventBridge(
            event_bus=event_bus, pubsub=pubsub, session_factory=session_factory
        )
        await _twin_event_bridge_instance.start()
    return _twin_event_bridge_instance


async def shutdown_twin_event_bridge() -> None:
    """Shutdown the singleton TwinEventBridge."""
    global _twin_event_bridge_instance
    if _twin_event_bridge_instance is not None:
        await _twin_event_bridge_instance.stop()
        _twin_event_bridge_instance = None
        logger.info("twin_event_bridge_shutdown_complete")
