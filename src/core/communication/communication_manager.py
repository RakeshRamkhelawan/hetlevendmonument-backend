from __future__ import annotations

#!/usr/bin/env python3
"""
M-MDP Communication Manager Implementation
Handles message routing, telemetry collection, and agent-to-agent communication
"""

import asyncio
import logging
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Any, Optional, cast
from collections.abc import Awaitable, Callable

import redis.asyncio as redis

from src.core.database.redis import ensure_async
from src.core.typing import AsyncRedisClient
from src.core.types import AgentType

from .message_protocol import (
    MDPMessage,
    MessageFactory,
    MessagePriority,
    MessageStatus,
    MessageType,
    TelemetryMessage,
)

logger = logging.getLogger(__name__)


class CommunicationManager:
    """Centralized communication manager for M-MDP multi-agent system"""

    def __init__(self, redis_url: str = "redis://localhost:6379") -> None:
        self.redis_url = redis_url
        self.redis_client: AsyncRedisClient | None = None

        # Message routing tables
        self.agent_endpoints: dict[str, dict[str, Any]] = {}  # TODO(TYPE): replace Any with concrete type
        self.message_handlers: dict[MessageType, list[Callable[..., Any]]] = defaultdict(list)  # TODO(TYPE): replace Any with concrete type

        # Message queues for different priorities
        self.message_queues: dict[MessagePriority, deque[Any]] = {  # TODO(TYPE): replace Any with concrete type
            priority: deque() for priority in MessagePriority
        }

        # Telemetry collection
        self.telemetry_data: dict[str, list[TelemetryMessage]] = defaultdict(list)
        self.performance_metrics: dict[str, dict[str, float]] = defaultdict(dict)

        # Message tracking
        self.pending_messages: dict[str, MDPMessage] = {}
        self.message_history: deque[Any] = deque(maxlen=1000)  # Keep last 1000 messages  # TODO(TYPE): replace Any with concrete type

        # Communication statistics
        self.comm_stats: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "messages_sent": 0,
            "messages_received": 0,
            "messages_failed": 0,
            "average_latency": 0.0,
            "active_conversations": 0,
        }

        # Background tasks
        self._processing_task: asyncio.Task[Any] | None = None  # TODO(TYPE): replace Any with concrete type
        self._cleanup_task: asyncio.Task[Any] | None = None  # TODO(TYPE): replace Any with concrete type

    async def initialize(self) -> None:
        """Initialize communication manager"""
        try:
            # Connect to AsyncRedisClient
            from src.core.typing import create_async_redis_client

            self.redis_client = await create_async_redis_client(self.redis_url)

            # Start background processing tasks
            self._processing_task = asyncio.create_task(self._process_message_queue())
            self._cleanup_task = asyncio.create_task(self._cleanup_expired_messages())

            logger.info("Communication manager initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize communication manager: {e}")
            raise

    async def register_agent(
        self,
        agent_id: str,
        agent_type: AgentType,
        endpoint: str | None = None,
        capabilities: list[str] | None = None,
    ) -> None:
        """Register an agent in the communication system"""
        self.agent_endpoints[agent_id] = {
            "type": agent_type,
            "endpoint": endpoint,
            "capabilities": capabilities or [],
            "last_seen": datetime.now(timezone.utc),
            "status": "active",
        }

        logger.info(f"Registered agent {agent_id} of type {agent_type.value}")

    async def send_message(self, message: MDPMessage) -> bool:
        """Send a message through the communication system"""
        try:
            # Validate recipient exists
            if message.header.recipient_id not in self.agent_endpoints:
                logger.warning(f"Recipient {message.header.recipient_id} not registered")
                return False

            # Store message in pending tracking
            self.pending_messages[message.header.message_id] = message

            # Add to appropriate priority queue
            self.message_queues[message.header.priority].append(message)

            # Store in AsyncRedisClient for persistence
            await self._persist_message(message)

            # Update statistics
            self.comm_stats["messages_sent"] += 1

            logger.info(f"Message {message.header.message_id} queued for delivery")
            return True

        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            self.comm_stats["messages_failed"] += 1
            return False

    async def receive_message(self, agent_id: str) -> MDPMessage | None:
        """Receive the next message for an agent"""
        try:
            # Check AsyncRedisClient for messages addressed to this agent
            message_key = f"messages:{agent_id}"
            redis_client = self.redis_client
            if redis_client is None:
                return None
            message_data = await cast(Awaitable[Any], redis_client.lpop(message_key))  # TODO(TYPE): replace Any with concrete type

            if message_data:
                message = MDPMessage.from_json(message_data.decode())
                message.status = MessageStatus.PROCESSING

                # Update statistics
                self.comm_stats["messages_received"] += 1

                # Add to message history
                self.message_history.append(message)

                logger.info(f"Message {message.header.message_id} delivered to {agent_id}")
                return message

            return None

        except Exception as e:
            logger.error(f"Failed to receive message for {agent_id}: {e}")
            return None

    async def acknowledge_message(
        self,
        message_id: str,
        success: bool,
        result_data: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Acknowledge message processing completion"""
        try:
            if message_id in self.pending_messages:
                message = self.pending_messages[message_id]
                message.status = MessageStatus.COMPLETED if success else MessageStatus.FAILED

                # Remove from pending
                del self.pending_messages[message_id]

                # Calculate and update latency
                processing_time = (datetime.now(timezone.utc) - message.header.timestamp).total_seconds()
                self._update_latency_stats(processing_time)

                logger.info(
                    f"Message {message_id} acknowledged: {'success' if success else 'failed'}"
                )

        except Exception as e:
            logger.error(f"Failed to acknowledge message {message_id}: {e}")

    async def collect_telemetry(
        self,
        agent_id: str,
        metrics: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        performance_indicators: dict[str, float],
        resource_usage: dict[str, float],
    ) -> None:
        """Collect telemetry data from an agent"""
        try:
            # Create telemetry message
            telemetry_msg = MessageFactory.create_telemetry_message(
                sender_id=agent_id,
                sender_type=self.agent_endpoints[agent_id]["type"],
                metrics=metrics,
                performance_indicators=performance_indicators,
                resource_usage=resource_usage,
            )

            # Store telemetry data
            from .message_protocol import TelemetryMessage as _TelemetryMessage

            self.telemetry_data[agent_id].append(cast(_TelemetryMessage, telemetry_msg.payload))
            self.performance_metrics[agent_id].update(performance_indicators)

            # Persist to AsyncRedisClient
            telemetry_key = f"telemetry:{agent_id}:{datetime.now(timezone.utc).strftime('%Y%m%d_%H')}"
            redis_client = self.redis_client
            if redis_client is None:
                return
            await cast(Awaitable[Any], redis_client.lpush(telemetry_key, telemetry_msg.to_json()))  # TODO(TYPE): replace Any with concrete type
            await cast(Awaitable[Any], redis_client.expire(telemetry_key, 86400))  # TODO(TYPE): replace Any with concrete type

            logger.debug(f"Telemetry collected from {agent_id}")

        except Exception as e:
            logger.error(f"Failed to collect telemetry from {agent_id}: {e}")

    async def get_agent_performance(self, agent_id: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get performance metrics for an agent"""
        if agent_id not in self.performance_metrics:
            return {}

        recent_telemetry = self.telemetry_data[agent_id][-10:]  # Last 10 entries

        return {
            "agent_id": agent_id,
            "current_metrics": self.performance_metrics[agent_id],
            "recent_telemetry_count": len(recent_telemetry),
            "last_update": datetime.now(timezone.utc).isoformat() if recent_telemetry else None,
            "agent_status": self.agent_endpoints.get(agent_id, {}).get("status", "unknown"),
        }

    async def get_communication_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get communication system statistics"""
        return {
            **self.comm_stats,
            "registered_agents": len(self.agent_endpoints),
            "pending_messages": len(self.pending_messages),
            "message_history_size": len(self.message_history),
            "active_agents": sum(
                1 for agent in self.agent_endpoints.values() if agent["status"] == "active"
            ),
        }

    async def get_system_health(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get overall system health status"""
        total_agents = len(self.agent_endpoints)
        active_agents = sum(
            1 for agent in self.agent_endpoints.values() if agent["status"] == "active"
        )

        health_score = (active_agents / total_agents * 100) if total_agents > 0 else 0

        return {
            "health_score": health_score,
            "total_agents": total_agents,
            "active_agents": active_agents,
            "communication_latency": self.comm_stats["average_latency"],
            "message_success_rate": self._calculate_success_rate(),
            "system_status": (
                "healthy" if health_score > 80 else "degraded" if health_score > 50 else "critical"
            ),
        }

    async def _process_message_queue(self) -> None:
        """Background task to process message queues"""
        while True:
            try:
                # Process messages by priority
                for priority in MessagePriority:
                    queue = self.message_queues[priority]

                    while queue:
                        message = queue.popleft()
                        await self._deliver_message(message)

                        # Small delay to prevent overwhelming
                        await asyncio.sleep(0.01)

                # Sleep before next processing cycle
                await asyncio.sleep(0.1)

            except Exception as e:
                logger.error(f"Error in message processing: {e}")
                await asyncio.sleep(1)  # Wait longer on error

    async def _deliver_message(self, message: MDPMessage) -> None:
        """Deliver a message to its recipient"""
        try:
            recipient_id = message.header.recipient_id

            # Store message in recipient's AsyncRedisClient queue
            message_key = f"messages:{recipient_id}"
            redis_client = self.redis_client
            if redis_client is None:
                return
            await cast(Awaitable[Any], redis_client.rpush(message_key, message.to_json()))  # TODO(TYPE): replace Any with concrete type

            # Update message status
            message.status = MessageStatus.COMPLETED

            logger.debug(f"Message {message.header.message_id} delivered to {recipient_id}")

        except Exception as e:
            logger.error(f"Failed to deliver message {message.header.message_id}: {e}")
            message.status = MessageStatus.FAILED

    async def _persist_message(self, message: MDPMessage) -> None:
        """Persist message to AsyncRedisClient"""
        try:
            # Store in general message log
            message_log_key = f"message_log:{datetime.now(timezone.utc).strftime('%Y%m%d')}"
            redis_client = self.redis_client
            if redis_client is None:
                return
            await cast(Awaitable[Any], redis_client.lpush(message_log_key, message.to_json()))  # TODO(TYPE): replace Any with concrete type
            await cast(Awaitable[Any], redis_client.expire(message_log_key, 604800))  # TODO(TYPE): replace Any with concrete type

        except Exception as e:
            logger.error(f"Failed to persist message: {e}")

    async def _cleanup_expired_messages(self) -> None:
        """Background task to cleanup expired messages"""
        while True:
            try:
                now = datetime.now(timezone.utc)
                expired_messages: list[Any] = []  # TODO(TYPE): replace Any with concrete type
                for message_id, message in self.pending_messages.items():
                    if message.header.expires_at and message.header.expires_at < now:
                        expired_messages.append(message_id)

                # Remove expired messages
                for message_id in expired_messages:
                    message = self.pending_messages.pop(message_id)
                    message.status = MessageStatus.EXPIRED
                    logger.warning(f"Message {message_id} expired")

                # Sleep for 60 seconds before next cleanup
                await asyncio.sleep(60)

            except Exception as e:
                logger.error(f"Error in message cleanup: {e}")
                await asyncio.sleep(60)

    def _update_latency_stats(self, processing_time: float) -> None:
        """Update average latency statistics"""
        current_avg = self.comm_stats["average_latency"]
        messages_count = self.comm_stats["messages_received"]

        # Calculate running average
        if messages_count > 1:
            self.comm_stats["average_latency"] = (
                current_avg * (messages_count - 1) + processing_time
            ) / messages_count
        else:
            self.comm_stats["average_latency"] = processing_time

    def _calculate_success_rate(self) -> float:
        """Calculate message success rate"""
        sent = cast(int, self.comm_stats["messages_sent"])
        failed = cast(int, self.comm_stats["messages_failed"])

        if sent == 0:
            return 100.0

        return ((sent - failed) / sent) * 100

    async def cleanup(self) -> None:
        """Cleanup communication manager resources"""
        try:
            # Cancel background tasks
            if self._processing_task:
                self._processing_task.cancel()
            if self._cleanup_task:
                self._cleanup_task.cancel()

            # Close AsyncRedisClient connection
            if self.redis_client:
                await self.redis_client.close()

            logger.info("Communication manager cleanup completed")

        except Exception as e:
            logger.error(f"Error during communication manager cleanup: {e}")


# Global communication manager instance
communication_manager = CommunicationManager()
