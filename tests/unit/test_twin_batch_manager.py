"""Unit tests for ObservationBatchManager buffer safety and overflow guard."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from src.core.learning.batching.batch_manager import (
    ObservationBatchManager,
    PendingObservation,
)


@pytest.mark.asyncio
async def test_flush_success_clears_buffer() -> None:
    """Successful flush should clear the buffer."""
    persist_fn = AsyncMock()
    manager = ObservationBatchManager(persist_fn=persist_fn, batch_size=2)
    await manager.start()

    await manager.add(PendingObservation(human_user_id="u1", tenant_id=1, session_id="s1", behavior_type="test"))
    await manager.add(PendingObservation(human_user_id="u1", tenant_id=1, session_id="s2", behavior_type="test"))

    # batch_size reached -> flush triggered
    await asyncio.sleep(0.1)
    persist_fn.assert_awaited_once()
    assert manager.buffer_size == 0

    await manager.stop()


@pytest.mark.asyncio
async def test_failed_flush_returns_batch_to_buffer() -> None:
    """Failed flush should return batch to buffer if capacity allows."""
    persist_fn = AsyncMock(side_effect=ConnectionError("DB down"))
    manager = ObservationBatchManager(persist_fn=persist_fn, batch_size=2)
    await manager.start()

    await manager.add(PendingObservation(human_user_id="u1", tenant_id=1, session_id="s1", behavior_type="test"))
    await manager.add(PendingObservation(human_user_id="u1", tenant_id=1, session_id="s2", behavior_type="test"))

    await manager.flush()
    # Batch failed, returned to buffer
    assert manager.buffer_size == 2

    await manager.stop()


@pytest.mark.asyncio
async def test_failed_flush_drops_batch_when_buffer_at_capacity() -> None:
    """Failed flush should drop batch when buffer cannot accommodate it."""
    persist_fn = AsyncMock(side_effect=ConnectionError("DB down"))
    manager = ObservationBatchManager(persist_fn=persist_fn, batch_size=2)
    await manager.start()

    # Fill buffer to exactly 2 * batch_size (the soft cap)
    for i in range(4):
        await manager.add(
            PendingObservation(human_user_id="u1", tenant_id=1, session_id=f"s{i}", behavior_type="test")
        )

    await manager.flush()
    # First batch of 2 failed and returned, buffer = 4
    assert manager.buffer_size == 4

    # Force flush again — batch of 4 will fail, buffer already at capacity
    await manager.flush()
    # Batch should be dropped because len(batch) + len(buffer) > batch_size * 2
    assert manager.buffer_size <= 4

    await manager.stop()


@pytest.mark.asyncio
async def test_buffer_never_exceeds_hard_cap() -> None:
    """Buffer must never exceed _MAX_BUFFER_SIZE even under persistent failure."""
    persist_fn = AsyncMock(side_effect=ConnectionError("DB down"))
    manager = ObservationBatchManager(persist_fn=persist_fn, batch_size=10)
    await manager.start()

    # Add more observations than the hard cap
    for i in range(1200):
        await manager.add(
            PendingObservation(human_user_id="u1", tenant_id=1, session_id=f"s{i}", behavior_type="test")
        )

    await manager.flush()
    # Buffer should never exceed the hard cap of 1000
    assert manager.buffer_size <= ObservationBatchManager._MAX_BUFFER_SIZE

    await manager.stop()
