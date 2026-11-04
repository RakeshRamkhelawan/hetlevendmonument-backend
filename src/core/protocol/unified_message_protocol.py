"""
Unified message protocol facade.

Phase C start implementation:
- Introduces a canonical import path for protocol types.
- Preserves legacy behavior by re-exporting existing protocol implementations.
- Enables incremental migration without breaking current call sites.
"""

import json
from typing import cast

from src.core.collaboration.message_protocol import AgentHeartbeatMessage
from src.core.collaboration.message_protocol import AgentMessage as CollaborationAgentMessage
from src.core.collaboration.message_protocol import AgentRegistrationMessage, BaseMessage
from src.core.collaboration.message_protocol import MessagePriority as CollaborationMessagePriority
from src.core.collaboration.message_protocol import MessageType as CollaborationMessageType
from src.core.collaboration.message_protocol import (
    TaskAssignmentMessage,
    TaskStatus,
    TaskStatusUpdateMessage,
)
from src.core.collaboration.message_protocol import (
    deserialize_message as deserialize_collaboration_message,
)
from src.core.collaboration.message_protocol import (
    serialize_message as serialize_collaboration_message,
)
from src.core.communication.message_protocol import MDPMessage
from src.core.communication.message_protocol import MessageFactory as MDPMessageFactory
from src.core.communication.message_protocol import MessagePriority as MDPMessagePriority
from src.core.communication.message_protocol import MessageType as MDPMessageType

UnifiedMessage = CollaborationAgentMessage | MDPMessage


def is_collaboration_message(message: object) -> bool:
    """Return True when the message is a collaboration protocol message."""
    return hasattr(message, "model_dump_json") and not hasattr(message, "to_json")


def is_mmdp_message(message: object) -> bool:
    """Return True when the message is an M-MDP message."""
    return isinstance(message, MDPMessage)


def serialize_unified_message(message: UnifiedMessage) -> str:
    """Serialize either protocol message through the matching serializer."""
    if is_mmdp_message(message):
        return cast(MDPMessage, message).to_json()
    return serialize_collaboration_message(cast(CollaborationAgentMessage, message))


def deserialize_unified_message(message_data: str) -> UnifiedMessage:
    """Deserialize JSON to either M-MDP or collaboration protocol message.

    Detection strategy:
    - If the payload contains M-MDP envelope keys (`header` + `payload`), use MDP.
    - Otherwise treat it as collaboration protocol JSON.
    """
    parsed = json.loads(message_data)
    if isinstance(parsed, dict) and "header" in parsed and "payload" in parsed:
        return MDPMessage.from_json(message_data)
    return deserialize_collaboration_message(message_data)


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
]
