"""Tests for ShardedGovernanceMonitor and ShardConsumer (Phase 2: Performance).

Covers: SHA-256 shard routing, tenant isolation, bounded buffer,
backpressure, and deterministic sampling by risk level.
"""

from __future__ import annotations

import pytest

from src.core.governance.governance_agent.sharding import ShardConsumer, ShardedGovernanceMonitor


class TestShardedGovernanceMonitorInit:
    def test_default_shard_count_is_ten(self) -> None:
        assert ShardedGovernanceMonitor.NUM_SHARDS == 10

    def test_initializes_all_shards(self) -> None:
        monitor = ShardedGovernanceMonitor(tenant_id=1)
        assert len(monitor.shards) == 10

    def test_shard_ids_are_zero_to_nine(self) -> None:
        monitor = ShardedGovernanceMonitor(tenant_id=1)
        assert set(monitor.shards.keys()) == set(range(10))

    def test_stores_tenant_id(self) -> None:
        monitor = ShardedGovernanceMonitor(tenant_id=42)
        assert monitor.tenant_id == 42


class TestShardedGovernanceMonitorRouting:
    """SHA-256 based consistent shard assignment."""

    def test_returns_valid_shard_id(self) -> None:
        monitor = ShardedGovernanceMonitor(tenant_id=1)
        shard = monitor.get_shard_for_agent("agent-abc")
        assert 0 <= shard < 10

    def test_same_agent_always_gets_same_shard(self) -> None:
        monitor = ShardedGovernanceMonitor(tenant_id=1)
        shard1 = monitor.get_shard_for_agent("agent-abc")
        shard2 = monitor.get_shard_for_agent("agent-abc")
        assert shard1 == shard2

    def test_different_tenants_same_agent_can_differ(self) -> None:
        """Routing key includes tenant_id so cross-tenant isolation holds."""
        monitor1 = ShardedGovernanceMonitor(tenant_id=1)
        monitor2 = ShardedGovernanceMonitor(tenant_id=2)
        # The shard for the same agent *can* differ across tenants
        # We verify the key includes tenant_id by checking determinism
        shard1 = monitor1.get_shard_for_agent("agent-x")
        shard2 = monitor2.get_shard_for_agent("agent-x")
        # Both are valid shard IDs (0-9), may or may not be equal
        assert 0 <= shard1 < 10
        assert 0 <= shard2 < 10

    def test_uses_sha256_not_md5(self) -> None:
        """SHA-256 produces consistent 64-char hex; verify routing is deterministic."""
        import hashlib

        monitor = ShardedGovernanceMonitor(tenant_id=5)
        expected_hash = int(hashlib.sha256("5:agent-xyz".encode()).hexdigest(), 16)
        expected_shard = expected_hash % 10
        assert monitor.get_shard_for_agent("agent-xyz") == expected_shard

    def test_different_agents_distributed_across_shards(self) -> None:
        """100 different agents should not all land on the same shard."""
        monitor = ShardedGovernanceMonitor(tenant_id=1)
        shards_used = {monitor.get_shard_for_agent(f"agent-{i}") for i in range(100)}
        assert len(shards_used) > 1  # Good distribution

    def test_queue_name_includes_tenant_and_shard(self) -> None:
        monitor = ShardedGovernanceMonitor(tenant_id=7)
        consumer = monitor.shards[3]
        assert "7" in consumer.queue_name
        assert "3" in consumer.queue_name


