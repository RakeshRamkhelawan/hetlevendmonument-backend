"""
Collaboration Module - Production Implementation
Multi-Agent communication services voor FASE 2
"""

from typing import Any

from .message_protocol import (
    AgentHeartbeatMessage,
    AgentRegistrationMessage,
    BaseMessage,
    MessagePriority,
    MessageType,
    TaskAssignmentMessage,
    TaskStatus,
    TaskStatusUpdateMessage,
    deserialize_message,
    serialize_message,
)

__all__ = [
    "BaseMessage",
    "TaskAssignmentMessage",
    "TaskStatusUpdateMessage",
    "AgentRegistrationMessage",
    "AgentHeartbeatMessage",
    "MessageType",
    "MessagePriority",
    "TaskStatus",
    "serialize_message",
    "deserialize_message",
]
