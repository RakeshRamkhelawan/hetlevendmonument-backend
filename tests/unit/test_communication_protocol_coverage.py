"""
Comprehensive tests for src/core/agents/communication_protocol.py
Coverage target: 100% of communication protocol functionality
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.core.agents.communication_protocol import (
    AgentMessage,
    CollaborationPattern,
    CollaborationRequest,
    CommunicationHub,
    MessagePriority,
    MessageType,
    SharedKnowledge,
)
from src.core.shared.interfaces import AgentType


class TestMessageType:
    """Test MessageType enum"""

    def test_task_request_type(self):
        """Test TASK_REQUEST message type"""
        assert MessageType.TASK_REQUEST.value == "task_request"

    def test_task_response_type(self):
        """Test TASK_RESPONSE message type"""
        assert MessageType.TASK_RESPONSE.value == "task_response"

    def test_knowledge_share_type(self):
        """Test KNOWLEDGE_SHARE message type"""
        assert MessageType.KNOWLEDGE_SHARE.value == "knowledge_share"

    def test_error_notification_type(self):
        """Test ERROR_NOTIFICATION message type"""
        assert MessageType.ERROR_NOTIFICATION.value == "error_notification"


class TestMessagePriority:
    """Test MessagePriority enum"""

    def test_critical_priority(self):
        """Test CRITICAL priority"""
        assert MessagePriority.CRITICAL.value == "critical"

    def test_high_priority(self):
        """Test HIGH priority"""
        assert MessagePriority.HIGH.value == "high"

    def test_medium_priority(self):
        """Test MEDIUM priority"""
        assert MessagePriority.MEDIUM.value == "medium"

    def test_low_priority(self):
        """Test LOW priority"""
        assert MessagePriority.LOW.value == "low"


class TestCollaborationPattern:
    """Test CollaborationPattern enum"""

    def test_sequential_pattern(self):
        """Test SEQUENTIAL pattern"""
        assert CollaborationPattern.SEQUENTIAL.value == "sequential"

    def test_parallel_pattern(self):
        """Test PARALLEL pattern"""
        assert CollaborationPattern.PARALLEL.value == "parallel"

    def test_hierarchical_pattern(self):
        """Test HIERARCHICAL pattern"""
        assert CollaborationPattern.HIERARCHICAL.value == "hierarchical"


class TestAgentMessage:
    """Test AgentMessage dataclass"""

    def test_message_creation(self):
        """Test creating an AgentMessage"""
        message = AgentMessage(
            message_id="msg-1",
            sender_id="agent-1",
            receiver_id="agent-2",
            message_type=MessageType.TASK_REQUEST,
            priority=MessagePriority.HIGH,
            content={"task": "test"},
            timestamp=datetime.now(timezone.utc),
        )

        assert message.message_id == "msg-1"
        assert message.sender_id == "agent-1"
        assert message.receiver_id == "agent-2"

    def test_message_to_dict(self):
        """Test converting message to dictionary"""
        message = AgentMessage(
            message_id="msg-2",
            sender_id="agent-1",
            receiver_id="agent-2",
            message_type=MessageType.TASK_REQUEST,
            priority=MessagePriority.HIGH,
            content={"task": "test"},
            timestamp=datetime.now(timezone.utc),
        )

        result = message.to_dict()

        assert isinstance(result, dict)
        assert result["message_id"] == "msg-2"
        assert result["message_type"] == "task_request"
        assert result["priority"] == "high"

    def test_message_from_dict(self):
        """Test creating message from dictionary"""
        data = {
            "message_id": "msg-3",
            "sender_id": "agent-1",
            "receiver_id": "agent-2",
            "message_type": "task_request",
            "priority": "high",
            "content": {"task": "test"},
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "requires_response": False,
        }

        message = AgentMessage.from_dict(data)

        assert message.message_id == "msg-3"
        assert message.message_type == MessageType.TASK_REQUEST
        assert message.priority == MessagePriority.HIGH

    def test_message_with_expiry(self):
        """Test message with expiration time"""
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        message = AgentMessage(
            message_id="msg-4",
            sender_id="agent-1",
            receiver_id="agent-2",
            message_type=MessageType.TASK_REQUEST,
            priority=MessagePriority.MEDIUM,
            content={},
            timestamp=datetime.now(timezone.utc),
            expires_at=expires_at,
        )

        assert message.expires_at == expires_at

    def test_message_with_correlation_id(self):
        """Test message with correlation ID for conversation tracking"""
        message = AgentMessage(
            message_id="msg-5",
            sender_id="agent-1",
            receiver_id="agent-2",
            message_type=MessageType.TASK_RESPONSE,
            priority=MessagePriority.MEDIUM,
            content={},
            timestamp=datetime.now(timezone.utc),
            correlation_id="conv-123",
        )

        assert message.correlation_id == "conv-123"


class TestCollaborationRequest:
    """Test CollaborationRequest dataclass"""

    def test_collaboration_request_creation(self):
        """Test creating a CollaborationRequest"""
        request = CollaborationRequest(
            collaboration_id="collab-1",
            initiator_id="agent-1",
            participant_ids=["agent-2", "agent-3"],
            pattern=CollaborationPattern.SEQUENTIAL,
            task_context={"task": "test"},
            coordination_rules={"rule": "value"},
            expected_duration=timedelta(minutes=30),
            success_criteria=["criterion1", "criterion2"],
        )

        assert request.collaboration_id == "collab-1"
        assert len(request.participant_ids) == 2
        assert request.pattern == CollaborationPattern.SEQUENTIAL


class TestSharedKnowledge:
    """Test SharedKnowledge dataclass"""

    def test_shared_knowledge_creation(self):
        """Test creating a SharedKnowledge instance"""
        knowledge = SharedKnowledge(
            knowledge_id="know-1",
            source_agent="agent-1",
            knowledge_type="technical",
            content={"data": "value"},
            confidence_level=0.95,
            created_at=datetime.now(timezone.utc),
        )

        assert knowledge.knowledge_id == "know-1"
        assert knowledge.source_agent == "agent-1"
        assert knowledge.confidence_level == 0.95


class TestCommunicationHubInitialization:
    """Test CommunicationHub initialization"""

    def test_hub_initialization(self):
        """Test CommunicationHub initialization"""
        hub = CommunicationHub()

        assert isinstance(hub.message_queues, dict)
        assert isinstance(hub.registered_agents, dict)
        assert isinstance(hub.active_collaborations, dict)
        assert isinstance(hub.shared_knowledge, dict)

    def test_hub_empty_on_initialization(self):
        """Test hub is empty on initialization"""
        hub = CommunicationHub()

        assert len(hub.registered_agents) == 0
        assert len(hub.message_queues) == 0
        assert len(hub.active_collaborations) == 0


class TestRegisterAgent:
    """Test register_agent method"""

    @pytest.mark.asyncio
    async def test_register_agent_success(self):
        """Test successful agent registration"""
        hub = CommunicationHub()

        result = await hub.register_agent(
            "agent-1", AgentType.SPECIALIST, ["capability1", "capability2"]
        )

        assert result is True
        assert "agent-1" in hub.registered_agents
        assert "agent-1" in hub.message_queues

    @pytest.mark.asyncio
    async def test_register_agent_stores_capabilities(self):
        """Test agent registration stores capabilities"""
        hub = CommunicationHub()

        await hub.register_agent("agent-2", AgentType.CVA, ["cap1", "cap2", "cap3"])

        assert hub.agent_capabilities["agent-2"] == ["cap1", "cap2", "cap3"]

    @pytest.mark.asyncio
    async def test_register_agent_sets_status(self):
        """Test agent registration sets active status"""
        hub = CommunicationHub()

        await hub.register_agent("agent-3", AgentType.SPECIALIST, ["capability1"])

        assert hub.agent_status["agent-3"] == "active"


class TestSendMessage:
    """Test send_message method"""

    @pytest.mark.asyncio
    async def test_send_message_success(self):
        """Test successful message sending"""
        hub = CommunicationHub()
        await hub.register_agent("agent-1", AgentType.SPECIALIST, [])
        await hub.register_agent("agent-2", AgentType.SPECIALIST, [])

        message = AgentMessage(
            message_id="msg-1",
            sender_id="agent-1",
            receiver_id="agent-2",
            message_type=MessageType.TASK_REQUEST,
            priority=MessagePriority.HIGH,
            content={"data": "test"},
            timestamp=datetime.now(timezone.utc),
        )

        result = await hub.send_message(message)

        assert result is True
        assert len(hub.message_queues["agent-2"]) == 1

    @pytest.mark.asyncio
    async def test_send_message_unknown_sender(self):
        """Test sending message from unknown sender"""
        hub = CommunicationHub()
        await hub.register_agent("agent-2", AgentType.SPECIALIST, [])

        message = AgentMessage(
            message_id="msg-2",
            sender_id="unknown-agent",
            receiver_id="agent-2",
            message_type=MessageType.TASK_REQUEST,
            priority=MessagePriority.HIGH,
            content={},
            timestamp=datetime.now(timezone.utc),
        )

        result = await hub.send_message(message)

        assert result is False

    @pytest.mark.asyncio
    async def test_send_message_unknown_receiver(self):
        """Test sending message to unknown receiver"""
        hub = CommunicationHub()
        await hub.register_agent("agent-1", AgentType.SPECIALIST, [])

        message = AgentMessage(
            message_id="msg-3",
            sender_id="agent-1",
            receiver_id="unknown-agent",
            message_type=MessageType.TASK_REQUEST,
            priority=MessagePriority.HIGH,
            content={},
            timestamp=datetime.now(timezone.utc),
        )

        result = await hub.send_message(message)

        assert result is False

    @pytest.mark.asyncio
    async def test_send_message_expired(self):
        """Test sending expired message"""
        hub = CommunicationHub()
        await hub.register_agent("agent-1", AgentType.SPECIALIST, [])
        await hub.register_agent("agent-2", AgentType.SPECIALIST, [])

        message = AgentMessage(
            message_id="msg-4",
            sender_id="agent-1",
            receiver_id="agent-2",
            message_type=MessageType.TASK_REQUEST,
            priority=MessagePriority.HIGH,
            content={},
            timestamp=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),  # Already expired
        )

        result = await hub.send_message(message)

        assert result is False

    @pytest.mark.asyncio
    async def test_send_message_tracks_conversation(self):
        """Test message sending tracks conversation by correlation ID"""
        hub = CommunicationHub()
        await hub.register_agent("agent-1", AgentType.SPECIALIST, [])
        await hub.register_agent("agent-2", AgentType.SPECIALIST, [])

        message = AgentMessage(
            message_id="msg-5",
            sender_id="agent-1",
            receiver_id="agent-2",
            message_type=MessageType.TASK_REQUEST,
            priority=MessagePriority.HIGH,
            content={},
            timestamp=datetime.now(timezone.utc),
            correlation_id="conv-1",
        )

        await hub.send_message(message)

        assert "conv-1" in hub.active_conversations
        assert len(hub.active_conversations["conv-1"]) == 1


class TestMessageStatistics:
    """Test message statistics tracking"""

    @pytest.mark.asyncio
    async def test_send_message_updates_statistics(self):
        """Test sending message updates statistics"""
        hub = CommunicationHub()
        await hub.register_agent("agent-1", AgentType.SPECIALIST, [])
        await hub.register_agent("agent-2", AgentType.SPECIALIST, [])

        message = AgentMessage(
            message_id="msg-6",
            sender_id="agent-1",
            receiver_id="agent-2",
            message_type=MessageType.TASK_REQUEST,
            priority=MessagePriority.HIGH,
            content={},
            timestamp=datetime.now(timezone.utc),
        )

        await hub.send_message(message)

        assert "task_request" in hub.message_statistics
        assert hub.message_statistics["task_request"] >= 1
