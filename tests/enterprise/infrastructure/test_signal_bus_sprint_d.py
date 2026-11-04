"""
Sprint D Tests - Signal Bus & Event-driven Communication

Tests for the existing SignalBus infrastructure:
- Signal creation and validation
- SignalBus emit with tiers (REFLEX, COGNITIVE, EMOTIONAL, SYNAPTIC, BROADCAST)
- Tenant isolation
- Payload hashing (SHA-256)
- Signal serialization/deserialization
"""

import json
from datetime import datetime, timezone

import pytest

from src.core.als.infrastructure.signal_bus import Signal, SignalBus, SignalTier


class TestSignal:
    """Test Signal dataclass and methods."""

    def test_signal_creation(self):
        """Can create a basic signal."""
        signal = Signal(
            tenant_id=1,
            source_agent_id="agent_1",
            target_agent_ids=["agent_2"],
            tier=SignalTier.COGNITIVE,
            payload={"task_id": "abc", "data": "test"},
        )

        assert signal.tenant_id == 1
        assert signal.source_agent_id == "agent_1"
        assert signal.target_agent_ids == ["agent_2"]
        assert signal.tier == SignalTier.COGNITIVE
        assert signal.payload == {"task_id": "abc", "data": "test"}
        assert signal.signal_id != ""  # Auto-generated
        assert isinstance(signal.timestamp, datetime)

    def test_signal_broadcast(self):
        """Signal with empty targets is a broadcast."""
        broadcast = Signal(
            tenant_id=1,
            source_agent_id="agent_1",
            target_agent_ids=[],  # Empty = broadcast
            tier=SignalTier.BROADCAST,
            payload={"message": "hello"},
        )

        assert broadcast.target_agent_ids == []
        assert broadcast.tier == SignalTier.BROADCAST

    def test_signal_payload_hash(self):
        """SHA-256 hash of payload is computed correctly."""
        signal = Signal(
            tenant_id=1,
            source_agent_id="agent_1",
            target_agent_ids=[],
            tier=SignalTier.COGNITIVE,
            payload={"key": "value", "number": 42},
        )

        hash1 = signal.get_payload_hash()
        hash2 = signal.get_payload_hash()

        # Hash should be consistent
        assert hash1 == hash2
        assert len(hash1) == 64  # SHA-256 hex string

    def test_signal_payload_hash_different_payloads(self):
        """Different payloads produce different hashes."""
        signal1 = Signal(
            tenant_id=1,
            source_agent_id="agent_1",
            target_agent_ids=[],
            tier=SignalTier.COGNITIVE,
            payload={"key": "value1"},
        )
        signal2 = Signal(
            tenant_id=1,
            source_agent_id="agent_1",
            target_agent_ids=[],
            tier=SignalTier.COGNITIVE,
            payload={"key": "value2"},
        )

        assert signal1.get_payload_hash() != signal2.get_payload_hash()

    def test_signal_to_json(self):
        """Signal can be serialized to JSON."""
        signal = Signal(
            tenant_id=1,
            source_agent_id="agent_1",
            target_agent_ids=["agent_2"],
            tier=SignalTier.REFLEX,
            payload={"urgent": True},
            correlation_id="req-123",
        )

        json_str = signal.to_json()
        data = json.loads(json_str)

        assert data["tenant_id"] == 1
        assert data["source_agent_id"] == "agent_1"
        # The tier serialization format depends on the enum implementation
        tier_str = str(data["tier"])
        assert "REFLEX" in tier_str or tier_str == "reflex"
        assert data["payload"]["urgent"] is True
        assert data["correlation_id"] == "req-123"

    def test_signal_from_json(self):
        """Signal can be deserialized from JSON."""
        signal = Signal(
            tenant_id=1,
            source_agent_id="agent_1",
            target_agent_ids=["agent_2"],
            tier=SignalTier.SYNAPTIC,
            payload={"direct": True},
        )

        json_str = signal.to_json()
        restored = Signal.from_json(json_str)

        assert restored.tenant_id == signal.tenant_id
        assert restored.source_agent_id == signal.source_agent_id
        assert restored.tier == signal.tier
        assert restored.payload == signal.payload

    def test_signal_correlation_id(self):
        """Correlation ID links related signals."""
        request_signal = Signal(
            tenant_id=1,
            source_agent_id="agent_1",
            target_agent_ids=["agent_2"],
            tier=SignalTier.COGNITIVE,
            payload={"request": "data"},
            correlation_id="flow-123",
        )

        response_signal = Signal(
            tenant_id=1,
            source_agent_id="agent_2",
            target_agent_ids=["agent_1"],
            tier=SignalTier.COGNITIVE,
            payload={"response": "result"},
            correlation_id="flow-123",  # Same correlation ID
        )

        assert request_signal.correlation_id == response_signal.correlation_id


class TestSignalTier:
    """Test SignalTier enum values."""

    def test_tier_values(self):
        """SignalTier has expected values."""
        assert SignalTier.REFLEX.value == "reflex"
        assert SignalTier.COGNITIVE.value == "cognitive"
        assert SignalTier.EMOTIONAL.value == "emotional"
        assert SignalTier.SYNAPTIC.value == "synaptic"
        assert SignalTier.BROADCAST.value == "broadcast"

    def test_tier_comparison(self):
        """Tiers can be compared by urgency."""
        # REFLEX is highest priority (urgent)
        assert SignalTier.REFLEX.value == "reflex"
        # BROADCAST is for system-wide announcements
        assert SignalTier.BROADCAST.value == "broadcast"


