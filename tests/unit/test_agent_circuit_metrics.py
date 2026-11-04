"""Tests for AgentCircuitBreaker Prometheus metrics."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from src.core.als.infrastructure.agent_circuit_breaker import AgentCircuitBreaker, CircuitState
from src.core.monitoring.agent_circuit_metrics import _state_to_float

def test_state_to_float() -> None:
    assert _state_to_float(CircuitState.CLOSED) == 0.0
    assert _state_to_float(CircuitState.OPEN) == 1.0
    assert _state_to_float(CircuitState.HALF_OPEN) == 2.0

@pytest.mark.asyncio
async def test_record_success_updates_metrics() -> None:
    pool = MagicMock()
    client = AsyncMock()
    client.hgetall = AsyncMock(return_value={})
    client.hset = AsyncMock()
    client.hincrby = AsyncMock(return_value=1)
    pool.get_client = AsyncMock(return_value=client)
    cb = AgentCircuitBreaker(pool, 1, "a1")
    cb._init_metrics()
    state = await cb.record_success()
    assert state == CircuitState.CLOSED

@pytest.mark.asyncio
async def test_record_failure_updates_metrics() -> None:
    pool = MagicMock()
    client = AsyncMock()
    client.hgetall = AsyncMock(return_value={})
    client.hset = AsyncMock()
    client.hincrby = AsyncMock(return_value=1)
    pool.get_client = AsyncMock(return_value=client)
    cb = AgentCircuitBreaker(pool, 1, "a1")
    cb._init_metrics()
    state = await cb.record_failure()
    assert state == CircuitState.CLOSED
