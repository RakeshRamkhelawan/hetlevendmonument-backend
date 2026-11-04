"""
Multi-Agent Communication Protocol
Advanced inter-agent messaging, coordination, and knowledge sharing system
"""

import asyncio
import logging
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional, Protocol, cast
from collections.abc import Callable, Coroutine, Mapping

from src.core.shared.interfaces import TaskData
from src.core.types import AgentType


class _HasAgentAttrs(Protocol):
    """Protocol for classes that have agent_id and agent_type attributes."""

    agent_id: str
    agent_type: AgentType


logger = logging.getLogger(__name__)


class MessageType(Enum):
    """Types of inter-agent messages"""

    TASK_REQUEST = "task_request"
    TASK_RESPONSE = "task_response"
    COLLABORATION_INVITE = "collaboration_invite"
    KNOWLEDGE_SHARE = "knowledge_share"
    STATUS_UPDATE = "status_update"
    RESOURCE_REQUEST = "resource_request"
    COORDINATION_REQUEST = "coordination_request"
    ERROR_NOTIFICATION = "error_notification"
    PERFORMANCE_METRICS = "performance_metrics"
    CONTEXT_PASSING = "context_passing"


class MessagePriority(Enum):
    """Message priority levels"""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class CollaborationPattern(Enum):
    """Agent collaboration patterns"""

    SEQUENTIAL = "sequential"  # One after another
    PARALLEL = "parallel"  # Simultaneously
    HIERARCHICAL = "hierarchical"  # Tree structure
    MESH = "mesh"  # Full interconnection
    PIPELINE = "pipeline"  # Data flow chain