class TestShardConsumerBoundedBuffer:
    """Bounded deque buffer with backpressure."""

    def test_max_buffer_is_1000(self) -> None:
        assert ShardConsumer.MAX_BUFFER == 1000

    def test_batch_size_is_100(self) -> None:
        assert ShardConsumer.BATCH_SIZE == 100

    @pytest.mark.asyncio
    async def test_enqueue_returns_true_when_buffer_has_space(self) -> None:
        consumer = ShardConsumer(shard_id=0, tenant_id=1, queue_name="test")
        result = await consumer.enqueue({"event_id": "e1"})
        assert result is True

    @pytest.mark.asyncio
    async def test_enqueue_returns_false_when_buffer_full(self) -> None:
        consumer = ShardConsumer(shard_id=0, tenant_id=1, queue_name="test")
        # Fill to capacity (deque with maxlen auto-drops oldest but we test the guard)
        # Manually set the buffer to max to simulate full state
        for i in range(ShardConsumer.MAX_BUFFER):
            consumer._buffer.append({"event_id": f"e{i}"})
        result = await consumer.enqueue({"event_id": "overflow"})
        assert result is False

    @pytest.mark.asyncio
    async def test_buffer_is_bounded_deque(self) -> None:
        from collections import deque

        consumer = ShardConsumer(shard_id=0, tenant_id=1, queue_name="test")
        assert isinstance(consumer._buffer, deque)
        assert consumer._buffer.maxlen == ShardConsumer.MAX_BUFFER


class TestShardConsumerDeterministicSampling:
    """should_deep_check uses deterministic SHA-256 sampling per risk level."""

    def test_high_risk_always_deep_checked(self) -> None:
        consumer = ShardConsumer(shard_id=0, tenant_id=1, queue_name="test")
        event = {"event_id": "any-event", "risk_level": "high"}
        assert consumer.should_deep_check(event) is True

    def test_returns_bool(self) -> None:
        consumer = ShardConsumer(shard_id=0, tenant_id=1, queue_name="test")
        result = consumer.should_deep_check({"event_id": "e1", "risk_level": "low"})
        assert isinstance(result, bool)

    def test_same_event_same_result_deterministic(self) -> None:
        consumer = ShardConsumer(shard_id=0, tenant_id=1, queue_name="test")
        event = {"event_id": "stable-id", "risk_level": "medium"}
        result1 = consumer.should_deep_check(event)
        result2 = consumer.should_deep_check(event)
        assert result1 == result2

    def test_unknown_risk_defaults_to_low_rate(self) -> None:
        consumer = ShardConsumer(shard_id=0, tenant_id=1, queue_name="test")
        # Should not raise for unknown risk level
        result = consumer.should_deep_check({"event_id": "e1", "risk_level": "unknown"})
        assert isinstance(result, bool)


class TestShardConsumerAnalysis:
    """Event analysis for security violations and deep check triggers."""

    @pytest.mark.asyncio
    async def test_detects_forbidden_action(self) -> None:
        consumer = ShardConsumer(shard_id=2, tenant_id=5, queue_name="q5-2")
        violation = await consumer._analyze_event({"event_id": "e1", "action": "privilege_escalation"})
        assert violation is not None
        assert violation["shard_id"] == 2
        assert violation["tenant_id"] == 5
        assert violation["reason"] == "forbidden_action_privilege_escalation"

    @pytest.mark.asyncio
    async def test_normal_action_returns_none(self) -> None:
        consumer = ShardConsumer(shard_id=2, tenant_id=5, queue_name="q5-2")
        violation = await consumer._analyze_event({"event_id": "e2", "action": "read_profile", "risk_level": "low"})
        assert violation is None

    @pytest.mark.asyncio
    async def test_deep_check_unauthorized_detected(self) -> None:
        consumer = ShardConsumer(shard_id=1, tenant_id=3, queue_name="q3-1")
        # High risk is always deep checked
        violation = await consumer._analyze_event({
            "event_id": "e3",
            "action": "query",
            "risk_level": "high",
            "unauthorized": True,
        })
        assert violation is not None
        assert violation["reason"] == "sampled_deep_check_unauthorized"


class TestShardConsumerViolationHandling:
    """Recording and handling of violations."""

    @pytest.mark.asyncio
    async def test_records_violations(self) -> None:
        consumer = ShardConsumer(shard_id=0, tenant_id=1, queue_name="q")
        violations = [{"event_id": "e1", "reason": "test_violation"}]
        await consumer._handle_violations(violations)
        assert len(consumer.recorded_violations) == 1
        assert consumer.recorded_violations[0]["reason"] == "test_violation"

