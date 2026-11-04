"""
Redis Pub/Sub Manager - Real-time Event Broadcasting
Enables agent communication, workflow events, and real-time updates across services.
Uses Redis pub/sub for distributed messaging.
"""

import asyncio
import json
import logging
from datetime import UTC, datetime
from enum import Enum
from typing import Any
from collections.abc import Awaitable, Callable

import redis.asyncio as redis

from src.core.config.config import get_settings

logger = logging.getLogger(__name__)


class EventType(str, Enum):
    """Pub/Sub event types for different services"""

    # Workflow events
    WORKFLOW_CREATED = "workflow:created"
    WORKFLOW_UPDATED = "workflow:updated"
    WORKFLOW_STARTED = "workflow:started"
    WORKFLOW_COMPLETED = "workflow:completed"
    WORKFLOW_FAILED = "workflow:failed"
    WORKFLOW_PAUSED = "workflow:paused"
    WORKFLOW_RESUMED = "workflow:resumed"

    # Task events
    TASK_CREATED = "task:created"
    TASK_STARTED = "task:started"
    TASK_COMPLETED = "task:completed"
    TASK_FAILED = "task:failed"

    # Agent events
    AGENT_REGISTERED = "agent:registered"
    AGENT_ACTIVATED = "agent:activated"
    AGENT_DEACTIVATED = "agent:deactivated"
    AGENT_MESSAGE = "agent:message"
    AGENT_STATUS_CHANGED = "agent:status_changed"

    # System events
    SYSTEM_HEALTH_CHECK = "system:health_check"
    SYSTEM_ALERT = "system:alert"
    CACHE_INVALIDATION = "cache:invalidation"

    # User events
    USER_LOGGED_IN = "user:logged_in"
    USER_LOGGED_OUT = "user:logged_out"
    USER_ACTIVITY = "user:activity"

    # Tool events
    TOOL_EXECUTED = "tool:executed"
    TOOL_FAILED = "tool:failed"


