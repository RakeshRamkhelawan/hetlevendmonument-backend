"""Unit tests for src.core.database.retry_logic."""

import time
from unittest.mock import MagicMock, patch

import pytest

from src.core.database.retry_logic import (
    RetryConfig,
    calculate_delay,
    with_retry,
    ConnectionRetryManager,
    DATABASE_RETRY_CONFIG,
    retry_manager,
)


def test_retry_config_defaults():
    """Validates default values of RetryConfig."""
    cfg = RetryConfig()
    assert cfg.max_retries == 3
    assert cfg.base_delay == 1.0
    assert cfg.max_delay == 30.0
    assert cfg.exponential_base == 2.0
    assert cfg.jitter is True
    assert ConnectionError in cfg.retryable_exceptions
    assert TimeoutError in cfg.retryable_exceptions
    assert OSError in cfg.retryable_exceptions


def test_calculate_delay_exponential_growth():
    """Validates exponential backoff calculation without jitter."""
    cfg = RetryConfig(base_delay=1.0, exponential_base=2.0, max_delay=10.0, jitter=False)
    assert calculate_delay(0, cfg) == 1.0
    assert calculate_delay(1, cfg) == 2.0
    assert calculate_delay(2, cfg) == 4.0
    assert calculate_delay(3, cfg) == 8.0
    assert calculate_delay(4, cfg) == 10.0  # Capped at max_delay


def test_calculate_delay_with_jitter():
    """Validates jitter bounds: delay * (0.5 to 1.5)."""
    cfg = RetryConfig(base_delay=2.0, exponential_base=2.0, jitter=True)
    for _ in range(20):
        delay = calculate_delay(0, cfg)
        assert 1.0 <= delay <= 3.0


@pytest.mark.asyncio
async def test_with_retry_async_succeeds_first_attempt():
    """Async function that succeeds immediately returns result without retries."""
    calls = 0

    @with_retry()
    async def successful_func():
        nonlocal calls
        calls += 1
        return "success"

    result = await successful_func()
    assert result == "success"
    assert calls == 1


@pytest.mark.asyncio
async def test_with_retry_async_recovers_after_failures():
    """Async function recovers after transient failures."""
    calls = 0
    on_retry_mock = MagicMock()

    cfg = RetryConfig(max_retries=3, base_delay=0.01)

    @with_retry(config=cfg, on_retry=on_retry_mock)
    async def flaky_func():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise ConnectionError(f"Fail {calls}")
        return "recovered"

    with patch("asyncio.sleep") as mock_sleep:
        result = await flaky_func()

    assert result == "recovered"
    assert calls == 3
    assert on_retry_mock.call_count == 2
    assert mock_sleep.call_count == 2


@pytest.mark.asyncio
async def test_with_retry_async_exhausts_retries():
    """Async function raises last exception after exceeding max_retries."""
    calls = 0
    cfg = RetryConfig(max_retries=2, base_delay=0.01)

    @with_retry(config=cfg)
    async def always_failing():
        nonlocal calls
        calls += 1
        raise TimeoutError("Still down")

    with patch("asyncio.sleep"):
        with pytest.raises(TimeoutError, match="Still down"):
            await always_failing()

    assert calls == 3  # 1 initial + 2 retries


@pytest.mark.asyncio
async def test_with_retry_async_non_retryable_exception():
    """Non-retryable exceptions are raised immediately without retry."""
    calls = 0

    @with_retry()
    async def bad_logic():
        nonlocal calls
        calls += 1
        raise KeyError("Invalid key")

    with pytest.raises(KeyError, match="Invalid key"):
        await bad_logic()

    assert calls == 1


def test_with_retry_sync_success_and_retry():
    """Synchronous function retry with on_retry callback."""
    calls = 0
    on_retry_mock = MagicMock()
    cfg = RetryConfig(max_retries=2, base_delay=0.01)

    @with_retry(config=cfg, on_retry=on_retry_mock)
    def sync_flaky():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("Socket error")
        return 42

    with patch("time.sleep"):
        result = sync_flaky()

    assert result == 42
    assert calls == 2
    assert on_retry_mock.call_count == 1


def test_with_retry_sync_exhausted():
    """Synchronous function exhausts retries and raises error."""
    calls = 0
    cfg = RetryConfig(max_retries=1, base_delay=0.01)

    @with_retry(config=cfg)
    def sync_fail():
        nonlocal calls
        calls += 1
        raise ConnectionError("Permanently broken")

    with patch("time.sleep"):
        with pytest.raises(ConnectionError, match="Permanently broken"):
            sync_fail()

    assert calls == 2


@pytest.mark.asyncio
async def test_connection_retry_manager_success():
    """ConnectionRetryManager executes async callable successfully."""
    manager = ConnectionRetryManager()

    async def add(a, b):
        return a + b

    res = await manager.execute_with_retry(add, 10, 20)
    assert res == 30
    assert manager.consecutive_failures == 0


@pytest.mark.asyncio
async def test_connection_retry_manager_circuit_breaker():
    """Circuit breaker opens when consecutive failures reach threshold."""
    cfg = RetryConfig(max_retries=1, base_delay=0.01)
    manager = ConnectionRetryManager(config=cfg)

    async def fail():
        raise ConnectionError("Network unreachable")

    with patch("asyncio.sleep"):
        # First round: 2 failures (consecutive_failures = 2 == max_retries * 2)
        with pytest.raises(ConnectionError, match="Network unreachable"):
            await manager.execute_with_retry(fail)

    assert manager.consecutive_failures == 2
    assert manager.circuit_open is True
    assert manager.circuit_open_until is not None

    # Next call should be blocked immediately by circuit breaker
    with pytest.raises(ConnectionError, match="Circuit breaker is open"):
        await manager.execute_with_retry(fail)

    # Reset circuit breaker
    manager.reset_circuit_breaker()
    assert manager.circuit_open is False
    assert manager.consecutive_failures == 0


def test_global_instances():
    """Validates global DATABASE_RETRY_CONFIG and retry_manager."""
    assert DATABASE_RETRY_CONFIG.max_retries == 5
    assert isinstance(retry_manager, ConnectionRetryManager)
