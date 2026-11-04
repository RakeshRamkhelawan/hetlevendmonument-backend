"""
Unified protocol entrypoint.

This package provides a canonical import surface for message protocol types while
keeping backward compatibility with legacy modules.
"""

from .agent_card import AgentCard, AgentCardAuth, build_agent_card, validate_agent_card
from .unified_message_bus import decode_from_transport, decode_mmdp_message, encode_for_transport
from .unified_message_protocol import (
    AgentHeartbeatMessage,
    AgentRegistrationMessage,
    BaseMessage,
    CollaborationAgentMessage,
    CollaborationMessagePriority,
    CollaborationMessageType,
    MDPMessage,
    MDPMessageFactory,
    MDPMessagePriority,
    MDPMessageType,
    TaskAssignmentMessage,
    TaskStatus,
    TaskStatusUpdateMessage,
    UnifiedMessage,
    deserialize_unified_message,
    is_collaboration_message,
    is_mmdp_message,
    serialize_unified_message,
)

__all__ = [
    "BaseMessage",
    "TaskAssignmentMessage",
    "TaskStatusUpdateMessage",
    "AgentRegistrationMessage",
    "AgentHeartbeatMessage",
    "TaskStatus",
    "CollaborationAgentMessage",
    "CollaborationMessageType",
    "CollaborationMessagePriority",
    "MDPMessage",
    "MDPMessageType",
    "MDPMessagePriority",
    "MDPMessageFactory",
    "UnifiedMessage",
    "is_collaboration_message",
    "is_mmdp_message",
    "serialize_unified_message",
    "deserialize_unified_message",
    "AgentCard",
    "AgentCardAuth",
    "build_agent_card",
    "validate_agent_card",
    "encode_for_transport",
    "decode_from_transport",
    "decode_mmdp_message",
]
