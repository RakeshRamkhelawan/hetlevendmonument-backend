#!/usr/bin/env python3
"""
M-MDP Communication Protocol Implementation
JSON messaging schema for agent-to-agent communication with telemetry
"""

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from src.core.types import AgentType


class MessageType(Enum):
    """Types of messages in the M-MDP communication protocol"""

    COMMAND = "command"  # CVA -> Orchestrator strategic commands
    TASK_ASSIGNMENT = "task_assignment"  # Orchestrator -> SubAgents task delegation
    STATUS_UPDATE = "status_update"  # SubAgents -> Orchestrator progress reports
    RESULT = "result"  # SubAgents -> Orchestrator task results
    FEEDBACK = "feedback"  # Orchestrator -> CVA execution feedback
    TELEMETRY = "telemetry"  # Performance metrics and learning data
    HEARTBEAT = "heartbeat"  # Agent health and availability
    ERROR = "error"  # Error reporting and handling


class MessagePriority(Enum):
    """Message priority levels for processing order"""

    EMERGENCY = 0  # Immediate processing required
    HIGH = 1  # High priority processing
    NORMAL = 2  # Standard processing
    LOW = 3  # Background processing


class MessageStatus(Enum):
    """Message processing status"""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    EXPIRED = "expired"


@dataclass
class MessageHeader:
    """Standard message header for all M-MDP communications"""

    message_id: str
    message_type: MessageType
    sender_id: str
    sender_type: AgentType
    recipient_id: str
    recipient_type: AgentType
    timestamp: datetime
    priority: MessagePriority = MessagePriority.NORMAL
    correlation_id: str | None = None  # For tracking conversation threads
    expires_at: datetime | None = None


@dataclass
class MessagePayload:
    """Base message payload structure"""

    data: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    metadata: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type


@dataclass
class CommandMessage(MessagePayload):
    """CVA strategic command message to orchestrator"""

    masterprompt: str | None = None
    expected_agents: list[str] = field(default_factory=list)
    command_type: str = ""
    parameters: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    memory_context: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type

    def __post_init__(self) -> None:
        if self.memory_context is None:
            self.memory_context = {}


@dataclass
class TaskAssignmentMessage(MessagePayload):
    """Orchestrator task assignment message to subagents"""

    deadline: datetime | None = None
    resource_allocation: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    dependency_tasks: list[str] = field(default_factory=list)
    task_id: str = ""
    task_type: str = ""
    task_description: str = ""
    agent_capabilities_required: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.resource_allocation is None:
            self.resource_allocation = {}


@dataclass
class StatusUpdateMessage(MessagePayload):
    """SubAgent status update message"""

    estimated_completion: datetime | None = None
    issues_encountered: list[str] = field(default_factory=list)
    task_id: str = ""
    progress_percentage: float = 0.0
    current_step: str = ""

    def __post_init__(self) -> None:
        self.progress_percentage = max(0.0, min(100.0, float(self.progress_percentage)))


@dataclass
class ResultMessage(MessagePayload):
    """SubAgent task result message"""

    quality_score: float | None = None
    error_details: str | None = None
    task_id: str = ""
    success: bool = False
    result_data: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    execution_time: float = 0.0

    def __post_init__(self) -> None:
        self.execution_time = max(0.0, float(self.execution_time))
        if self.quality_score is not None:
            self.quality_score = max(0.0, min(1.0, float(self.quality_score)))


@dataclass
class FeedbackMessage(MessagePayload):
    """Orchestrator feedback message to CVA"""

    strategic_insights: str | None = None
    command_id: str = ""
    execution_summary: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    performance_metrics: dict[str, float] = field(default_factory=dict)
    lessons_learned: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if self.execution_summary is None:
            self.execution_summary = {}
        if self.performance_metrics is None:
            self.performance_metrics = {}


