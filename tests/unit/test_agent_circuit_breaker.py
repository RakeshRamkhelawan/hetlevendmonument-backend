"""Tests for AgentCircuitBreaker."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.core.als.infrastructure.agent_circuit_breaker import AgentCircuitBreaker, CircuitState

@pytest.fixture
def mock_pool():
    pool = MagicMock()
    client = AsyncMock()
    pool.get_client = AsyncMock(return_value=client)
    return pool, client

@pytest.fixture
def cb(mock_pool):
    pool, _ = mock_pool
    return AgentCircuitBreaker(pool, tenant_id=1, agent_id="a1", failure_threshold=3, reset_timeout_seconds=10)

@pytest.mark.asyncio
async def test_initial_state_closed(cb: AgentCircuitBreaker, mock_pool) -> None:
    pool, client = mock_pool
    client.hgetall.return_value = {}
    state = await cb.get_state()
    assert state == CircuitState.CLOSED

@pytest.mark.asyncio
async def test_allow_when_closed(cb: AgentCircuitBreaker, mock_pool) -> None:
    pool, client = mock_pool
    client.hgetall.return_value = {}
    assert await cb.allow() is True

@pytest.mark.asyncio
async def test_record_failure_increments(cb: AgentCircuitBreaker, mock_pool) -> None:
    pool, client = mock_pool
    client.hgetall.return_value = {b"state": b"closed", b"failure_count": b"0"}
    client.hincrby.return_value = 1
    state = await cb.record_failure()
    assert state == CircuitState.CLOSED
    client.hincrby.assert_called_once()

@pytest.mark.asyncio
async def test_opens_after_threshold(cb: AgentCircuitBreaker, mock_pool) -> None:
    pool, client = mock_pool
    client.hgetall.return_value = {b"state": b"closed", b"failure_count": b"2"}
    client.hincrby.return_value = 3
    state = await cb.record_failure()
    assert state == CircuitState.OPEN

@pytest.mark.asyncio
async def test_half_open_allows(cb: AgentCircuitBreaker, mock_pool) -> None:
    pool, client = mock_pool
    client.hgetall.return_value = {b"state": b"half_open"}
    assert await cb.allow() is True

@pytest.mark.asyncio
async def test_record_success_in_half_open(cb: AgentCircuitBreaker, mock_pool) -> None:
    pool, client = mock_pool
    client.hgetall.return_value = {b"state": b"half_open"}
    client.hincrby.return_value = 2
    state = await cb.record_success()
    assert state == CircuitState.CLOSED

@pytest.mark.asyncio
async def test_open_blocks_and_respects_timeout(cb: AgentCircuitBreaker, mock_pool) -> None:
    pool, client = mock_pool
    import time
    client.hgetall.return_value = {b"state": b"open", b"last_failure_time": str(int(time.time()) + 1000).encode()}
    assert await cb.allow() is False

@pytest.mark.asyncio
async def test_open_allows_after_timeout(cb: AgentCircuitBreaker, mock_pool) -> None:
    pool, client = mock_pool
    import time
    client.hgetall.return_value = {b"state": b"open", b"last_failure_time": str(int(time.time()) - 20).encode()}
    assert await cb.allow() is True
    client.hset.assert_any_call(cb._key, "state", CircuitState.HALF_OPEN.value)

@pytest.mark.asyncio
async def test_reset(cb: AgentCircuitBreaker, mock_pool) -> None:
    pool, client = mock_pool
    await cb.reset()
    client.hset.assert_called()

def test_invalid_threshold() -> None:
    pool = MagicMock()
    with pytest.raises(ValueError):
        AgentCircuitBreaker(pool, 1, "a1", failure_threshold=0)