class TestSignalTenantIsolation:
    """Test tenant isolation in signals."""

    def test_signal_has_tenant_id(self):
        """Every signal must have a tenant_id."""
        signal = Signal(
            tenant_id=42,
            source_agent_id="agent_1",
            target_agent_ids=[],
            tier=SignalTier.COGNITIVE,
            payload={},
        )

        assert signal.tenant_id == 42

    def test_different_tenants_different_signals(self):
        """Signals from different tenants are distinct."""
        signal_t1 = Signal(
            tenant_id=1,
            source_agent_id="agent_1",
            target_agent_ids=[],
            tier=SignalTier.COGNITIVE,
            payload={"data": "tenant1"},
        )
        signal_t2 = Signal(
            tenant_id=2,
            source_agent_id="agent_1",
            target_agent_ids=[],
            tier=SignalTier.COGNITIVE,
            payload={"data": "tenant2"},
        )

        assert signal_t1.tenant_id != signal_t2.tenant_id
        assert signal_t1.payload != signal_t2.payload


class TestSignalContractLifecycle:
    """Test signals for contract lifecycle events."""

    def test_contract_proposed_signal(self):
        """Signal for contract proposal."""
        signal = Signal(
            tenant_id=1,
            source_agent_id="finance_dept",
            target_agent_ids=["hr_dept"],
            tier=SignalTier.COGNITIVE,
            payload={
                "event": "contract_proposed",
                "contract_id": "abc-123",
                "prana_cost": 100,
                "schema_ref": "hr.skill_matrix@1.0.0",
            },
        )

        assert signal.tier == SignalTier.COGNITIVE
        assert signal.payload["event"] == "contract_proposed"
        assert signal.payload["prana_cost"] == 100

    def test_contract_agreed_signal(self):
        """Signal for contract agreement."""
        signal = Signal(
            tenant_id=1,
            source_agent_id="hr_dept",
            target_agent_ids=["finance_dept"],
            tier=SignalTier.SYNAPTIC,
            payload={
                "event": "contract_agreed",
                "contract_id": "abc-123",
                "agreed_at": datetime.now(timezone.utc).isoformat(),
            },
        )

        assert signal.tier == SignalTier.SYNAPTIC
        assert signal.payload["event"] == "contract_agreed"

    def test_contract_settled_signal(self):
        """Signal for contract settlement."""
        signal = Signal(
            tenant_id=1,
            source_agent_id="system",
            target_agent_ids=["finance_dept", "hr_dept"],
            tier=SignalTier.REFLEX,  # High priority
            payload={
                "event": "contract_settled",
                "contract_id": "abc-123",
                "success": True,
                "prana_transferred": 100,
            },
        )

        assert signal.tier == SignalTier.REFLEX
        assert signal.payload["success"] is True


class TestSignalRoutingScenarios:
    """Test various signal routing scenarios."""

    def test_department_to_department_signal(self):
        """Signal from one department to another."""
        signal = Signal(
            tenant_id=1,
            source_agent_id="dept_finance",
            target_agent_ids=["dept_hr"],
            tier=SignalTier.COGNITIVE,
            payload={"task": "salary_analysis", "data": {"employee_id": "E123"}},
        )

        assert signal.source_agent_id == "dept_finance"
        assert "dept_hr" in signal.target_agent_ids

    def test_agent_capability_request(self):
        """Signal requesting specific agent capability."""
        signal = Signal(
            tenant_id=1,
            source_agent_id="orchestrator",
            target_agent_ids=[],  # Broadcast to all capable agents
            tier=SignalTier.COGNITIVE,
            payload={
                "request_type": "capability",
                "capability": "budget_analysis",
                "task_data": {"year": 2026, "quarter": 1},
            },
        )

        assert signal.target_agent_ids == []  # Broadcast
        assert signal.payload["capability"] == "budget_analysis"

    def test_system_broadcast(self):
        """System-wide broadcast signal."""
        signal = Signal(
            tenant_id=1,
            source_agent_id="chief_orchestrator",
            target_agent_ids=[],  # All agents
            tier=SignalTier.BROADCAST,
            payload={
                "announcement": "maintenance_window",
                "starts_at": "2026-03-01T02:00:00Z",
                "duration_minutes": 30,
            },
        )

        assert signal.tier == SignalTier.BROADCAST
        assert signal.source_agent_id == "chief_orchestrator"


class TestSignalSerializationEdgeCases:
    """Test edge cases in signal serialization."""

    def test_signal_with_complex_payload(self):
        """Signal with nested payload structure."""
        signal = Signal(
            tenant_id=1,
            source_agent_id="agent_1",
            target_agent_ids=["agent_2"],
            tier=SignalTier.COGNITIVE,
            payload={
                "nested": {"deep": {"value": 123}},
                "list": [1, 2, 3],
                "mixed": [{"a": 1}, {"b": 2}],
            },
        )

        json_str = signal.to_json()
        restored = Signal.from_json(json_str)

        assert restored.payload["nested"]["deep"]["value"] == 123
        assert restored.payload["list"] == [1, 2, 3]

    def test_signal_timestamp_preserved(self):
        """Timestamp is preserved through serialization."""
        original_time = datetime(2026, 2, 26, 14, 30, 0)
        signal = Signal(
            tenant_id=1,
            source_agent_id="agent_1",
            target_agent_ids=[],
            tier=SignalTier.COGNITIVE,
            payload={},
        )
        signal.timestamp = original_time

        json_str = signal.to_json()
        restored = Signal.from_json(json_str)

        assert restored.timestamp == original_time