@dataclass
class TelemetryMessage(MessagePayload):
    """Telemetry data for performance monitoring and learning"""

    learning_data: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    agent_id: str = ""
    metrics: dict[str, float | int | str] = field(default_factory=dict)
    performance_indicators: dict[str, float] = field(default_factory=dict)
    resource_usage: dict[str, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.learning_data is None:
            self.learning_data = {}


@dataclass
class MDPMessage:
    """Complete M-MDP message structure"""

    header: MessageHeader
    payload: MessagePayload
    status: MessageStatus = MessageStatus.PENDING

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert message to dictionary for JSON serialization"""
        return {
            "header": {
                **asdict(self.header),
                "timestamp": self.header.timestamp.isoformat(),
                "expires_at": (
                    self.header.expires_at.isoformat() if self.header.expires_at else None
                ),
                "message_type": self.header.message_type.value,
                "sender_type": self.header.sender_type.value,
                "recipient_type": self.header.recipient_type.value,
                "priority": self.header.priority.value,
            },
            "payload": asdict(self.payload),
            "status": self.status.value,
        }

    def to_json(self) -> str:
        """Convert message to JSON string"""
        return json.dumps(self.to_dict(), default=str)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MDPMessage":  # TODO(TYPE): replace Any with concrete type
        """Create message from dictionary"""
        header_data = data["header"]
        expires_at_value = header_data.get("expires_at")
        expires_at: datetime | None = (
            datetime.fromisoformat(expires_at_value) if expires_at_value is not None else None
        )

        header = MessageHeader(
            message_id=header_data["message_id"],
            message_type=MessageType(header_data["message_type"]),
            sender_id=header_data["sender_id"],
            sender_type=AgentType(header_data["sender_type"]),
            recipient_id=header_data["recipient_id"],
            recipient_type=AgentType(header_data["recipient_type"]),
            timestamp=datetime.fromisoformat(header_data["timestamp"]),
            priority=MessagePriority(header_data["priority"]),
            correlation_id=header_data.get("correlation_id"),
            expires_at=expires_at,
        )

        # Create appropriate payload based on message type
        payload_data = data["payload"]
        payload: (
            CommandMessage |
            TaskAssignmentMessage |
            StatusUpdateMessage |
            ResultMessage |
            FeedbackMessage |
            TelemetryMessage |
            MessagePayload
        )
        if header.message_type == MessageType.COMMAND:
            payload = CommandMessage(**payload_data)
        elif header.message_type == MessageType.TASK_ASSIGNMENT:
            payload = TaskAssignmentMessage(**payload_data)
        elif header.message_type == MessageType.STATUS_UPDATE:
            payload = StatusUpdateMessage(**payload_data)
        elif header.message_type == MessageType.RESULT:
            payload = ResultMessage(**payload_data)
        elif header.message_type == MessageType.FEEDBACK:
            payload = FeedbackMessage(**payload_data)
        elif header.message_type == MessageType.TELEMETRY:
            payload = TelemetryMessage(**payload_data)
        else:
            payload = MessagePayload(**payload_data)

        return cls(header=header, payload=payload, status=MessageStatus(data["status"]))

    @classmethod
    def from_json(cls, json_str: str) -> "MDPMessage":
        """Create message from JSON string"""
        return cls.from_dict(json.loads(json_str))


class MessageFactory:
    """Factory for creating standard M-MDP messages"""

    @staticmethod
    def create_command_message(
        sender_id: str,
        sender_type: AgentType,
        recipient_id: str,
        command_type: str,
        parameters: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        masterprompt: str | None = None,
        priority: MessagePriority = MessagePriority.NORMAL,
    ) -> MDPMessage:
        """Create a strategic command message from CVA to Orchestrator"""

        header = MessageHeader(
            message_id=str(uuid.uuid4()),
            message_type=MessageType.COMMAND,
            sender_id=sender_id,
            sender_type=sender_type,
            recipient_id=recipient_id,
            recipient_type=AgentType.ORCHESTRATOR,
            timestamp=datetime.now(timezone.utc),
            priority=priority,
        )

        payload = CommandMessage(
            data={},  # Base data field required
            command_type=command_type,
            parameters=parameters,
            masterprompt=masterprompt,
        )

        return MDPMessage(header=header, payload=payload)

    @staticmethod
    def create_task_assignment_message(
        sender_id: str,
        recipient_id: str,
        recipient_type: AgentType,
        task_id: str,
        task_type: str,
        task_description: str,
        capabilities_required: list[str],
        deadline: datetime | None = None,
    ) -> MDPMessage:
        """Create a task assignment message from Orchestrator to SubAgent"""

        header = MessageHeader(
            message_id=str(uuid.uuid4()),
            message_type=MessageType.TASK_ASSIGNMENT,
            sender_id=sender_id,
            sender_type=AgentType.ORCHESTRATOR,
            recipient_id=recipient_id,
            recipient_type=recipient_type,
            timestamp=datetime.now(timezone.utc),
            priority=MessagePriority.HIGH,
        )

        payload = TaskAssignmentMessage(
            data={},  # Base data field required
            task_id=task_id,
            task_type=task_type,
            task_description=task_description,
            agent_capabilities_required=capabilities_required,
            deadline=deadline,
        )

        return MDPMessage(header=header, payload=payload)

    @staticmethod
    def create_status_update_message(
        sender_id: str,
        sender_type: AgentType,
        recipient_id: str,
        task_id: str,
        progress_percentage: float,
        current_step: str,
    ) -> MDPMessage:
        """Create a status update message from SubAgent to Orchestrator"""

        header = MessageHeader(
            message_id=str(uuid.uuid4()),
            message_type=MessageType.STATUS_UPDATE,
            sender_id=sender_id,
            sender_type=sender_type,
            recipient_id=recipient_id,
            recipient_type=AgentType.ORCHESTRATOR,
            timestamp=datetime.now(timezone.utc),
            priority=MessagePriority.NORMAL,
        )

        payload = StatusUpdateMessage(
            data={},  # Base data field required
            task_id=task_id,
            progress_percentage=progress_percentage,
            current_step=current_step,
        )

        return MDPMessage(header=header, payload=payload)

    @staticmethod
    def create_telemetry_message(
        sender_id: str,
        sender_type: AgentType,
        metrics: dict[str, float | int | str],
        performance_indicators: dict[str, float],
        resource_usage: dict[str, float],
    ) -> MDPMessage:
        """Create a telemetry message for performance monitoring"""

        header = MessageHeader(
            message_id=str(uuid.uuid4()),
            message_type=MessageType.TELEMETRY,
            sender_id=sender_id,
            sender_type=sender_type,
            recipient_id="system_monitor",
            recipient_type=AgentType.ORCHESTRATOR,  # System monitor is part of orchestrator
            timestamp=datetime.now(timezone.utc),
            priority=MessagePriority.LOW,
        )

        payload = TelemetryMessage(
            data={},  # Base data field required
            agent_id=sender_id,
            metrics=metrics,
            performance_indicators=performance_indicators,
            resource_usage=resource_usage,
        )

        return MDPMessage(header=header, payload=payload)
