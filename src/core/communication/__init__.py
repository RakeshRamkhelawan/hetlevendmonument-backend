"""
M-MDP Communication Module
Provides JSON messaging protocol and agent-to-agent communication capabilities
"""

from typing import Any

from .communication_manager import CommunicationManager, communication_manager
from .message_protocol import (
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

__all__ = [
    "MessageType",
    "MessagePriority",
    "MessageStatus",
    "MessageHeader",
    "MessagePayload",
    "CommandMessage",
    "TaskAssignmentMessage",
    "StatusUpdateMessage",
    "ResultMessage",
    "FeedbackMessage",
    "TelemetryMessage",
    "MDPMessage",
    "MessageFactory",
    "CommunicationManager",
    "communication_manager",
]
