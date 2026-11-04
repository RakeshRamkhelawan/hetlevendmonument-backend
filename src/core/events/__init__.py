"""
Event System - Domain events via Redis Pub/Sub (ADR-006).
"""

from typing import Any

from .consumer import EventConsumer, get_event_consumer
from .publisher import DomainEvent, EventPublisher, get_event_publisher
from .pubsub_manager import EventType, PubSubMessage, RedisPubSubManager, get_pubsub_manager

__all__ = [
    # Publisher
    "EventPublisher",
    "DomainEvent",
    "get_event_publisher",
    # Consumer
    "EventConsumer",
    "get_event_consumer",
    # Pub/Sub
    "RedisPubSubManager",
    "PubSubMessage",
    "EventType",
    "get_pubsub_manager",
]
