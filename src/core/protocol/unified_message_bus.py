"""Unified message bus transport helpers.

This module is the canonical encode/decode entrypoint for message transport,
independent of the underlying message family.
"""

from .unified_message_protocol import (
    UnifiedMessage,
    deserialize_unified_message,
    is_mmdp_message,
    serialize_unified_message,
)


def encode_for_transport(message: UnifiedMessage) -> str:
    """Encode any supported message family to a transport payload."""
    return serialize_unified_message(message)


def decode_from_transport(payload: str) -> UnifiedMessage:
    """Decode transport payload to a typed unified message."""
    return deserialize_unified_message(payload)


def decode_mmdp_message(payload: str) -> UnifiedMessage:
    """Decode payload and enforce M-MDP message type for M-MDP queues."""
    message = decode_from_transport(payload)
    if not is_mmdp_message(message):
        raise TypeError("Expected M-MDP message payload")
    return message
