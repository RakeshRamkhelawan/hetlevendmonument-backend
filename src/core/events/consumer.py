"""
Event Consumer - Redis Pub/Sub-gebaseerde event consumer.
Vervangt de aio_pika/RabbitMQ implementatie conform ADR-006.
"""

import asyncio
from typing import Any, Optional
from collections.abc import Callable

from loguru import logger

from .pubsub_manager import RedisPubSubManager


class EventConsumer:
    """
    Event Consumer die via Redis Pub/Sub luistert naar domain events.
    Vervangt de RabbitMQ-gebaseerde consumer (ADR-006).

    Handlers worden geregistreerd op event_type (bv. "agent.created") en
    worden aangeroepen wanneer een overeenkomstig event binnenkomt via de
    RedisPubSubManager.
    """

    def __init__(
        self, redis_url: str = "", pubsub_manager: RedisPubSubManager | None = None
    ) -> None:
        # redis_url wordt niet meer gebruikt maar blijft voor backward-compatibiliteit
        self.pubsub_manager = pubsub_manager
        self._connected = False
        self._consuming = False
        self._handlers: dict[str, list[Callable[..., Any]]] = {}  # TODO(TYPE): replace Any with concrete type

    EventHandler = Callable[..., Any]  # TODO(TYPE): replace Any with concrete type

    async def connect(self) -> None:
        """Verbind via de gedeelde Redis pub/sub manager."""
        try:
            if self.pubsub_manager is None:
                from .pubsub_manager import get_pubsub_manager
                self.pubsub_manager = await get_pubsub_manager()
            self._connected = True
            logger.info("[OK] Event Consumer verbonden via Redis Pub/Sub")
        except Exception as e:
            logger.error(
                "Event Consumer verbinding mislukt: %s: %s", type(e).__name__, e, exc_info=True
            )
            self._connected = False

    async def disconnect(self) -> None:
        """Verbreek verbinding met de event consumer."""
        await self.stop_consuming()
        self._connected = False
        logger.info("Event Consumer verbroken")

    def register_handler(self, event_type: str, handler: "EventConsumer.EventHandler") -> None:
        """
        Registreer een handler voor een specifiek event type.

        Args:
            event_type: Event type (bv. "agent.created")
            handler: Async functie die een DomainEvent ontvangt
        """
        if event_type not in self._handlers:
            self._handlers[event_type] = []
        self._handlers[event_type].append(handler)
        logger.info("Handler geregistreerd voor event type: %s", event_type)

    def unregister_handler(self, event_type: str, handler: "EventConsumer.EventHandler") -> None:
        """Verwijder een handler voor een event type."""
        if event_type in self._handlers:
            self._handlers[event_type] = [h for h in self._handlers[event_type] if h != handler]

    async def start_consuming(self) -> None:
        """
        Start het consumeren van events.

        In Redis Pub/Sub modus worden handlers geregistreerd via de pubsub_manager.
        Deze methode houdt de consumer actief zodat hij niet stopt.
        """
        self._consuming = True
        logger.info("[OK] Event Consumer gestart (Redis Pub/Sub modus)")
        while self._consuming:
            await asyncio.sleep(5)

    async def stop_consuming(self) -> None:
        """Stop het consumeren van events."""
        self._consuming = False
        logger.info("Event Consumer gestopt")

    async def get_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Geef consumer statistieken terug."""
        return {
            "connected": self._connected,
            "consuming": self._consuming,
            "mode": "redis_pubsub",
            "handlers_registered": {
                event_type: len(handlers) for event_type, handlers in self._handlers.items()
            },
            "total_handlers": sum(len(h) for h in self._handlers.values()),
        }


# Globale consumer instance
_event_consumer: EventConsumer | None = None


async def get_event_consumer(
    redis_url: str = "", pubsub_manager: RedisPubSubManager | None = None
) -> EventConsumer:
    """Geef of maak de globale event consumer instantie.

    Args:
        redis_url: Niet meer gebruikt (backward-compat parameter, wordt genegeerd).
        pubsub_manager: Optionele RedisPubSubManager instantie.
    """
    global _event_consumer

    if _event_consumer is None:
        _event_consumer = EventConsumer(redis_url, pubsub_manager)
        await _event_consumer.connect()

    return _event_consumer
