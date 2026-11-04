"""Tests for SignalBus topic-aware emit and wait."""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from src.core.als.infrastructure.signal_bus import Signal, SignalBus, SignalTier

@pytest.fixture
def mock_pool():
    pool = MagicMock()
    client = AsyncMock()
    client.exists.return_value = 0
    pool.get_client = AsyncMock(return_value=client)
    return pool, client

@pytest.mark.asyncio
async def test_emit_publishes_to_topic_channel(mock_pool) -> None:
    pool, client = mock_pool
    bus = SignalBus(pool)
    sig = Signal(tenant_id=1, source_agent_id="test", target_agent_ids=[], tier=SignalTier.COGNITIVE, topic="user.created", payload={"x": 1})
    await bus.emit(sig)
    calls = [c.args for c in client.publish.call_args_list]
    assert any("organism:1:cognitive" in str(c) for c in calls)
    assert any("organism:1:user.created" in str(c) for c in calls)

@pytest.mark.asyncio
async def test_wait_for_signal_returns_none_on_timeout(mock_pool) -> None:
    pool, client = mock_pool
    pubsub = AsyncMock()
    client.pubsub = MagicMock(return_value=pubsub)
    bus = SignalBus(pool)
    pubsub.get_message = AsyncMock(return_value=None)
    result = await bus.wait_for_signal(topics=["user.created"], tenant_id=1, timeout=0.1)
    assert result is None
