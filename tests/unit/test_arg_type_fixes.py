"""
Test suite for arg-type error fixes in message protocol implementations.

Focus areas:
- Union type assignments (specific msg types → generic MessagePayload)
- Optional parameter handling and datetime narrowing
- Agent type narrowing with isinstance checks
- Enum construction and validation
"""

import json
import pytest
from datetime import datetime, timedelta, timezone
from typing import Any, Dict
from uuid import uuid4

from src.core.communication.message_protocol import (
    CommandMessage,
    FeedbackMessage,
    MDPMessage,
    MessageFactory,
    MessageHeader,
    MessagePayload,
    MessagePriority,
    MessageStatus,
    MessageType,
    ResultMessage,
    StatusUpdateMessage,
    TaskAssignmentMessage,
    TelemetryMessage,
)
from src.core.types import AgentType


class TestMDPMessagePayloadUnionTypes:
    """Test proper Union typing for MDPMessage payload creation"""

    @pytest.mark.unit
    def test_from_dict_command_message_creates_correct_type(self) -> None:
        """Should create CommandMessage when message_type is COMMAND"""
        msg_id = str(uuid4())
        data = {
            "header": {
                "message_id": msg_id,
                "message_type": MessageType.COMMAND.value,
                "sender_id": "agent_1",
                "sender_type": AgentType.ORCHESTRATOR.value,
                "recipient_id": "agent_2",
                "recipient_type": AgentType.ORCHESTRATOR.value,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "priority": MessagePriority.HIGH.value,
                "correlation_id": None,
                "expires_at": None,
            },
            "payload": {
                "data": {"test": "data"},
                "metadata": {},
                "command_type": "execute",
                "parameters": {"key": "value"},
            },
            "status": MessageStatus.PENDING.value,
        }

        message = MDPMessage.from_dict(data)

        assert isinstance(message, MDPMessage)
        assert isinstance(message.payload, CommandMessage)
        assert message.payload.command_type == "execute"
        assert message.header.message_type == MessageType.COMMAND

    @pytest.mark.unit
    def test_from_dict_task_assignment_creates_correct_type(self) -> None:
        """Should create TaskAssignmentMessage when message_type is TASK_ASSIGNMENT"""
        msg_id = str(uuid4())
        data = {
            "header": {
                "message_id": msg_id,
                "message_type": MessageType.TASK_ASSIGNMENT.value,
                "sender_id": "orchestrator_1",
                "sender_type": AgentType.ORCHESTRATOR.value,
                "recipient_id": "agent_1",
                "recipient_type": AgentType.SPECIALIST.value,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "priority": MessagePriority.NORMAL.value,
                "correlation_id": None,
                "expires_at": None,
            },
            "payload": {
                "data": {},
                "task_id": "task_123",
                "task_type": "analysis",
                "task_description": "Analyze data",
                "agent_capabilities_required": ["analysis"],
                "dependency_tasks": [],
            },
            "status": MessageStatus.PENDING.value,
        }

        message = MDPMessage.from_dict(data)

        assert isinstance(message, MDPMessage)
        assert isinstance(message.payload, TaskAssignmentMessage)
        assert message.payload.task_type == "analysis"

    @pytest.mark.unit
    def test_from_dict_status_update_creates_correct_type(self) -> None:
        """Should create StatusUpdateMessage when message_type is STATUS_UPDATE"""
        msg_id = str(uuid4())
        data = {
            "header": {
                "message_id": msg_id,
                "message_type": MessageType.STATUS_UPDATE.value,
                "sender_id": "agent_1",
                "sender_type": AgentType.SPECIALIST.value,
                "recipient_id": "orchestrator_1",
                "recipient_type": AgentType.ORCHESTRATOR.value,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "priority": MessagePriority.NORMAL.value,
                "correlation_id": None,
                "expires_at": None,
            },
            "payload": {
                "data": {},
                "task_id": "task_123",
                "progress_percentage": 50.0,
                "current_step": "Step 1",
                "issues_encountered": [],
            },
            "status": MessageStatus.PROCESSING.value,
        }

        message = MDPMessage.from_dict(data)

        assert isinstance(message, MDPMessage)
        assert isinstance(message.payload, StatusUpdateMessage)
        assert message.payload.progress_percentage == 50.0

    @pytest.mark.unit
    def test_from_dict_result_creates_correct_type(self) -> None:
        """Should create ResultMessage when message_type is RESULT"""
        msg_id = str(uuid4())
        data = {
            "header": {
                "message_id": msg_id,
                "message_type": MessageType.RESULT.value,
                "sender_id": "agent_1",
                "sender_type": AgentType.SPECIALIST.value,
                "recipient_id": "orchestrator_1",
                "recipient_type": AgentType.ORCHESTRATOR.value,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "priority": MessagePriority.NORMAL.value,
                "correlation_id": None,
                "expires_at": None,
            },
            "payload": {
                "data": {},
                "task_id": "task_123",
                "success": True,
                "result_data": {"result": "success"},
                "execution_time": 10.5,
            },
            "status": MessageStatus.COMPLETED.value,
        }

        message = MDPMessage.from_dict(data)

        assert isinstance(message, MDPMessage)
        assert isinstance(message.payload, ResultMessage)
        assert message.payload.success is True

    @pytest.mark.unit
    def test_from_dict_feedback_creates_correct_type(self) -> None:
        """Should create FeedbackMessage when message_type is FEEDBACK"""
        msg_id = str(uuid4())
        data = {
            "header": {
                "message_id": msg_id,
                "message_type": MessageType.FEEDBACK.value,
                "sender_id": "orchestrator_1",
                "sender_type": AgentType.ORCHESTRATOR.value,
                "recipient_id": "cva_1",
                "recipient_type": AgentType.ORCHESTRATOR.value,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "priority": MessagePriority.NORMAL.value,
                "correlation_id": None,
                "expires_at": None,
            },
            "payload": {
                "data": {},
                "command_id": "cmd_123",
                "execution_summary": {"status": "complete"},
                "performance_metrics": {"latency": 1.5},
            },
            "status": MessageStatus.COMPLETED.value,
        }

        message = MDPMessage.from_dict(data)

        assert isinstance(message, MDPMessage)
        assert isinstance(message.payload, FeedbackMessage)
        assert message.payload.command_id == "cmd_123"

    @pytest.mark.unit
    def test_from_dict_telemetry_creates_correct_type(self) -> None:
        """Should create TelemetryMessage when message_type is TELEMETRY"""
        msg_id = str(uuid4())
        data = {
            "header": {
                "message_id": msg_id,
                "message_type": MessageType.TELEMETRY.value,
                "sender_id": "agent_1",
                "sender_type": AgentType.SPECIALIST.value,
                "recipient_id": "system_monitor",
                "recipient_type": AgentType.ORCHESTRATOR.value,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "priority": MessagePriority.LOW.value,
                "correlation_id": None,
                "expires_at": None,
            },
            "payload": {
                "data": {},
                "agent_id": "agent_1",
                "metrics": {"cpu": 50.0, "memory": 75.0},
                "performance_indicators": {"latency": 1.2},
                "resource_usage": {"cpu": 50.0},
            },
            "status": MessageStatus.PENDING.value,
        }

        message = MDPMessage.from_dict(data)

        assert isinstance(message, MDPMessage)
        assert isinstance(message.payload, TelemetryMessage)
        assert message.payload.agent_id == "agent_1"

    @pytest.mark.unit
    def test_from_dict_error_message_creates_base_payload(self) -> None:
        """Should create base MessagePayload for ERROR message type"""
        msg_id = str(uuid4())
        data = {
            "header": {
                "message_id": msg_id,
                "message_type": MessageType.ERROR.value,
                "sender_id": "agent_1",
                "sender_type": AgentType.SPECIALIST.value,
                "recipient_id": "agent_2",
                "recipient_type": AgentType.ORCHESTRATOR.value,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "priority": MessagePriority.NORMAL.value,
                "correlation_id": None,
                "expires_at": None,
            },
            "payload": {"data": {"error": "unknown"}},
            "status": MessageStatus.FAILED.value,
        }

        # ERROR type should default to base MessagePayload
        message = MDPMessage.from_dict(data)

        assert isinstance(message, MDPMessage)
        assert isinstance(message.payload, MessagePayload)


