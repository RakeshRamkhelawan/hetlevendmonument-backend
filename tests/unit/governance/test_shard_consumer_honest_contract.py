"""Tests for honest contract and bounded memory in ShardConsumer."""

from __future__ import annotations

import logging
from collections import deque
import pytest

from src.core.governance.governance_agent.sharding import ShardConsumer


@pytest.mark.asyncio
async def test_shard_consumer_start_raises_not_implemented_honestly() -> None:
    """ShardConsumer.start() must raise NotImplementedError per ADR-006 until wired to Redis Pub/Sub."""
    consumer = ShardConsumer(shard_id=0, tenant_id=1, queue_name="test.queue")
    with pytest.raises(NotImplementedError) as exc_info:
        await consumer.start()
    assert "ADR-006" in str(exc_info.value)
    assert not hasattr(consumer, "is_running") or not consumer.is_running


@pytest.mark.asyncio
async def test_shard_consumer_handle_violations_logs_and_bounds_memory(caplog: pytest.LogCaptureFixture) -> None:
    """_handle_violations must emit structured warnings and bound recorded violations in memory."""
    consumer = ShardConsumer(shard_id=2, tenant_id=5, queue_name="test.queue")

    test_violations = [
        {"event_id": f"evt-{i}", "reason": f"violation_{i}"}
        for i in range(10)
    ]

    with caplog.at_level(logging.WARNING):
        await consumer._handle_violations(test_violations)

    # Verify structured logging
    assert any("Governance policy violation detected on shard 2" in record.message for record in caplog.records)

    # Verify bounded memory structure
    assert isinstance(consumer.recorded_violations, deque)
    assert consumer.recorded_violations.maxlen == ShardConsumer.MAX_BUFFER
    assert len(consumer.recorded_violations) == 10


@pytest.mark.asyncio
async def test_shard_consumer_recorded_violations_does_not_exceed_max_buffer() -> None:
    """Adding more than MAX_BUFFER violations must not grow unboundedly."""
    consumer = ShardConsumer(shard_id=1, tenant_id=10, queue_name="test.queue")

    excess_count = ShardConsumer.MAX_BUFFER + 50
    violations = [
        {"event_id": f"evt-{i}", "reason": "overflow_test"}
        for i in range(excess_count)
    ]

    await consumer._handle_violations(violations)
    assert len(consumer.recorded_violations) == ShardConsumer.MAX_BUFFER
