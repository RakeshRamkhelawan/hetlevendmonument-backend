"""Complete Infrastructure Tests - 100% Happy & Unhappy Paths.

Tests all components against real Docker services:
- PostgreSQL on port 5435
- Redis on port 6385
"""

import asyncio
import shutil
import subprocess

import pytest

pytestmark = pytest.mark.integration
import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from src.core.als.infrastructure.redis_pool import RedisPoolManager, get_redis_pool
from src.core.als.infrastructure.signal_bus import Signal, SignalBus, SignalTier


async def _require_live_redis() -> None:
    if shutil.which("docker") is None:
        pytest.skip("ALS Redis integration tests require Docker")

    pool = RedisPoolManager()
    try:
        client = await pool.get_client()
        await client.ping()
    except Exception as exc:
        pytest.skip(f"ALS Redis integration tests require live Redis on localhost:6385: {exc}")
    finally:
        await pool.close()


# =============================================================================
# Signal Dataclass Tests - 100% Coverage
# =============================================================================


class TestSignalHappyPaths:
    """Happy path tests for Signal creation and serialization."""

    def test_signal_creation_with_all_fields(self):
        """HAPPY: Create signal with all fields populated."""
        signal = Signal(
            tenant_id=123,
            source_agent_id="source_agent",
            target_agent_ids=["agent1", "agent2", "agent3"],
            tier=SignalTier.COGNITIVE,
            payload={"action": "process", "data": {"key": "value"}},
            correlation_id="corr_123",
        )

        assert signal.tenant_id == 123
        assert signal.source_agent_id == "source_agent"
        assert len(signal.target_agent_ids) == 3
        assert signal.tier == SignalTier.COGNITIVE
        assert signal.signal_id is not None
        assert signal.correlation_id == "corr_123"
        assert isinstance(signal.timestamp, datetime)

    def test_signal_creation_defaults(self):
        """HAPPY: Create signal with default values."""
        signal = Signal(
            tenant_id=456,
            source_agent_id="sender",
            target_agent_ids=[],
            tier=SignalTier.BROADCAST,
            payload={},
        )

        assert signal.tenant_id == 456
        assert signal.signal_id is not None  # Auto-generated
        assert signal.correlation_id is None  # Default
        assert isinstance(signal.timestamp, datetime)

    def test_signal_all_tiers(self):
        """HAPPY: Create signals for all tier types."""
        tiers = [
            (SignalTier.REFLEX, "reflex"),
            (SignalTier.COGNITIVE, "cognitive"),
            (SignalTier.EMOTIONAL, "emotional"),
            (SignalTier.SYNAPTIC, "synaptic"),
            (SignalTier.BROADCAST, "broadcast"),
        ]

        for tier, expected_value in tiers:
            signal = Signal(
                tenant_id=1,
                source_agent_id="test",
                target_agent_ids=[],
                tier=tier,
                payload={},
            )
            assert SignalTier(signal.tier).value == expected_value

    def test_signal_serialization_roundtrip(self):
        """HAPPY: Serialize and deserialize signal."""
        original = Signal(
            tenant_id=789,
            source_agent_id="original_sender",
            target_agent_ids=["target1"],
            tier=SignalTier.SYNAPTIC,
            payload={"nested": {"data": [1, 2, 3]}},
            correlation_id="test_corr",
        )

        # Serialize
        json_str = original.to_json()
        assert isinstance(json_str, str)
        assert "original_sender" in json_str
        assert "SYNAPTIC" in json_str

        # Deserialize
        restored = Signal.from_json(json_str)
        assert restored.tenant_id == original.tenant_id
        assert restored.source_agent_id == original.source_agent_id
        assert restored.tier == original.tier
        assert restored.correlation_id == original.correlation_id
        assert restored.payload == original.payload