class TestOptionalDatetimeHandling:
    """Test proper handling of Optional datetime parameters"""

    @pytest.mark.unit
    def test_from_dict_with_expires_at_none(self) -> None:
        """Should handle None expires_at correctly"""
        msg_id = str(uuid4())
        data = {
            "header": {
                "message_id": msg_id,
                "message_type": MessageType.COMMAND.value,
                "sender_id": "agent_1",
                "sender_type": AgentType.ORCHESTRATOR.value,
                "recipient_id": "agent_2",
                "recipient_type": AgentType.ORCHESTRATOR.value,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "priority": MessagePriority.NORMAL.value,
                "correlation_id": None,
                "expires_at": None,
            },
            "payload": {"data": {}},
            "status": MessageStatus.PENDING.value,
        }

        message = MDPMessage.from_dict(data)

        assert message.header.expires_at is None

    @pytest.mark.unit
    def test_from_dict_with_expires_at_datetime_string(self) -> None:
        """Should parse expires_at ISO format datetime string"""
        msg_id = str(uuid4())
        future_time = datetime.now(timezone.utc) + timedelta(hours=1)
        data = {
            "header": {
                "message_id": msg_id,
                "message_type": MessageType.COMMAND.value,
                "sender_id": "agent_1",
                "sender_type": AgentType.ORCHESTRATOR.value,
                "recipient_id": "agent_2",
                "recipient_type": AgentType.ORCHESTRATOR.value,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "priority": MessagePriority.NORMAL.value,
                "correlation_id": None,
                "expires_at": future_time.isoformat(),
            },
            "payload": {"data": {}},
            "status": MessageStatus.PENDING.value,
        }

        message = MDPMessage.from_dict(data)

        assert message.header.expires_at is not None
        assert isinstance(message.header.expires_at, datetime)

    @pytest.mark.unit
    def test_from_dict_missing_expires_at_key(self) -> None:
        """Should handle missing expires_at key in header data"""
        msg_id = str(uuid4())
        data = {
            "header": {
                "message_id": msg_id,
                "message_type": MessageType.COMMAND.value,
                "sender_id": "agent_1",
                "sender_type": AgentType.ORCHESTRATOR.value,
                "recipient_id": "agent_2",
                "recipient_type": AgentType.ORCHESTRATOR.value,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "priority": MessagePriority.NORMAL.value,
                "correlation_id": None,
                # expires_at not included
            },
            "payload": {"data": {}},
            "status": MessageStatus.PENDING.value,
        }

        message = MDPMessage.from_dict(data)

        assert message.header.expires_at is None


