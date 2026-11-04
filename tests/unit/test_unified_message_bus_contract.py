"""Contract tests for unified message bus transport helpers (Phase C3)."""

from src.core.protocol import (
    MDPMessageFactory,
    MDPMessagePriority,
    TaskAssignmentMessage,
    decode_from_transport,
    decode_mmdp_message,
    encode_for_transport,
    is_collaboration_message,
    is_mmdp_message,
)
from src.core.shared.interfaces import AgentType


def test_bus_roundtrip_for_collaboration_message() -> None:
    message = TaskAssignmentMessage.create_task_assignment(
        sender_id="orchestrator",
        recipient_id="knowledge_agent",
        task_name="Index docs",
        task_type="knowledge_index",
        task_parameters={"collection": "default"},
    )

    encoded = encode_for_transport(message)
    decoded = decode_from_transport(encoded)

    assert is_collaboration_message(decoded)
    assert not is_mmdp_message(decoded)


def test_bus_roundtrip_for_mmdp_message() -> None:
    message = MDPMessageFactory.create_command_message(
        sender_id="cva",
        sender_type=AgentType.CVA,
        recipient_id="orchestrator",
        command_type="delegate",
        parameters={"goal": "optimize"},
        priority=MDPMessagePriority.HIGH,
    )

    encoded = encode_for_transport(message)
    decoded = decode_mmdp_message(encoded)

    assert decoded.payload.command_type == "delegate"
    assert decoded.header.sender_id == "cva"
