"""Unit tests for ALS Infrastructure (without external dependencies)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.als.infrastructure.signal_bus import Signal, SignalTier


class TestSignal:
    """Test Signal dataclass."""

    def test_signal_creation_happy_path(self):
        """Happy path: Create valid signal."""
        signal = Signal(
            tenant_id=123,
            source_agent_id="test_agent",
            target_agent_ids=["agent_1", "agent_2"],
            tier=SignalTier.COGNITIVE,
            payload={"action": "test", "data": "value"},
        )

        assert signal.tenant_id == 123
        assert signal.source_agent_id == "test_agent"
        assert len(signal.target_agent_ids) == 2
        assert signal.tier == SignalTier.COGNITIVE
        assert signal.payload["action"] == "test"
        assert signal.signal_id is not None  # Auto-generated

    def test_signal_broadcast_happy_path(self):
        """Happy path: Create broadcast signal (no targets)."""
        signal = Signal(
            tenant_id=123,
            source_agent_id="test_agent",
            target_agent_ids=[],  # Empty = broadcast
            tier=SignalTier.BROADCAST,
            payload={"message": "hello all"},
        )

        assert signal.target_agent_ids == []

    def test_signal_to_json_happy_path(self):
        """Happy path: Serialize to JSON."""
        signal = Signal(
            tenant_id=123,
            source_agent_id="test_agent",
            target_agent_ids=[],
            tier=SignalTier.COGNITIVE,
            payload={"test": True},
        )

        json_str = signal.to_json()
        assert "test_agent" in json_str
        assert "COGNITIVE" in json_str

    def test_signal_from_json_happy_path(self):
        """Happy path: Deserialize from JSON."""
        original = Signal(
            tenant_id=123,
            source_agent_id="test_agent",
            target_agent_ids=[],
            tier=SignalTier.REFLEX,
            payload={"test": True},
        )

        json_str = original.to_json()
        restored = Signal.from_json(json_str)

        assert restored.tenant_id == original.tenant_id
        assert restored.source_agent_id == original.source_agent_id
        assert restored.tier == original.tier


class TestSignalTier:
    """Test SignalTier enum."""

    def test_all_tiers_defined(self):
        """Happy path: All tiers exist."""
        assert SignalTier.REFLEX.value == "reflex"
        assert SignalTier.COGNITIVE.value == "cognitive"
        assert SignalTier.EMOTIONAL.value == "emotional"
        assert SignalTier.SYNAPTIC.value == "synaptic"
        assert SignalTier.BROADCAST.value == "broadcast"
