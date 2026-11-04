import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.als.infrastructure.signal_bus import Signal, SignalBus, SignalTier


@pytest.mark.asyncio
async def test_signal_loop_detection():
    # Setup mock pool manager
    mock_pool = MagicMock()
    mock_client = AsyncMock()
    # Correct async mock: get_client is an async function
    mock_pool.get_client = AsyncMock(return_value=mock_client)

    bus = SignalBus(mock_pool)
    # Mock block check to avoid further Redis calls
    bus.is_tenant_blocked = AsyncMock(return_value=False)

    # Create signal with high hop count
    signal = Signal(
        tenant_id=1,
        source_agent_id="test_agent",
        target_agent_ids=[],
        tier=SignalTier.REFLEX,
        payload={"msg": "hello"},
        hop_count=10,  # Already at limit
    )

    # Emit should drop the signal
    await bus.emit(signal)

    # Verify client.publish was NEVER called
    assert mock_client.publish.call_count == 0


@pytest.mark.asyncio
async def test_global_observer_hook():
    mock_pool = MagicMock()
    mock_client = AsyncMock()
    mock_pool.get_client = AsyncMock(return_value=mock_client)

    bus = SignalBus(mock_pool)
    bus.is_tenant_blocked = AsyncMock(return_value=False)
    bus._log_signal = AsyncMock()

    # Global observer callback
    observer_called = asyncio.Event()

    async def my_observer(signal):
        observer_called.set()

    bus.add_global_observer(SignalTier.COGNITIVE, my_observer)

    signal = Signal(
        tenant_id=1,
        source_agent_id="test",
        target_agent_ids=[],
        tier=SignalTier.COGNITIVE,
        payload={},
    )

    await bus.emit(signal)

    # Wait for observer to be triggered (it runs in create_task)
    await asyncio.wait_for(observer_called.wait(), timeout=1.0)
    assert observer_called.is_set()