class TestMessageFactoryEnumHandling:
    """Test enum creation and validation in message factory methods"""

    @pytest.mark.unit
    def test_create_command_message_with_normal_priority(self) -> None:
        """Should create command message with NORMAL priority"""
        message = MessageFactory.create_command_message(
            sender_id="cva_1",
            sender_type=AgentType.ORCHESTRATOR,
            recipient_id="orchestrator_1",
            command_type="start",
            parameters={"task": "analyze"},
            priority=MessagePriority.NORMAL,
        )

        assert isinstance(message, MDPMessage)
        assert message.header.priority == MessagePriority.NORMAL
        assert message.header.message_type == MessageType.COMMAND

    @pytest.mark.unit
    def test_create_task_assignment_message_with_high_priority(self) -> None:
        """Should create task assignment with HIGH priority"""
        message = MessageFactory.create_task_assignment_message(
            sender_id="orchestrator_1",
            recipient_id="agent_1",
            recipient_type=AgentType.SPECIALIST,
            task_id="task_123",
            task_type="analysis",
            task_description="Analyze dataset",
            capabilities_required=["data_analysis"],
        )

        assert isinstance(message, MDPMessage)
        assert message.header.priority == MessagePriority.HIGH
        assert message.header.message_type == MessageType.TASK_ASSIGNMENT

    @pytest.mark.unit
    def test_message_round_trip_serialization(self) -> None:
        """Should serialize and deserialize without type loss"""
        original = MessageFactory.create_command_message(
            sender_id="cva_1",
            sender_type=AgentType.ORCHESTRATOR,
            recipient_id="orchestrator_1",
            command_type="start",
            parameters={"test": "data"},
        )

        # Serialize to dict and back
        data_dict = original.to_dict()
        restored = MDPMessage.from_dict(data_dict)

        assert isinstance(restored.payload, CommandMessage)
        assert restored.header.message_type == original.header.message_type
        assert restored.payload.command_type == original.payload.command_type


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