class PubSubMessage:
    """Structured pub/sub message"""

    def __init__(
        self,
        event_type: EventType,
        data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        source: str,
        tenant_id: int | None = None,
        user_id: int | None = None,
    ) -> None:
        self.event_type = event_type
        self.data = data
        self.source = source
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.timestamp = datetime.now(UTC).isoformat()

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert message to dictionary for JSON serialization"""
        return {
            "event_type": self.event_type.value,
            "data": self.data,
            "source": self.source,
            "tenant_id": self.tenant_id,
            "user_id": self.user_id,
            "timestamp": self.timestamp,
        }

    def to_json(self) -> str:
        """Serialize message to JSON"""
        return json.dumps(self.to_dict(), ensure_ascii=True)

    @classmethod
    def from_json(cls, json_str: str) -> "PubSubMessage":
        """Deserialize message from JSON"""
        data = json.loads(json_str)
        return cls(
            event_type=EventType(data["event_type"]),
            data=data["data"],
            source=data["source"],
            tenant_id=data.get("tenant_id"),
            user_id=data.get("user_id"),
        )


class RedisPubSubManager:
    """
    Production-grade pub/sub manager using Redis.
    Enables real-time communication between agents, workflows, and services.
    """

    # Channel patterns
    GLOBAL_CHANNEL = "events:global"
    TENANT_CHANNEL_PREFIX = "events:tenant:"
    USER_CHANNEL_PREFIX = "events:user:"
    AGENT_CHANNEL_PREFIX = "events:agent:"
    WORKFLOW_CHANNEL_PREFIX = "events:workflow:"
    TOOL_CHANNEL_PREFIX = "events:tool:"

    def __init__(self, redis_client: redis.Redis | None = None) -> None:  # type: ignore[type-arg]
        """
        Initialize pub/sub manager.

        Args:
            redis_client: Existing Redis client (created if None)
        """
        self.redis_client = redis_client
        self.pubsub: object | None = None
        self.connected = False
        self.subscribers: dict[
            str,
            list[
                Callable[[PubSubMessage], Awaitable[object]]
            ],  # TODO(TYPE): replace Any with concrete type
        ] = {}  # TODO(TYPE): replace Any with concrete type
        self.listening_task: asyncio.Task[None] | None = None
        self._stop_listening: bool = False

    async def connect(self) -> bool:
        """Establish Redis connection if not provided"""
        if self.redis_client is not None:
            self.connected = True
            return True

        try:
            settings = get_settings()
            self.redis_client = redis.Redis.from_url(
                settings.redis_url,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5,
                max_connections=10,
            )
            await self.redis_client.ping()
            self.connected = True
            logger.info("Pub/Sub manager connected to Redis")
            return True
        except Exception as e:
            logger.error(f"Failed to connect pub/sub manager: {e}")
            self.connected = False
            return False

    async def disconnect(self) -> None:
        """Close Redis connection"""
        await self.stop_listening()

        if self.redis_client:
            try:
                client: Any = self.redis_client  # TODO(TYPE): replace Any with concrete type
                await client.aclose()
                self.connected = False
                logger.info("Pub/Sub manager disconnected")
            except Exception as e:
                logger.error(f"Error disconnecting pub/sub manager: {e}")

    async def publish(
        self,
        message: PubSubMessage | None = None,
        *,
        event_type: EventType | None = None,
        data: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        source: str | None = None,
        tenant_id: int | None = None,
        user_id: int | None = None,
    ) -> bool:
        """
        Publish event message to all relevant channels.

        Accepts either a PubSubMessage object or individual keyword arguments.

        Args:
            message: PubSubMessage to publish (positional)
            event_type: Event type (keyword, used when message is None)
            data: Event data dict (keyword, used when message is None)
            source: Event source string (keyword, used when message is None)
            tenant_id: Optional tenant ID (keyword)
            user_id: Optional user ID (keyword)

        Returns:
            True if published successfully
        """
        if message is None:
            if event_type is None or data is None or source is None:
                logger.warning(
                    "Pub/Sub publish requires either a PubSubMessage "
                    "or event_type, data, and source kwargs"
                )
                return False
            message = PubSubMessage(
                event_type=event_type,
                data=data,
                source=source,
                tenant_id=tenant_id,
                user_id=user_id,
            )
        if not self.connected:
            logger.warning("Pub/Sub manager not connected")
            return False

        try:
            channels = [self.GLOBAL_CHANNEL]

            # Add tenant-specific channel
            if message.tenant_id:
                channels.append(f"{self.TENANT_CHANNEL_PREFIX}{message.tenant_id}")

            # Add user-specific channel
            if message.user_id:
                channels.append(f"{self.USER_CHANNEL_PREFIX}{message.user_id}")

            # Add event-type specific channels
            if message.event_type in [
                EventType.AGENT_MESSAGE,
                EventType.AGENT_STATUS_CHANGED,
            ]:
                channels.append(f"{self.AGENT_CHANNEL_PREFIX}*")

            if message.event_type.value.startswith("workflow:"):
                channels.append(
                    f"{self.WORKFLOW_CHANNEL_PREFIX}{message.data.get('workflow_id', '*')}"
                )

            if message.event_type.value.startswith("tool:"):
                # Tenant-scoped channel so subscribers receive only their own tool events.
                # Matches psubscribe pattern "events:tool:*" in learning_event_wiring.
                tenant_key = str(message.tenant_id) if message.tenant_id else "global"
                channels.append(f"{self.TOOL_CHANNEL_PREFIX}{tenant_key}")

            # Publish to all relevant channels
            if self.redis_client is None:
                return False
            message_json = message.to_json()
            for channel in channels:
                await self.redis_client.publish(channel, message_json)

            logger.debug(f"Published {message.event_type} to {len(channels)} channels")
            return True

        except Exception as e:
            logger.error(f"Failed to publish message: {e}")
            return False

    async def subscribe(
        self,
        channel_pattern: str,
        handler: Callable[
            [PubSubMessage], Awaitable[Any]  # TODO(TYPE): replace Any with concrete type
        ],  # TODO(TYPE): replace Any with concrete type
    ) -> bool:
        """
        Subscribe to channel(s) with event handler.

        Args:
            channel_pattern: Channel name or pattern (with *)
            handler: Async callable to handle messages

        Returns:
            True if subscription successful
        """
        if not self.connected:
            logger.warning("Pub/Sub manager not connected")
            return False

        try:
            if channel_pattern not in self.subscribers:
                self.subscribers[channel_pattern] = []

            self.subscribers[channel_pattern].append(handler)
            logger.info(f"Subscribed to channel: {channel_pattern}")
            return True

        except Exception as e:
            logger.error(f"Failed to subscribe to {channel_pattern}: {e}")
            return False

    async def start_listening(self) -> None:
        """Start listening for published messages"""
        if not self.connected:
            logger.warning("Cannot start listening - not connected")
            return

        if self.redis_client is None:
            logger.warning("Cannot start listening - Redis client not available")
            return
        pubsub: Any = None
        message: Any = None
        try:
            self._stop_listening = False

            # Create pub/sub connection (separate from main connection)
            pubsub = self.redis_client.pubsub()

            # Subscribe to all registered channels
            for channel_pattern in self.subscribers.keys():
                await pubsub.psubscribe(channel_pattern)
                logger.info(f"Subscribed to pattern: {channel_pattern}")

            # Listen for messages
            async for message in pubsub.listen():
                if self._stop_listening:
                    break

                if message is not None and message.get("type") == "pmessage":
                    try:
                        msg = PubSubMessage.from_json(message.get("data", "{}"))
                        handlers = self.subscribers.get(message.get("pattern", ""), [])

                        # Call all handlers asynchronously
                        tasks = [handler(msg) for handler in handlers]
                        if tasks:
                            await asyncio.gather(*tasks, return_exceptions=True)

                    except Exception as e:
                        logger.error(f"Error processing message: {e}")

        except Exception as e:
            logger.error(f"Error in pub/sub listener: {e}")

        finally:
            if pubsub:
                await pubsub.aclose()

    async def stop_listening(self) -> None:
        """Stop listening for messages"""
        self._stop_listening = True
        if self.listening_task:
            try:
                await asyncio.wait_for(self.listening_task, timeout=5)
            except TimeoutError:
                logger.warning("Pub/Sub listener shutdown timeout")

    def start_listener_task(self) -> None:
        """Start the listener as a background task"""
        if self.listening_task is None or self.listening_task.done():
            self.listening_task = asyncio.create_task(self.start_listening())

    # Convenience methods for common events

    async def publish_workflow_event(
        self,
        event_type: EventType,
        workflow_id: int,
        tenant_id: int,
        data: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        source: str = "workflow_service",
    ) -> bool:
        """Publish workflow-related event"""
        message = PubSubMessage(
            event_type=event_type,
            data={**(data or {}), "workflow_id": workflow_id},
            source=source,
            tenant_id=tenant_id,
        )
        return await self.publish(message)

    async def publish_task_event(
        self,
        event_type: EventType,
        task_id: int,
        workflow_id: int,
        tenant_id: int,
        data: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        source: str = "task_service",
    ) -> bool:
        """Publish task-related event"""
        message = PubSubMessage(
            event_type=event_type,
            data={**(data or {}), "task_id": task_id, "workflow_id": workflow_id},
            source=source,
            tenant_id=tenant_id,
        )
        return await self.publish(message)

    async def publish_agent_event(
        self,
        event_type: EventType,
        agent_id: int,
        tenant_id: int,
        data: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        source: str = "agent_service",
        user_id: int | None = None,
    ) -> bool:
        """Publish agent-related event"""
        message = PubSubMessage(
            event_type=event_type,
            data={**(data or {}), "agent_id": agent_id},
            source=source,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        return await self.publish(message)

    async def publish_cache_invalidation(
        self,
        pattern: str,
        tenant_id: int | None = None,
        source: str = "cache_service",
    ) -> bool:
        """Publish cache invalidation event"""
        message = PubSubMessage(
            event_type=EventType.CACHE_INVALIDATION,
            data={"pattern": pattern},
            source=source,
            tenant_id=tenant_id,
        )
        return await self.publish(message)

    async def publish_user_event(
        self,
        event_type: EventType,
        user_id: int,
        tenant_id: int,
        data: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        source: str = "auth_service",
    ) -> bool:
        """Publish user-related event"""
        message = PubSubMessage(
            event_type=event_type,
            data=data or {},
            source=source,
            tenant_id=tenant_id,
            user_id=user_id,
        )
        return await self.publish(message)

    async def get_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get pub/sub statistics"""
        if not self.connected:
            return {"connected": False}

        try:
            return {
                "connected": True,
                "subscribed_channels": len(self.subscribers),
                "total_handlers": sum(len(handlers) for handlers in self.subscribers.values()),
                "channels": list(self.subscribers.keys()),
            }

        except Exception as e:
            logger.error(f"Failed to get pub/sub stats: {e}")
            return {"connected": True, "error": str(e)}


# Global pub/sub manager instance
_pubsub_manager: RedisPubSubManager | None = None


async def get_pubsub_manager() -> RedisPubSubManager:
    """Get global pub/sub manager instance (singleton pattern)"""
    global _pubsub_manager

    if _pubsub_manager is None:
        _pubsub_manager = RedisPubSubManager()
        await _pubsub_manager.connect()

    return _pubsub_manager