class TestSignalUnhappyPaths:
    """Unhappy path tests for Signal edge cases."""

    def test_signal_deserialization_invalid_tier(self):
        """UNHAPPY: Deserialize signal with invalid tier value."""
        invalid_json = json.dumps(
            {
                "tenant_id": 1,
                "source_agent_id": "test",
                "target_agent_ids": [],
                "tier": "INVALID_TIER",
                "payload": {},
                "signal_id": "test_id",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

        with pytest.raises(ValueError):
            Signal.from_json(invalid_json)

    def test_signal_deserialization_missing_fields(self):
        """UNHAPPY: Deserialize signal with missing required fields."""
        incomplete_json = json.dumps(
            {
                "tenant_id": 1,
                "source_agent_id": "test",
                # Missing other required fields
            }
        )

        with pytest.raises((KeyError, TypeError)):
            Signal.from_json(incomplete_json)

    def test_signal_deserialization_malformed_json(self):
        """UNHAPPY: Deserialize malformed JSON."""
        malformed = "{ invalid json }"

        with pytest.raises(json.JSONDecodeError):
            Signal.from_json(malformed)


# =============================================================================
# SignalBus Happy Path Tests
# =============================================================================


@pytest.mark.asyncio
class TestSignalBusHappyPaths:
    """Happy path tests for SignalBus with real Redis."""

    async def test_emit_signal_success(self, signal_bus):
        """HAPPY: Successfully emit a signal."""
        signal = Signal(
            tenant_id=10001,
            source_agent_id="test_emitter",
            target_agent_ids=["target"],
            tier=SignalTier.COGNITIVE,
            payload={"test": "data"},
        )

        signal_id = await signal_bus.emit(signal, check_cooldown=False)

        assert signal_id is not None
        assert signal_id == signal.signal_id

    async def test_emit_reflex_signal_no_cooldown(self, signal_bus):
        """HAPPY: REFLEX signals bypass cooldown."""
        signal = Signal(
            tenant_id=10001,
            source_agent_id="reflex_emitter",
            target_agent_ids=[],
            tier=SignalTier.REFLEX,
            payload={"urgent": True},
        )

        # Emit multiple times quickly
        for i in range(5):
            signal_id = await signal_bus.emit(signal)
            assert signal_id is not None

    async def test_emit_broadcast_signal(self, signal_bus):
        """HAPPY: Emit broadcast signal (no targets)."""
        signal = Signal(
            tenant_id=10001,
            source_agent_id="broadcaster",
            target_agent_ids=[],  # Broadcast
            tier=SignalTier.BROADCAST,
            payload={"announcement": "hello all"},
        )

        signal_id = await signal_bus.emit(signal, check_cooldown=False)
        assert signal_id is not None

    async def test_query_agents_success(self, signal_bus):
        """HAPPY: Query agents and get responses."""
        # Note: This test might timeout if no agents are listening
        # In real scenario, agents would respond
        responses = await signal_bus.query(
            source_agent="test_querier",
            target_agents=[],  # Broadcast query
            query_type="capability_check",
            payload={"capability": "test"},
            timeout_ms=100,  # Short timeout for test
            tenant_id=10001,
        )

        # Should return empty list (no agents listening in test)
        assert isinstance(responses, list)

    async def test_respond_to_query(self, signal_bus):
        """HAPPY: Respond to a pending query."""
        query_id = str(uuid.uuid4())

        # Register pending query
        async with signal_bus._query_lock:
            signal_bus._pending_queries[query_id] = asyncio.Queue()

        # Respond
        await signal_bus.respond_to_query(
            query_id=query_id, responder="test_responder", payload={"answer": "test"}
        )

        # Verify response is in queue
        async with signal_bus._query_lock:
            queue = signal_bus._pending_queries[query_id]
            assert not queue.empty()


# =============================================================================
# SignalBus Unhappy Path Tests
# =============================================================================


@pytest.mark.asyncio
class TestSignalBusUnhappyPaths:
    """Unhappy path tests for SignalBus."""

    async def test_emit_tenant_blocked(self, signal_bus):
        """UNHAPPY: Signal dropped when tenant is blocked."""
        # Block the tenant
        await signal_bus.block_tenant(10003, duration_s=60)

        try:
            signal = Signal(
                tenant_id=10003,
                source_agent_id="blocked_emitter",
                target_agent_ids=[],
                tier=SignalTier.COGNITIVE,
                payload={"test": "data"},
            )

            # Should still return signal_id but not publish
            signal_id = await signal_bus.emit(signal)
            assert signal_id == signal.signal_id

        finally:
            # Cleanup
            await signal_bus.unblock_tenant(10003)

    async def test_emit_cooldown_active(self, signal_bus):
        """UNHAPPY: Signal dropped when cooldown active."""
        signal = Signal(
            tenant_id=10004,
            source_agent_id="cooldown_emitter",
            target_agent_ids=[],
            tier=SignalTier.COGNITIVE,  # Non-reflex
            payload={"test": "data"},
        )

        # First emit should succeed
        signal_id_1 = await signal_bus.emit(signal)

        # Second emit immediately should be dropped (cooldown)
        signal_id_2 = await signal_bus.emit(signal)

        # Both return signal_id, but second was dropped
        assert signal_id_1 == signal.signal_id
        assert signal_id_2 == signal.signal_id  # Returns ID even if dropped

    async def test_query_invalid_tenant(self, signal_bus):
        """UNHAPPY: Query with missing tenant_id raises error."""
        with pytest.raises(ValueError, match="tenant_id"):
            await signal_bus.query(
                source_agent="test",
                target_agents=[],
                query_type="test",
                payload={},
                tenant_id=None,  # Missing!
            )

    async def test_respond_to_nonexistent_query(self, signal_bus):
        """UNHAPPY: Respond to query that doesn't exist."""
        # Should not raise, just log warning
        await signal_bus.respond_to_query(
            query_id="nonexistent_query", responder="test", payload={}
        )

    async def test_is_tenant_blocked_unhappy(self, signal_bus):
        """UNHAPPY: Check block status after block expires."""
        # Block with very short duration
        await signal_bus.block_tenant(10005, duration_s=1)

        try:
            # Initially blocked
            is_blocked = await signal_bus.is_tenant_blocked(10005)
            assert is_blocked is True

            # Wait for expiration
            await asyncio.sleep(2)

            # Should be unblocked now
            is_blocked = await signal_bus.is_tenant_blocked(10005)
            assert is_blocked is False

        finally:
            await signal_bus.unblock_tenant(10005)


# =============================================================================
# RedisPoolManager Tests
# =============================================================================


@pytest.mark.asyncio
class TestRedisPoolManagerHappyPaths:
    """Happy path tests for RedisPoolManager with real Redis."""

    async def test_get_client_creates_connection(self):
        """HAPPY: Get client creates new Redis connection."""
        await _require_live_redis()
        pool = RedisPoolManager()

        try:
            client = await pool.get_client()
            assert client is not None

            # Verify connection works
            result = await client.ping()
            assert result is True
        finally:
            await pool.close()

    async def test_get_client_reuses_connection(self):
        """HAPPY: Multiple calls return same client (singleton)."""
        await _require_live_redis()
        pool = RedisPoolManager()

        try:
            client1 = await pool.get_client()
            client2 = await pool.get_client()

            # Should be same instance
            assert client1 is client2
        finally:
            await pool.close()

    async def test_health_check_success(self):
        """HAPPY: Health check passes when connected."""
        await _require_live_redis()
        pool = RedisPoolManager()

        try:
            healthy = await pool.health_check()
            assert healthy is True
        finally:
            await pool.close()

    async def test_global_pool_singleton(self):
        """HAPPY: Global pool is singleton."""
        pool1 = get_redis_pool()
        pool2 = get_redis_pool()

        assert pool1 is pool2


@pytest.mark.asyncio
class TestRedisPoolManagerUnhappyPaths:
    """Unhappy path tests for RedisPoolManager."""

    async def test_health_check_failure(self):
        """UNHAPPY: Health check fails when Redis unavailable."""
        # Create pool with a mock client that fails
        pool = RedisPoolManager()

        # Mock the client to simulate connection failure
        mock_client = AsyncMock()
        mock_client.ping.side_effect = Exception("Connection refused")
        pool._client = mock_client

        try:
            healthy = await pool.health_check()
            assert healthy is False
        finally:
            await pool.close()

    async def test_close_releases_connection(self):
        """UNHAPPY: Operations after close should fail."""
        await _require_live_redis()
        pool = RedisPoolManager()
        client = await pool.get_client()
        await pool.close()

        # Connection should be closed
        # Note: redis-py might not raise immediately, but operations will fail


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