@dataclass
class AgentMessage:
    """Standard message format for inter-agent communication"""

    message_id: str
    sender_id: str
    receiver_id: str
    message_type: MessageType
    priority: MessagePriority
    content: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    timestamp: datetime
    expires_at: datetime | None = None
    correlation_id: str | None = None  # For tracking conversations
    context: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    requires_response: bool = False

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert message to dictionary for serialization"""
        data = asdict(self)
        data["message_type"] = self.message_type.value
        data["priority"] = self.priority.value
        data["timestamp"] = self.timestamp.isoformat()
        if self.expires_at:
            data["expires_at"] = self.expires_at.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AgentMessage":  # TODO(TYPE): replace Any with concrete type
        """Create message from dictionary"""
        data["message_type"] = MessageType(data["message_type"])
        data["priority"] = MessagePriority(data["priority"])
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        if data.get("expires_at"):
            data["expires_at"] = datetime.fromisoformat(data["expires_at"])
        return cls(**data)


@dataclass
class CollaborationRequest:
    """Request for multi-agent collaboration"""

    collaboration_id: str
    initiator_id: str
    participant_ids: list[str]
    pattern: CollaborationPattern
    task_context: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    coordination_rules: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    expected_duration: timedelta
    success_criteria: list[str]


@dataclass
class SharedKnowledge:
    """Shared knowledge between agents"""

    knowledge_id: str
    source_agent: str
    knowledge_type: str
    content: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    confidence_level: float
    created_at: datetime
    expires_at: datetime | None = None
    access_permissions: list[str] | None = None


class CommunicationHub:
    """Central hub for multi-agent communication and coordination"""

    def __init__(self) -> None:
        # Message routing and delivery
        self.message_queues: dict[str, list[AgentMessage]] = {}
        self.message_handlers: dict[str, dict[MessageType, Callable[..., Any]]] = {}  # TODO(TYPE): replace Any with concrete type
        self.active_conversations: dict[str, list[AgentMessage]] = {}

        # Agent registry and status
        self.registered_agents: dict[str, dict[str, Any]] = {}  # TODO(TYPE): replace Any with concrete type
        self.agent_capabilities: dict[str, list[str]] = {}
        self.agent_status: dict[str, str] = {}

        # Collaboration management
        self.active_collaborations: dict[str, CollaborationRequest] = {}
        self.collaboration_history: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type

        # Knowledge sharing
        self.shared_knowledge: dict[str, SharedKnowledge] = {}
        self.knowledge_subscriptions: dict[str, list[str]] = {}  # agent_id -> knowledge_types

        # Performance and monitoring
        self.message_statistics: dict[str, int] = {}
        self.performance_metrics: dict[str, dict[str, Any]] = {}  # TODO(TYPE): replace Any with concrete type

        logger.info("CommunicationHub initialized")

    async def register_agent(
        self,
        agent_id: str,
        agent_type: AgentType,
        capabilities: list[str],
        message_handlers: Mapping[MessageType, Callable[..., Any]] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> bool:
        """Register an agent with the communication hub"""
        try:
            self.registered_agents[agent_id] = {
                "agent_type": agent_type.value,
                "capabilities": capabilities,
                "registered_at": datetime.now(timezone.utc),
                "last_seen": datetime.now(timezone.utc),
                "status": "active",
            }

            self.agent_capabilities[agent_id] = capabilities
            self.agent_status[agent_id] = "active"
            self.message_queues[agent_id] = []

            if message_handlers:
                self.message_handlers[agent_id] = dict(message_handlers)

            logger.info(f"Agent {agent_id} registered with {len(capabilities)} capabilities")

            # Notify other agents of new registration
            await self._broadcast_agent_status_update(agent_id, "registered")

            return True

        except Exception as e:
            logger.error(f"Failed to register agent {agent_id}: {e}")
            return False

    async def send_message(self, message: AgentMessage) -> bool:
        """Send message between agents"""
        try:
            # Validate sender and receiver
            if message.sender_id not in self.registered_agents:
                logger.error(f"Unknown sender: {message.sender_id}")
                return False

            if message.receiver_id not in self.registered_agents:
                logger.error(f"Unknown receiver: {message.receiver_id}")
                return False

            # Check if message has expired
            if message.expires_at and datetime.now(timezone.utc) > message.expires_at:
                logger.warning(f"Message {message.message_id} expired")
                return False

            # Add to receiver's queue
            self.message_queues[message.receiver_id].append(message)

            # Track conversation if correlation_id exists
            if message.correlation_id:
                if message.correlation_id not in self.active_conversations:
                    self.active_conversations[message.correlation_id] = []
                self.active_conversations[message.correlation_id].append(message)

            # Update statistics
            msg_type_key = f"{message.message_type.value}"
            self.message_statistics[msg_type_key] = self.message_statistics.get(msg_type_key, 0) + 1

            # Process message if handler exists
            if message.receiver_id in self.message_handlers:
                handler = self.message_handlers[message.receiver_id].get(message.message_type)
                if handler:
                    asyncio.create_task(handler(message))

            logger.debug(
                f"Message {message.message_id} sent from {message.sender_id} to {message.receiver_id}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to send message {message.message_id}: {e}")
            return False

    async def get_messages(
        self, agent_id: str, message_type: MessageType | None = None, limit: int = 10
    ) -> list[AgentMessage]:
        """Get messages for an agent"""
        try:
            if agent_id not in self.message_queues:
                return []

            messages = self.message_queues[agent_id]

            # Filter by message type if specified
            if message_type:
                messages = [msg for msg in messages if msg.message_type == message_type]

            # Sort by priority and timestamp
            priority_order = {
                MessagePriority.CRITICAL: 0,
                MessagePriority.HIGH: 1,
                MessagePriority.MEDIUM: 2,
                MessagePriority.LOW: 3,
            }

            messages.sort(key=lambda m: (priority_order[m.priority], m.timestamp))

            # Return limited results and remove from queue
            result = messages[:limit]
            self.message_queues[agent_id] = messages[limit:]

            return result

        except Exception as e:
            logger.error(f"Failed to get messages for {agent_id}: {e}")
            return []

    async def initiate_collaboration(self, collaboration_request: CollaborationRequest) -> bool:
        """Initiate multi-agent collaboration"""
        try:
            # Validate participants
            for participant_id in collaboration_request.participant_ids:
                if participant_id not in self.registered_agents:
                    logger.error(f"Unknown participant: {participant_id}")
                    return False

            # Store collaboration request
            self.active_collaborations[collaboration_request.collaboration_id] = (
                collaboration_request
            )

            # Send collaboration invites to participants
            for participant_id in collaboration_request.participant_ids:
                if participant_id != collaboration_request.initiator_id:
                    invite_message = AgentMessage(
                        message_id=str(uuid.uuid4()),
                        sender_id=collaboration_request.initiator_id,
                        receiver_id=participant_id,
                        message_type=MessageType.COLLABORATION_INVITE,
                        priority=MessagePriority.HIGH,
                        content={
                            "collaboration_id": collaboration_request.collaboration_id,
                            "pattern": collaboration_request.pattern.value,
                            "task_context": collaboration_request.task_context,
                            "coordination_rules": collaboration_request.coordination_rules,
                            "expected_duration": str(collaboration_request.expected_duration),
                        },
                        timestamp=datetime.now(timezone.utc),
                        correlation_id=collaboration_request.collaboration_id,
                        requires_response=True,
                    )

                    await self.send_message(invite_message)

            logger.info(
                f"Collaboration {collaboration_request.collaboration_id} initiated with {len(collaboration_request.participant_ids)} participants"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to initiate collaboration: {e}")
            return False

    async def share_knowledge(self, shared_knowledge: SharedKnowledge) -> bool:
        """Share knowledge between agents"""
        try:
            # Store shared knowledge
            self.shared_knowledge[shared_knowledge.knowledge_id] = shared_knowledge

            # Notify subscribed agents
            knowledge_type = shared_knowledge.knowledge_type
            for agent_id, subscribed_types in self.knowledge_subscriptions.items():
                if knowledge_type in subscribed_types:
                    knowledge_message = AgentMessage(
                        message_id=str(uuid.uuid4()),
                        sender_id=shared_knowledge.source_agent,
                        receiver_id=agent_id,
                        message_type=MessageType.KNOWLEDGE_SHARE,
                        priority=MessagePriority.MEDIUM,
                        content={
                            "knowledge_id": shared_knowledge.knowledge_id,
                            "knowledge_type": knowledge_type,
                            "content": shared_knowledge.content,
                            "confidence_level": shared_knowledge.confidence_level,
                        },
                        timestamp=datetime.now(timezone.utc),
                    )

                    await self.send_message(knowledge_message)

            logger.info(
                f"Knowledge {shared_knowledge.knowledge_id} shared by {shared_knowledge.source_agent}"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to share knowledge: {e}")
            return False

    async def subscribe_to_knowledge(self, agent_id: str, knowledge_types: list[str]) -> bool:
        """Subscribe agent to specific knowledge types"""
        try:
            if agent_id not in self.registered_agents:
                logger.error(f"Unknown agent: {agent_id}")
                return False

            self.knowledge_subscriptions[agent_id] = knowledge_types
            logger.info(f"Agent {agent_id} subscribed to {len(knowledge_types)} knowledge types")
            return True

        except Exception as e:
            logger.error(f"Failed to subscribe agent to knowledge: {e}")
            return False

    async def coordinate_task_execution(
        self,
        task: TaskData,
        participating_agents: list[str],
        coordination_pattern: CollaborationPattern,
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Coordinate task execution across multiple agents"""
        try:
            collaboration_id = str(uuid.uuid4())

            # Create collaboration request
            collaboration_request = CollaborationRequest(
                collaboration_id=collaboration_id,
                initiator_id="orchestrator",
                participant_ids=participating_agents,
                pattern=coordination_pattern,
                task_context={
                    "task_id": task.id,
                    "task_title": task.title,
                    "task_description": task.description,
                    "task_priority": task.priority.value,
                    "task_metadata": task.metadata,
                },
                coordination_rules={
                    "timeout_minutes": 30,
                    "failure_threshold": 0.7,
                    "retry_attempts": 3,
                },
                expected_duration=timedelta(minutes=30),
                success_criteria=[
                    "All participants respond",
                    "Task completion confirmed",
                    "Quality thresholds met",
                ],
            )

            # Initiate collaboration
            success = await self.initiate_collaboration(collaboration_request)

            if success:
                return {
                    "collaboration_id": collaboration_id,
                    "status": "initiated",
                    "participants": participating_agents,
                    "pattern": coordination_pattern.value,
                }
            else:
                return {
                    "collaboration_id": collaboration_id,
                    "status": "failed",
                    "error": "Failed to initiate collaboration",
                }

        except Exception as e:
            logger.error(f"Failed to coordinate task execution: {e}")
            return {"status": "error", "error": str(e)}

    async def get_agent_performance_metrics(self, agent_id: str | None = None) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get performance metrics for agents"""
        try:
            if agent_id:
                # Get metrics for specific agent
                return self.performance_metrics.get(agent_id, {})
            else:
                # Get system-wide metrics
                total_messages = sum(self.message_statistics.values())
                active_agents = len(
                    [aid for aid, status in self.agent_status.items() if status == "active"]
                )

                return {
                    "total_registered_agents": len(self.registered_agents),
                    "active_agents": active_agents,
                    "total_messages_sent": total_messages,
                    "message_breakdown": self.message_statistics,
                    "active_collaborations": len(self.active_collaborations),
                    "shared_knowledge_items": len(self.shared_knowledge),
                    "active_conversations": len(self.active_conversations),
                }

        except Exception as e:
            logger.error(f"Failed to get performance metrics: {e}")
            return {}

    async def _broadcast_agent_status_update(self, agent_id: str, status: str) -> None:
        """Broadcast agent status updates to all other agents"""
        try:
            for other_agent_id in self.registered_agents:
                if other_agent_id != agent_id:
                    status_message = AgentMessage(
                        message_id=str(uuid.uuid4()),
                        sender_id="communication_hub",
                        receiver_id=other_agent_id,
                        message_type=MessageType.STATUS_UPDATE,
                        priority=MessagePriority.LOW,
                        content={
                            "agent_id": agent_id,
                            "status": status,
                            "agent_type": self.registered_agents[agent_id]["agent_type"],
                            "capabilities": self.agent_capabilities.get(agent_id, []),
                        },
                        timestamp=datetime.now(timezone.utc),
                    )

                    await self.send_message(status_message)

        except Exception as e:
            logger.error(f"Failed to broadcast status update: {e}")

    async def cleanup_expired_data(self) -> None:
        """Clean up expired messages, knowledge, and conversations"""
        try:
            current_time = datetime.now(timezone.utc)

            # Clean up expired messages
            for agent_id, messages in self.message_queues.items():
                self.message_queues[agent_id] = [
                    msg for msg in messages if not msg.expires_at or msg.expires_at > current_time
                ]

            # Clean up expired knowledge
            expired_knowledge = [
                kid
                for kid, knowledge in self.shared_knowledge.items()
                if knowledge.expires_at and knowledge.expires_at <= current_time
            ]

            for kid in expired_knowledge:
                del self.shared_knowledge[kid]

            # Clean up old conversations (older than 24 hours)
            day_ago = current_time - timedelta(days=1)
            expired_conversations = [
                cid
                for cid, messages in self.active_conversations.items()
                if messages and messages[-1].timestamp < day_ago
            ]

            for cid in expired_conversations:
                del self.active_conversations[cid]

            logger.info(
                f"Cleanup completed: {len(expired_knowledge)} knowledge items, {len(expired_conversations)} conversations removed"
            )

        except Exception as e:
            logger.error(f"Failed to cleanup expired data: {e}")


# Singleton instance
_communication_hub: CommunicationHub | None = None


def get_communication_hub() -> CommunicationHub:
    """Get the global communication hub instance"""
    global _communication_hub
    if _communication_hub is None:
        _communication_hub = CommunicationHub()
    return _communication_hub


class AgentCommunicationMixin:
    """Mixin class to add communication capabilities to agents"""

    # Type declarations for attributes provided by the using class
    agent_id: str
    agent_type: AgentType

    def _get_self(self) -> _HasAgentAttrs:
        """Return self cast to _HasAgentAttrs for type checking."""
        return cast(_HasAgentAttrs, self)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.communication_hub = get_communication_hub()
        self.conversation_contexts: dict[str, dict[str, Any]] = {}  # TODO(TYPE): replace Any with concrete type

    async def register_for_communication(self, capabilities: list[str]) -> None:
        """Register agent with communication hub"""
        message_handlers = {
            MessageType.TASK_REQUEST: self._handle_task_request,
            MessageType.COLLABORATION_INVITE: self._handle_collaboration_invite,
            MessageType.KNOWLEDGE_SHARE: self._handle_knowledge_share,
            MessageType.STATUS_UPDATE: self._handle_status_update,
            MessageType.CONTEXT_PASSING: self._handle_context_passing,
        }

        await self.communication_hub.register_agent(
            agent_id=self.agent_id,
            agent_type=self.agent_type,
            capabilities=capabilities,
            message_handlers=message_handlers,
        )

    async def send_to_agent(
        self,
        receiver_id: str,
        message_type: MessageType,
        content: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        priority: MessagePriority = MessagePriority.MEDIUM,
        requires_response: bool = False,
        correlation_id: str | None = None,
    ) -> bool:
        """Send message to another agent"""
        message = AgentMessage(
            message_id=str(uuid.uuid4()),
            sender_id=self.agent_id,
            receiver_id=receiver_id,
            message_type=message_type,
            priority=priority,
            content=content,
            timestamp=datetime.now(timezone.utc),
            requires_response=requires_response,
            correlation_id=correlation_id,
        )

        return await self.communication_hub.send_message(message)

    async def get_my_messages(
        self, message_type: MessageType | None = None, limit: int = 10
    ) -> list[AgentMessage]:
        """Get messages for this agent"""
        return await self.communication_hub.get_messages(
            self.agent_id,
            message_type,
            limit,
        )

    async def share_knowledge_with_network(
        self,
        knowledge_type: str,
        content: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        confidence_level: float = 0.8,
    ) -> bool:
        """Share knowledge with the agent network"""
        shared_knowledge = SharedKnowledge(
            knowledge_id=str(uuid.uuid4()),
            source_agent=self.agent_id,
            knowledge_type=knowledge_type,
            content=content,
            confidence_level=confidence_level,
            created_at=datetime.now(timezone.utc),
        )

        return await self.communication_hub.share_knowledge(shared_knowledge)

    async def subscribe_to_knowledge_types(self, knowledge_types: list[str]) -> bool:
        """Subscribe to specific knowledge types"""
        return await self.communication_hub.subscribe_to_knowledge(
            self.agent_id,
            knowledge_types,
        )

    async def _handle_task_request(self, message: AgentMessage) -> None:
        """Handle incoming task requests"""
        try:
            # Default implementation - can be overridden by specific agents
            logger.info(
                f"Agent {self.agent_id} received task request: {message.content.get('task_title')}"
            )

            if message.requires_response:
                # Send acknowledgment
                await self.send_to_agent(
                    receiver_id=message.sender_id,
                    message_type=MessageType.TASK_RESPONSE,
                    content={
                        "status": "acknowledged",
                        "message_id": message.message_id,
                    },
                    correlation_id=message.correlation_id,
                )

        except Exception as e:
            logger.error(f"Failed to handle task request: {e}")

    async def _handle_collaboration_invite(self, message: AgentMessage) -> None:
        """Handle collaboration invitations"""
        try:
            logger.info(
                f"Agent {self.agent_id} received collaboration invite for {message.content.get('collaboration_id')}"
            )

            # Default: accept collaboration
            await self.send_to_agent(
                receiver_id=message.sender_id,
                message_type=MessageType.TASK_RESPONSE,
                content={
                    "collaboration_id": message.content.get("collaboration_id"),
                    "response": "accepted",
                    "agent_capabilities": getattr(self, "analysis_domains", []),
                },
                correlation_id=message.correlation_id,
            )

        except Exception as e:
            logger.error(f"Failed to handle collaboration invite: {e}")

    async def _handle_knowledge_share(self, message: AgentMessage) -> None:
        """Handle incoming knowledge sharing"""
        try:
            knowledge_type = message.content.get("knowledge_type")
            knowledge_content = message.content.get("content")

            logger.info(f"Agent {self.agent_id} received knowledge: {knowledge_type}")

            # Store knowledge in conversation context for potential use
            if hasattr(self, "conversation_contexts"):
                context_key = f"shared_knowledge_{knowledge_type}"
                self.conversation_contexts[context_key] = {
                    "content": knowledge_content,
                    "confidence": message.content.get("confidence_level"),
                    "received_at": datetime.now(timezone.utc),
                    "source_agent": message.sender_id,
                }

        except Exception as e:
            logger.error(f"Failed to handle knowledge share: {e}")

    async def _handle_status_update(self, message: AgentMessage) -> None:
        """Handle agent status updates"""
        try:
            agent_id = message.content.get("agent_id")
            status = message.content.get("status")

            logger.debug(f"Agent {self.agent_id} received status update: {agent_id} is {status}")

        except Exception as e:
            logger.error(f"Failed to handle status update: {e}")

    async def _handle_context_passing(self, message: AgentMessage) -> None:
        """Handle context passing between agents"""
        try:
            context_data = message.content.get("context")
            context_type = message.content.get("context_type")

            if context_data and context_type and hasattr(self, "conversation_contexts"):
                self.conversation_contexts[context_type] = {
                    "data": context_data,
                    "received_at": datetime.now(timezone.utc),
                    "source_agent": message.sender_id,
                }

            logger.info(f"Agent {self.agent_id} received context: {context_type}")

        except Exception as e:
            logger.error(f"Failed to handle context passing: {e}")


# Utility functions for common communication patterns
async def broadcast_to_agent_type(
    agent_type: AgentType,
    message_type: MessageType,
    content: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    sender_id: str,
    priority: MessagePriority = MessagePriority.MEDIUM,
) -> None:
    """Broadcast message to all agents of a specific type"""
    hub = get_communication_hub()

    target_agents = [
        agent_id
        for agent_id, agent_info in hub.registered_agents.items()
        if agent_info["agent_type"] == agent_type.value
    ]

    for agent_id in target_agents:
        message = AgentMessage(
            message_id=str(uuid.uuid4()),
            sender_id=sender_id,
            receiver_id=agent_id,
            message_type=message_type,
            priority=priority,
            content=content,
            timestamp=datetime.now(timezone.utc),
        )

        await hub.send_message(message)


async def create_agent_conversation(
    initiator_id: str, participant_ids: list[str], conversation_topic: str
) -> str:
    """Create a conversation context for multiple agents"""
    correlation_id = str(uuid.uuid4())

    hub = get_communication_hub()

    for participant_id in participant_ids:
        if participant_id != initiator_id:
            message = AgentMessage(
                message_id=str(uuid.uuid4()),
                sender_id=initiator_id,
                receiver_id=participant_id,
                message_type=MessageType.COLLABORATION_INVITE,
                priority=MessagePriority.MEDIUM,
                content={
                    "conversation_topic": conversation_topic,
                    "participants": participant_ids,
                },
                timestamp=datetime.now(timezone.utc),
                correlation_id=correlation_id,
            )

            await hub.send_message(message)

    return correlation_id
