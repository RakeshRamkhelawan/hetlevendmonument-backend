"""
Unit tests voor ObservationBatchManager.

Controleert:
- add() buffers correct
- flush() leegt de buffer
- Flush wordt geactiveerd bij batch_size bereikt
- Exponential backoff bij flush-failure
- Buffer overflow bescherming (niet oneindig groeien)
- stop() doet final flush
- buffer_size property
- Geen persist_fn = geen crash (test mode)
"""

import asyncio
import time
from typing import List
from unittest.mock import AsyncMock, patch

import pytest

from src.core.learning.batching.batch_manager import (
    ObservationBatchManager,
    PendingObservation,
    get_batch_manager,
    reset_batch_manager,
    shutdown_batch_manager,
)


def _make_obs(behavior_type: str = "file_edit", user: str = "u1") -> PendingObservation:
    return PendingObservation(
        human_user_id=user,
        tenant_id=1,
        session_id="sess_abc",
        behavior_type=behavior_type,
        context={"edit_count": 1},
        outcome_metrics={},
        trace_id="trace_001",
    )


@pytest.mark.asyncio
class TestObservationBatchManagerUnit:
    """Unit tests — geen echte asyncio tasks."""

    async def test_add_buffers_observation(self):
        mgr = ObservationBatchManager(batch_size=10)
        obs = _make_obs()
        await mgr.add(obs)
        assert mgr.buffer_size == 1

    async def test_add_multiple_observations(self):
        mgr = ObservationBatchManager(batch_size=10)
        for _ in range(5):
            await mgr.add(_make_obs())
        assert mgr.buffer_size == 5

    async def test_flush_empties_buffer(self):
        persist = AsyncMock()
        mgr = ObservationBatchManager(persist_fn=persist, batch_size=10)

        for _ in range(3):
            await mgr.add(_make_obs())

        await mgr.flush()
        assert mgr.buffer_size == 0
        persist.assert_called_once()

    async def test_flush_passes_batch_to_persist(self):
        received: List = []

        async def fake_persist(batch):
            received.extend(batch)

        mgr = ObservationBatchManager(persist_fn=fake_persist, batch_size=10)
        obs1 = _make_obs("file_edit")
        obs2 = _make_obs("rapid_switch")
        await mgr.add(obs1)
        await mgr.add(obs2)
        await mgr.flush()

        assert len(received) == 2
        types = {o.behavior_type for o in received}
        assert types == {"file_edit", "rapid_switch"}

    async def test_flush_with_empty_buffer_is_noop(self):
        persist = AsyncMock()
        mgr = ObservationBatchManager(persist_fn=persist, batch_size=10)
        await mgr.flush()
        persist.assert_not_called()

    async def test_flush_no_persist_fn_does_not_crash(self):
        """Geen persist_fn = flush slaagt stil (test mode)."""
        mgr = ObservationBatchManager(persist_fn=None, batch_size=10)
        await mgr.add(_make_obs())
        await mgr.flush()
        assert mgr.buffer_size == 0

    async def test_buffer_size_property(self):
        mgr = ObservationBatchManager(batch_size=10)
        assert mgr.buffer_size == 0
        await mgr.add(_make_obs())
        assert mgr.buffer_size == 1


