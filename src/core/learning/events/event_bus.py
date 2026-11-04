"""
TwinEventBus -- Pub/Sub event bus voor digital twin events.

Pattern: Publish-Subscribe (Pub/Sub)
Voordeel: Services communiceren via events, geen directe coupling

Features:
- Asynchrone handlers (fire-and-forget)
- Subscriber per event_type
- Fail-safe: handler errors worden gelogged maar stoppen de bus niet
- Integration met src/core/events/ via bridge (optioneel)
- Singleton: gedeelde instantie across alle requests

Gebruik:
    bus = get_twin_event_bus()
    bus.subscribe("twin.user_behavior.tracked", my_handler)
    await bus.publish(UserBehaviorTracked(...))
"""

import asyncio
from collections.abc import Callable, Coroutine
from typing import Any

from loguru import logger

from src.core.learning.events.twin_events import TwinEvent

# Type voor async event handlers
EventHandler = Callable[[TwinEvent], Coroutine[Any, Any, None]]  # TODO(TYPE): replace Any with concrete type


class TwinEventBus:
    """
    Lichtgewicht Pub/Sub event bus voor twin events.

    De bus is niet persistent -- events worden niet opgeslagen.
    Voor audit trails gebruik de loguru structured logging.
    """

    def __init__(self) -> None:
        self._subscribers: dict[str, list[EventHandler]] = {}

    def subscribe(self, event_type: str, handler: EventHandler) -> None:
        """
        Registreer een handler voor een event type.

        Args:
            event_type: bijv. "twin.user_behavior.tracked"
            handler: async callable die een TwinEvent ontvangt
        """
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        self._subscribers[event_type].append(handler)
        logger.debug("event_bus_subscribe", event_type=event_type, handler=handler.__name__)

    def unsubscribe(self, event_type: str, handler: EventHandler) -> None:
        """Verwijder een handler voor een event type."""
        if event_type in self._subscribers:
            self._subscribers[event_type] = [
                h for h in self._subscribers[event_type] if h is not handler
            ]

    async def publish(self, event: TwinEvent) -> None:
        """
        Publiceer een event naar alle subscribers.

        Handler errors worden gelogged maar stoppen de bus niet (fail-safe).
        """
        handlers = self._subscribers.get(event.event_type, [])

        if not handlers:
            logger.debug(
                "event_bus_no_handlers",
                event_type=event.event_type,
                trace_id=event.trace_id,
            )
            return

        logger.debug(
            "event_bus_publish",
            event_type=event.event_type,
            user_id=event.user_id,
            tenant_id=event.tenant_id,
            trace_id=event.trace_id,
            handler_count=len(handlers),
        )

        for handler in handlers:
            try:
                await handler(event)
            except Exception as exc:
                logger.error(
                    "event_bus_handler_error",
                    event_type=event.event_type,
                    handler=handler.__name__,
                    trace_id=event.trace_id,
                    error=str(exc),
                )

    async def publish_async(self, event: TwinEvent) -> None:
        """
        Publiceer event als asyncio task (fire-and-forget).

        Gebruik wanneer de caller niet wil wachten op handlers.
        """
        asyncio.create_task(self.publish(event))

    def subscriber_count(self, event_type: str) -> int:
        """Geef het aantal subscribers voor een event type."""
        return len(self._subscribers.get(event_type, []))

    def clear(self) -> None:
        """Verwijder alle subscribers (handig voor tests)."""
        self._subscribers.clear()


# Singleton instance (module-level, lazy-initialized)
_twin_event_bus_instance: TwinEventBus | None = None


def get_twin_event_bus() -> TwinEventBus:
    """Return the singleton TwinEventBus instance.

    Lazy-initialized: created on first call.
    """
    global _twin_event_bus_instance
    if _twin_event_bus_instance is None:
        _twin_event_bus_instance = TwinEventBus()
        logger.debug("twin_event_bus_singleton_created")
    return _twin_event_bus_instance


def reset_twin_event_bus() -> None:
    """Reset the singleton instance (useful for tests)."""
    global _twin_event_bus_instance
    if _twin_event_bus_instance is not None:
        _twin_event_bus_instance.clear()
        _twin_event_bus_instance = None
        logger.debug("twin_event_bus_singleton_reset")
