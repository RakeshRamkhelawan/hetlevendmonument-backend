"""Contract tests for the unified protocol facade.

Validates that both message families (collaboration + M-MDP) are supported
through the canonical protocol API.
"""

from datetime import datetime

from src.core.protocol import (
    MDPMessageFactory,
    MDPMessagePriority,
    TaskAssignmentMessage,
    deserialize_unified_message,
    is_collaboration_message,
    is_mmdp_message,
    serialize_unified_message,
)
from src.core.shared.interfaces import AgentType


def test_collaboration_family_roundtrip_via_unified_facade() -> None:
    """Collaboration protocol message serializes/deserializes via unified facade."""
    original = TaskAssignmentMessage.create_task_assignment(
        sender_id="orchestrator",
        recipient_id="knowledge_agent",
        task_name="Index knowledge",
        task_type="knowledge_index",
        task_parameters={"action": "create_knowledge", "content": "doc"},
    )

    encoded = serialize_unified_message(original)
    decoded = deserialize_unified_message(encoded)

    assert is_collaboration_message(decoded)
    assert not is_mmdp_message(decoded)
    assert isinstance(decoded, TaskAssignmentMessage)
    assert decoded.task_name == original.task_name
    assert decoded.task_type == original.task_type
    assert decoded.task_parameters["action"] == "create_knowledge"


def test_mmdp_family_roundtrip_via_unified_facade() -> None:
    """M-MDP message serializes/deserializes via unified facade."""
    original = MDPMessageFactory.create_command_message(
        sender_id="cva_main",
        sender_type=AgentType.CVA,
        recipient_id="ultimate_orchestrator",
        command_type="delegate",
        parameters={"goal": "optimize_ops"},
        masterprompt="execute strategic delegation",
        priority=MDPMessagePriority.HIGH,
    )

    encoded = serialize_unified_message(original)
    decoded = deserialize_unified_message(encoded)

    assert is_mmdp_message(decoded)
    assert not is_collaboration_message(decoded)
    assert decoded.header.sender_id == "cva_main"
    assert decoded.header.recipient_id == "ultimate_orchestrator"
    assert decoded.payload.command_type == "delegate"
    assert decoded.payload.parameters["goal"] == "optimize_ops"
