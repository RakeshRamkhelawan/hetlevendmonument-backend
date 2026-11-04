"""
Message Protocol - Production Implementation
Pydantic-modellen voor multi-agent communicatie zoals gespecificeerd in FASE 2 STAP 2.1
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class MessageType(str, Enum):
    """Message types voor agent communicatie"""

    BASE = "base"
    TASK_ASSIGNMENT = "task_assignment"
    TASK_STATUS_UPDATE = "task_status_update"
    AGENT_REGISTRATION = "agent_registration"
    AGENT_HEARTBEAT = "agent_heartbeat"
    AGENT_DISCOVERY = "agent_discovery"
    SYSTEM_NOTIFICATION = "system_notification"


class MessagePriority(str, Enum):
    """Message priority levels"""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class TaskStatus(str, Enum):
    """Task execution status"""

    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class BaseMessage(BaseModel):
    """
    Base message model - gestandaardiseerde taal voor agent communicatie
    Zoals gespecificeerd in FASE 2 STAP 2.1
    """

    model_config = ConfigDict(use_enum_values=True, arbitrary_types_allowed=True, extra="forbid")

    # Core message identification
    message_id: UUID = Field(default_factory=uuid4, description="Unique message identifier")
    message_type: MessageType = Field(description="Type of the message")
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="Message creation timestamp"
    )

    # Routing information
    sender_id: str = Field(description="ID of the sending agent")
    recipient_id: str | None = Field(
        default=None, description="ID of the recipient agent (None for broadcast)"
    )
    correlation_id: UUID | None = Field(
        default=None, description="ID to correlate related messages"
    )

    # Message metadata
    priority: MessagePriority = Field(
        default=MessagePriority.NORMAL, description="Message priority"
    )
    expires_at: datetime | None = Field(default=None, description="Message expiration timestamp")
    retry_count: int = Field(default=0, description="Number of delivery retries")
    max_retries: int = Field(default=3, description="Maximum number of retries")

    # Message content
    payload: dict[str, Any] = Field(default_factory=dict, description="Message payload data")  # TODO(TYPE): replace Any with concrete type
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")  # TODO(TYPE): replace Any with concrete type

    def is_expired(self) -> bool:
        """Check if message has expired"""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at

    def can_retry(self) -> bool:
        """Check if message can be retried"""
        return self.retry_count < self.max_retries

    def increment_retry(self) -> None:
        """Increment retry counter"""
        self.retry_count += 1


class TaskAssignmentMessage(BaseMessage):
    """
    Task assignment message - zoals gespecificeerd in FASE 2 STAP 2.1
    Voor het toewijzen van taken aan agents
    """

    message_type: MessageType = Field(default=MessageType.TASK_ASSIGNMENT, frozen=True)

    # Task identification
    task_id: UUID = Field(default_factory=uuid4, description="Unique task identifier")
    task_name: str = Field(description="Human-readable task name")
    task_type: str = Field(description="Type/category of the task")

    # Task parameters
    task_parameters: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict, description="Task execution parameters"
    )
    required_capabilities: list[str] = Field(
        default_factory=list, description="Required agent capabilities"
    )
    estimated_duration: int | None = Field(
        default=None, description="Estimated duration in seconds"
    )

    # Task constraints
    deadline: datetime | None = Field(default=None, description="Task completion deadline")
    dependencies: list[UUID] = Field(
        default_factory=list, description="Task dependencies (other task IDs)"
    )

    # Result expectations
    expected_result_format: str = Field(default="json", description="Expected result format")
    callback_url: str | None = Field(default=None, description="URL for result callback")

    @classmethod
    def create_task_assignment(
        cls,
        sender_id: str,
        recipient_id: str,
        task_name: str,
        task_type: str,
        task_parameters: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        priority: MessagePriority = MessagePriority.NORMAL,
        deadline: datetime | None = None,
    ) -> "TaskAssignmentMessage":
        """Factory method voor task assignment creation"""
        return cls(
            sender_id=sender_id,
            recipient_id=recipient_id,
            task_name=task_name,
            task_type=task_type,
            task_parameters=task_parameters or {},
            priority=priority,
            deadline=deadline,
        )


class TaskStatusUpdateMessage(BaseMessage):
    """
    Task status update message - zoals gespecificeerd in FASE 2 STAP 2.1
    Voor het rapporteren van task execution status
    """

    message_type: MessageType = Field(default=MessageType.TASK_STATUS_UPDATE, frozen=True)

    # Task reference
    task_id: UUID = Field(description="Task identifier being updated")
    original_assignment_id: UUID = Field(description="Original task assignment message ID")

    # Status information
    status: TaskStatus = Field(description="Current task status")
    progress_percentage: float = Field(
        default=0.0, ge=0.0, le=100.0, description="Task completion percentage"
    )
    status_message: str | None = Field(default=None, description="Human-readable status message")

    # Execution details
    started_at: datetime | None = Field(default=None, description="Task start timestamp")
    completed_at: datetime | None = Field(default=None, description="Task completion timestamp")
    execution_time: float | None = Field(default=None, description="Execution time in seconds")

    # Results and errors
    result: dict[str, Any] | None = Field(default=None, description="Task execution result")  # TODO(TYPE): replace Any with concrete type
    error_details: dict[str, Any] | None = Field(  # TODO(TYPE): replace Any with concrete type
        default=None, description="Error details if task failed"
    )
    logs: list[str] = Field(default_factory=list, description="Execution logs")

    # Resource usage
    resource_usage: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict, description="Resource usage metrics"
    )

    @classmethod
    def create_status_update(
        cls,
        sender_id: str,
        recipient_id: str,
        task_id: UUID,
        original_assignment_id: UUID,
        status: TaskStatus,
        progress_percentage: float = 0.0,
        result: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        error_details: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> "TaskStatusUpdateMessage":
        """Factory method voor status update creation"""
        return cls(
            sender_id=sender_id,
            recipient_id=recipient_id,
            task_id=task_id,
            original_assignment_id=original_assignment_id,
            status=status,
            progress_percentage=progress_percentage,
            result=result,
            error_details=error_details,
            completed_at=(
                datetime.now(timezone.utc)
                if status in [TaskStatus.COMPLETED, TaskStatus.FAILED]
                else None
            ),
        )


class AgentRegistrationMessage(BaseMessage):
    """Agent registration message voor AgentMesh"""

    message_type: MessageType = Field(default=MessageType.AGENT_REGISTRATION, frozen=True)

    # Agent information
    agent_id: str = Field(description="Unique agent identifier")
    agent_name: str = Field(description="Human-readable agent name")
    agent_type: str = Field(description="Type/category of the agent")
    agent_version: str = Field(default="1.0.0", description="Agent version")

    # Connection details
    address: str = Field(description="Agent network address (URL)")
    port: int = Field(description="Agent listening port")
    endpoints: dict[str, str] = Field(default_factory=dict, description="Available endpoints")

    # Capabilities
    capabilities: list[str] = Field(default_factory=list, description="Agent capabilities")
    max_concurrent_tasks: int = Field(default=1, description="Maximum concurrent tasks")
    supported_task_types: list[str] = Field(
        default_factory=list, description="Supported task types"
    )

    # Status
    status: str = Field(default="online", description="Agent status")
    health_check_url: str | None = Field(default=None, description="Health check endpoint")


class AgentHeartbeatMessage(BaseMessage):
    """Agent heartbeat message voor liveness detection"""

    message_type: MessageType = Field(default=MessageType.AGENT_HEARTBEAT, frozen=True)

    # Agent status
    agent_id: str = Field(description="Agent identifier")
    status: str = Field(default="online", description="Current agent status")
    current_load: float = Field(
        default=0.0, ge=0.0, le=100.0, description="Current load percentage"
    )
    active_tasks: int = Field(default=0, description="Number of active tasks")

    # System metrics
    cpu_usage: float = Field(default=0.0, description="CPU usage percentage")
    memory_usage: float = Field(default=0.0, description="Memory usage percentage")
    uptime: float = Field(default=0.0, description="Agent uptime in seconds")


# Message union type voor type checking
AgentMessage = (
    BaseMessage
    | TaskAssignmentMessage
    | TaskStatusUpdateMessage
    | AgentRegistrationMessage
    | AgentHeartbeatMessage
)


def serialize_message(message: AgentMessage) -> str:
    """
    Serialize message to JSON string
    """
    return message.model_dump_json()


def deserialize_message(message_data: str) -> AgentMessage:
    """
    Deserialize JSON string to appropriate message type
    """
    import json

    # Parse JSON to get message_type
    data = json.loads(message_data)
    message_type = data.get("message_type")

    # Map message types to classes
    message_classes: dict[str, type[BaseMessage]] = {
        MessageType.BASE: BaseMessage,
        MessageType.TASK_ASSIGNMENT: TaskAssignmentMessage,
        MessageType.TASK_STATUS_UPDATE: TaskStatusUpdateMessage,
        MessageType.AGENT_REGISTRATION: AgentRegistrationMessage,
        MessageType.AGENT_HEARTBEAT: AgentHeartbeatMessage,
    }

    # Get appropriate class
    message_class = message_classes.get(message_type, BaseMessage)

    # Deserialize to appropriate type
    return message_class.model_validate(data)
