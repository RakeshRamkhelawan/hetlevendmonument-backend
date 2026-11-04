"""
Learning Event Wiring Module

This module wires the LearningEventHandler to the event system.
It registers handlers for tool execution events that trigger learning observations.

Usage:
    from src.core.events.learning_event_wiring import register_learning_event_handlers

    # In application startup:
    await register_learning_event_handlers(pubsub_manager)
"""

from typing import Any, Optional
from uuid import uuid4

from loguru import logger

from src.core.events.handlers.learning_event_handler import LearningEventHandler
from src.core.events.pubsub_manager import EventType, PubSubMessage, RedisPubSubManager


async def register_learning_event_handlers(
    pubsub_manager: RedisPubSubManager,
    tenant_id: int | None = None,
    handler: LearningEventHandler | None = None,
) -> None:
    """
    Register learning event handlers with the pub/sub manager.

    This wires the LearningEventHandler to receive tool execution events
    and convert them to learning observations.

    Args:
        pubsub_manager: The Redis pub/sub manager instance
        tenant_id: Optional tenant ID filter (if None, handles all tenants)
    """
    if handler is None:
        handler = LearningEventHandler(tenant_id=tenant_id)

    # Subscribe to tool execution events
    await pubsub_manager.subscribe("events:tool:*", _create_tool_handler(handler))

    logger.info(f"Learning event handlers registered (tenant_id={tenant_id or 'all'})")


def _create_tool_handler(learning_handler: LearningEventHandler) -> Any:  # TODO(TYPE): replace Any with concrete type
    """Create a handler function for tool events."""

    async def handle_tool_event(message: PubSubMessage) -> None:
        """Handle tool execution events and record learning observations."""
        try:
            event_type = message.event_type
            data = message.data

            # Map event types to learning handler methods
            if event_type in (EventType.TOOL_EXECUTED, "tool.executed"):
                await _handle_tool_executed(learning_handler, data, message.tenant_id)

            elif event_type in (EventType.TOOL_FAILED, "tool.failed"):
                await _handle_tool_failed(learning_handler, data, message.tenant_id)

        except Exception as e:
            # Non-blocking: learning failures should not break event processing
            logger.warning(f"Learning observation failed (non-blocking): {e}")

    return handle_tool_event


async def _handle_tool_executed(
    handler: LearningEventHandler,
    data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    tenant_id: int | None,
) -> None:
    """Handle successful tool execution for learning."""
    from src.core.events.publisher import DomainEvent

    # Create a DomainEvent from the pub/sub message data
    event = DomainEvent(
        event_id=str(uuid4()),
        event_type="tool.executed",
        aggregate_type="tool_execution",
        aggregate_id=data.get("tool_execution_id", "unknown"),
        data={
            "agent_id": data.get("agent_id"),
            "tool_name": data.get("tool_name"),
            "success": True,
            "duration": data.get("duration_seconds", 0.0),
            "result": data.get("result"),
            "tenant_id": tenant_id,
            **data,
        },
    )

    await handler.handle_tool_executed(event)


async def _handle_tool_failed(
    handler: LearningEventHandler,
    data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    tenant_id: int | None,
) -> None:
    """Handle failed tool execution for learning."""
    from src.core.events.publisher import DomainEvent

    event = DomainEvent(
        event_id=str(uuid4()),
        event_type="tool.failed",
        aggregate_type="tool_execution",
        aggregate_id=data.get("tool_execution_id", "unknown"),
        data={
            "agent_id": data.get("agent_id"),
            "tool_name": data.get("tool_name"),
            "success": False,
            "error": data.get("error", "Unknown error"),
            "tenant_id": tenant_id,
            **data,
        },
    )

    await handler.handle_tool_failed(event)


# Global handler registry for application lifecycle management
_learning_handlers_registered = False


async def initialize_learning_events(
    pubsub_manager: RedisPubSubManager,
    tenant_id: int | None = None,
    handler: LearningEventHandler | None = None,
) -> bool:
    """
    Initialize learning event handlers.

    Safe to call multiple times - will only register once.

    Args:
        pubsub_manager: The Redis pub/sub manager instance
        tenant_id: Optional tenant ID filter

    Returns:
        True if handlers were registered, False if already registered
    """
    global _learning_handlers_registered

    if _learning_handlers_registered:
        logger.debug("Learning event handlers already registered")
        return False

    await register_learning_event_handlers(pubsub_manager, tenant_id, handler)
    _learning_handlers_registered = True
    return True


def reset_learning_event_registration() -> None:
    """
    Reset the registration flag. Used for testing.
    """
    global _learning_handlers_registered
    _learning_handlers_registered = False