@pytest.mark.asyncio
class TestBatchManagerRetryLogic:
    """Tests voor retry- en fail-safe logica."""

    async def test_retry_on_failure_succeeds_on_second_attempt(self):
        call_count = 0

        async def flaky_persist(batch):
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise RuntimeError("DB unavailable")

        mgr = ObservationBatchManager(persist_fn=flaky_persist, batch_size=10)
        mgr._RETRY_BASE_DELAY = 0.01  # type: ignore  # speed up test

        await mgr.add(_make_obs())
        await mgr.flush()

        assert call_count == 2
        assert mgr.buffer_size == 0  # Buffer cleared after success

    async def test_buffer_restored_after_all_retries_fail(self):
        async def always_fail(batch):
            raise RuntimeError("permanent failure")

        mgr = ObservationBatchManager(persist_fn=always_fail, batch_size=10)
        mgr._RETRY_BASE_DELAY = 0.01  # type: ignore

        await mgr.add(_make_obs())
        await mgr.flush()

        # Buffer should be restored since failure count < batch_size * 2
        assert mgr.buffer_size == 1

    async def test_buffer_overflow_protection(self):
        """Verwijder batch als buffer al te vol is (voorkomt oneindige groei)."""

        async def always_fail(batch):
            raise RuntimeError("permanent failure")

        mgr = ObservationBatchManager(persist_fn=always_fail, batch_size=3)
        mgr._RETRY_BASE_DELAY = 0.01  # type: ignore

        # Vul buffer al voor flush
        for _ in range(7):  # 7 > 3 * 2 = 6
            mgr._buffer.append(_make_obs())

        # Probeer nog 1 observation te flushen
        batch = [_make_obs("extra")]
        await mgr._persist_with_retry(batch)

        # Batch mag NIET worden teruggeplaatst (buffer overflow bescherming)
        # De buffer is al op 7, batch_size * 2 = 6, dus buffer overflow triggered
        assert mgr.buffer_size == 7  # unchanged, batch dropped

    async def test_exactly_three_retry_attempts(self):
        call_count = 0

        async def always_fail(batch):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("fail")

        mgr = ObservationBatchManager(persist_fn=always_fail, batch_size=10)
        mgr._RETRY_BASE_DELAY = 0.001  # type: ignore

        await mgr._persist_with_retry([_make_obs()])
        assert call_count == 3  # MAX_RETRY_ATTEMPTS = 3


@pytest.mark.asyncio
class TestBatchManagerFlushTriggers:
    """Tests voor flush-triggers (batch_size, time-window)."""

    async def test_batch_size_triggers_flush_task(self):
        """batch_size bereikt → asyncio.create_task voor flush."""
        flush_calls = []

        async def counting_persist(batch):
            flush_calls.append(len(batch))

        mgr = ObservationBatchManager(
            persist_fn=counting_persist,
            batch_size=3,
            flush_interval_seconds=9999.0,
        )

        # Voeg batch_size observaties toe
        tasks = []
        for _ in range(3):
            await mgr.add(_make_obs())

        # Wacht kort zodat gecreëerde tasks kunnen runnen
        await asyncio.sleep(0.05)

        # Buffer moet nu geleegd zijn
        assert mgr.buffer_size == 0 or len(flush_calls) > 0


@pytest.mark.asyncio
class TestBatchManagerStopFlush:
    """Tests voor stop() final flush."""

    async def test_stop_does_final_flush(self):
        flushed = []

        async def capture_persist(batch):
            flushed.extend(batch)

        mgr = ObservationBatchManager(
            persist_fn=capture_persist,
            batch_size=100,
            flush_interval_seconds=9999.0,
        )
        await mgr.start()

        await mgr.add(_make_obs("work_start"))
        await mgr.add(_make_obs("file_edit"))

        await mgr.stop()

        assert len(flushed) == 2
        assert mgr.buffer_size == 0



@pytest.mark.asyncio
class TestBatchManagerSingleton:
    """Tests voor singleton getter/reset."""

    async def test_get_batch_manager_returns_same_instance(self):
        reset_batch_manager()
        mgr1 = await get_batch_manager(persist_fn=AsyncMock())
        mgr2 = await get_batch_manager()
        assert mgr1 is mgr2
        await shutdown_batch_manager()

    async def test_shutdown_creates_new_instance(self):
        reset_batch_manager()
        mgr1 = await get_batch_manager(persist_fn=AsyncMock())
        await shutdown_batch_manager()
        mgr2 = await get_batch_manager(persist_fn=AsyncMock())
        assert mgr1 is not mgr2
        await shutdown_batch_manager()

    async def test_singleton_is_running(self):
        reset_batch_manager()
        mgr = await get_batch_manager(persist_fn=AsyncMock())
        assert mgr._running is True
        await shutdown_batch_manager()

    async def test_add_is_async_safe(self):
        """Multiple concurrent adds should not corrupt the buffer."""
        reset_batch_manager()
        flushed = []

        async def capture_persist(batch: list[PendingObservation]) -> None:
            flushed.extend(batch)

        mgr = ObservationBatchManager(
            persist_fn=capture_persist,
            batch_size=10,
            flush_interval_seconds=9999.0,
        )
        await mgr.start()

        # Fire 20 concurrent adds
        await asyncio.gather(*[mgr.add(_make_obs()) for _ in range(20)])

        # Give background flush tasks time to complete
        await asyncio.sleep(0.1)

        # All 20 observations should have been flushed (two batches of 10)
        assert len(flushed) == 20
        assert mgr.buffer_size == 0

        await mgr.stop()
