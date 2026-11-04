"""Tests for AgentRunner + CircuitBreaker integration."""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from src.core.agent_runner import AgentRunner
from src.core.als.infrastructure.signal_bus import Signal, SignalTier
from src.core.als.infrastructure.agent_circuit_breaker import CircuitState

@pytest.fixture
def mock_db_factory():
    session = AsyncMock()
    session.close = AsyncMock()
    return AsyncMock(return_value=session)

@pytest.fixture
def mock_signal_bus():
    bus = MagicMock()
    bus.wait_for_signal = AsyncMock(side_effect=asyncio.TimeoutError)
    return bus

@pytest.fixture
def mock_redis_pool():
    pool = MagicMock()
    client = AsyncMock()
    client.hgetall = AsyncMock(return_value={})
    client.hset = AsyncMock()
    client.hincrby = AsyncMock(return_value=1)
    pool.get_client = AsyncMock(return_value=client)
    return pool, client

@pytest.mark.asyncio
async def test_circuit_breaker_created_when_redis_present(mock_db_factory, mock_signal_bus, mock_redis_pool) -> None:
    pool, client = mock_redis_pool
    cfg = MagicMock()
    cfg.tenant_id = 1
    cfg.agent_id = "a1"
    cfg.subscribed_topics = ["test"]
    runner = AgentRunner(mock_db_factory, mock_signal_bus, redis_pool=pool)
    cb = runner._get_circuit_breaker(cfg)
    assert cb is not None
    assert cb.tenant_id == 1
    assert cb.agent_id == "a1"

@pytest.mark.asyncio
async def test_circuit_open_blocks_execution(mock_db_factory, mock_signal_bus, mock_redis_pool) -> None:
    pool, client = mock_redis_pool
    import time
    client.hgetall.return_value = {b"state": b"open", b"last_failure_time": str(int(time.time()) + 1000).encode()}
    signal = Signal(tenant_id=1, source_agent_id="test", target_agent_ids=[], tier=SignalTier.COGNITIVE, topic="test", payload={})
    cfg = MagicMock()
    cfg.tenant_id = 1
    cfg.agent_id = "a1"
    cfg.subscribed_topics = ["test"]
    agent = AsyncMock()
    async def factory(c):
        return agent
    runner = AgentRunner(mock_db_factory, mock_signal_bus, agent_factory=factory, redis_pool=pool)
    call_count = 0
    async def ws(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return signal
        runner._stop_event.set()
        raise asyncio.TimeoutError
    mock_signal_bus.wait_for_signal = ws
    await runner._run_agent_loop(cfg)
    agent.execute_ooda.assert_not_awaited()

@pytest.mark.asyncio
async def test_success_closes_circuit(mock_db_factory, mock_signal_bus, mock_redis_pool) -> None:
    pool, client = mock_redis_pool
    client.hgetall.return_value = {b"state": b"closed"}
    signal = Signal(tenant_id=1, source_agent_id="test", target_agent_ids=[], tier=SignalTier.COGNITIVE, topic="test", payload={})
    cfg = MagicMock()
    cfg.tenant_id = 1
    cfg.agent_id = "a1"
    cfg.subscribed_topics = ["test"]
    agent = AsyncMock()
    async def factory(c):
        return agent
    runner = AgentRunner(mock_db_factory, mock_signal_bus, agent_factory=factory, redis_pool=pool)
    call_count = 0
    async def ws(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return signal
        runner._stop_event.set()
        raise asyncio.TimeoutError
    mock_signal_bus.wait_for_signal = ws
    await runner._run_agent_loop(cfg)
    agent.execute_ooda.assert_awaited_once()
