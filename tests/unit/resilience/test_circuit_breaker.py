"""
Unit tests for Circuit Breaker implementation
Tests for PERF-001: Circuit Breaker for External APIs
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpen,
    CircuitState,
    circuit_breaker,
    get_circuit_breaker,
)


class TestCircuitBreakerInitialization:
    """Test circuit breaker initialization"""

    def test_default_initialization(self):
        """Happy path: Circuit breaker initializes with defaults"""
        cb = CircuitBreaker("test")

        assert cb.name == "test"
        assert cb.state == CircuitState.CLOSED
        assert cb.config.failure_threshold == 5
        assert cb.config.recovery_timeout == 60.0

    def test_custom_initialization(self):
        """Happy path: Circuit breaker initializes with custom config"""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            recovery_timeout=30.0,
            half_open_max_calls=2,
            success_threshold=1,
        )
        cb = CircuitBreaker("custom", config)

        assert cb.config.failure_threshold == 3
        assert cb.config.recovery_timeout == 30.0
        assert cb.config.half_open_max_calls == 2
        assert cb.config.success_threshold == 1


class TestCircuitBreakerClosedState:
    """Test circuit breaker in CLOSED state (normal operation)"""

    @pytest.mark.asyncio
    async def test_successful_call_in_closed_state(self):
        """Happy path: Successful calls pass through when closed"""
        cb = CircuitBreaker("test")

        mock_func = AsyncMock(return_value="success")

        result = await cb.call(mock_func, "arg1", kwarg1="value1")

        assert result == "success"
        assert cb.state == CircuitState.CLOSED
        mock_func.assert_called_once_with("arg1", kwarg1="value1")

    @pytest.mark.asyncio
    async def test_failure_count_increments_in_closed_state(self):
        """Happy path: Failure count increments on failure"""
        cb = CircuitBreaker("test")

        mock_func = AsyncMock(side_effect=Exception("Failure"))

        with pytest.raises(Exception, match="Failure"):
            await cb.call(mock_func)

        assert cb.stats.failures == 1
        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_opens_after_threshold_failures(self):
        """Unhappy path: Circuit opens after threshold failures"""
        config = CircuitBreakerConfig(failure_threshold=2)
        cb = CircuitBreaker("test", config)

        mock_func = AsyncMock(side_effect=Exception("Failure"))

        # First failure
        with pytest.raises(Exception):
            await cb.call(mock_func)
        assert cb.state == CircuitState.CLOSED

        # Second failure - should open
        with pytest.raises(Exception):
            await cb.call(mock_func)
        assert cb.state == CircuitState.OPEN


class TestCircuitBreakerOpenState:
    """Test circuit breaker in OPEN state (failing fast)"""

    @pytest.mark.asyncio
    async def test_rejects_calls_when_open(self):
        """Unhappy path: Calls are rejected when circuit is open"""
        config = CircuitBreakerConfig(failure_threshold=1)
        cb = CircuitBreaker("test", config)

        # Force circuit to open
        mock_func = AsyncMock(side_effect=Exception("Failure"))
        with pytest.raises(Exception):
            await cb.call(mock_func)

        assert cb.state == CircuitState.OPEN

        # Next call should be rejected
        mock_func_success = AsyncMock(return_value="success")

        with pytest.raises(CircuitBreakerOpen) as exc_info:
            await cb.call(mock_func_success)

        assert "Circuit 'test' is OPEN" in str(exc_info.value)
        mock_func_success.assert_not_called()

    @pytest.mark.asyncio
    async def test_includes_retry_after_in_error(self):
        """Happy path: Error message includes retry timing"""
        config = CircuitBreakerConfig(failure_threshold=1, recovery_timeout=60)
        cb = CircuitBreaker("test", config)

        # Force circuit to open
        mock_func = AsyncMock(side_effect=Exception("Failure"))
        with pytest.raises(Exception):
            await cb.call(mock_func)

        # Check error message
        with pytest.raises(CircuitBreakerOpen) as exc_info:
            await cb.call(AsyncMock())

        assert "Retry after" in str(exc_info.value)


class TestCircuitBreakerHalfOpenState:
    """Test circuit breaker in HALF_OPEN state (testing recovery)"""

    @pytest.mark.asyncio
    async def test_transitions_to_half_open_after_timeout(self):
        """Happy path: Circuit transitions to half-open after timeout"""
        config = CircuitBreakerConfig(failure_threshold=1, recovery_timeout=0.01)
        cb = CircuitBreaker("test", config)

        # Open the circuit
        mock_func = AsyncMock(side_effect=Exception("Failure"))
        with pytest.raises(Exception):
            await cb.call(mock_func)

        assert cb.state == CircuitState.OPEN

        # Wait for timeout
        await asyncio.sleep(0.02)

        # Next call should transition to half-open
        mock_success = AsyncMock(return_value="success")
        result = await cb.call(mock_success)

        assert cb.state == CircuitState.HALF_OPEN
        assert result == "success"

    @pytest.mark.asyncio
    async def test_success_in_half_open_closes_circuit(self):
        """Happy path: Success in half-open closes the circuit"""
        config = CircuitBreakerConfig(
            failure_threshold=1, recovery_timeout=0.01, success_threshold=1
        )
        cb = CircuitBreaker("test", config)

        # Open the circuit
        with pytest.raises(Exception):
            await cb.call(AsyncMock(side_effect=Exception("Failure")))

        await asyncio.sleep(0.02)

        # Success in half-open should close
        await cb.call(AsyncMock(return_value="success"))

        assert cb.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_failure_in_half_open_reopens_circuit(self):
        """Unhappy path: Failure in half-open reopens the circuit"""
        config = CircuitBreakerConfig(failure_threshold=1, recovery_timeout=0.01)
        cb = CircuitBreaker("test", config)

        # Open the circuit
        with pytest.raises(Exception):
            await cb.call(AsyncMock(side_effect=Exception("Failure")))

        await asyncio.sleep(0.02)

        # Failure in half-open should reopen
        with pytest.raises(Exception):
            await cb.call(AsyncMock(side_effect=Exception("Still failing")))

        assert cb.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_half_open_call_limit(self):
        """Unhappy path: Limited calls allowed in half-open"""
        config = CircuitBreakerConfig(
            failure_threshold=1,
            recovery_timeout=0.01,
            half_open_max_calls=2,
            success_threshold=5,  # High threshold so circuit stays half-open
        )
        cb = CircuitBreaker("test", config)

        # Open the circuit
        with pytest.raises(Exception):
            await cb.call(AsyncMock(side_effect=Exception("Failure")))

        await asyncio.sleep(0.02)

        # Make first call (should transition to half-open and succeed)
        result1 = await cb.call(AsyncMock(return_value="success1"))
        assert result1 == "success1"
        assert cb.state == CircuitState.HALF_OPEN

        # Make second call (should succeed, at limit now)
        result2 = await cb.call(AsyncMock(return_value="success2"))
        assert result2 == "success2"
        assert cb.half_open_calls == 2

        # Third call should be rejected (limit reached)
        with pytest.raises(CircuitBreakerOpen) as exc_info:
            await cb.call(AsyncMock(return_value="success3"))

        assert "HALF_OPEN limit reached" in str(exc_info.value)


class TestCircuitBreakerDecorator:
    """Test circuit breaker decorator"""

    @pytest.mark.asyncio
    async def test_decorator_wraps_function(self):
        """Happy path: Decorator wraps function correctly"""

        @circuit_breaker(name="test_decorator", threshold=2)
        async def test_func(arg):
            return f"result_{arg}"

        result = await test_func("test")
        assert result == "result_test"

    @pytest.mark.asyncio
    async def test_decorator_opens_on_failures(self):
        """Unhappy path: Decorator opens circuit on failures"""
        call_count = 0

        @circuit_breaker(name="test_decorator_fails", threshold=2)
        async def failing_func():
            nonlocal call_count
            call_count += 1
            raise Exception("Failure")

        # First two calls fail
        with pytest.raises(Exception):
            await failing_func()
        with pytest.raises(Exception):
            await failing_func()

        # Third call should be rejected
        with pytest.raises(CircuitBreakerOpen):
            await failing_func()

        # Function should only be called twice
        assert call_count == 2


class TestCircuitBreakerRegistry:
    """Test circuit breaker registry"""

    def test_get_circuit_breaker_creates_new(self):
        """Happy path: Registry creates new circuit breaker"""
        cb1 = get_circuit_breaker("new_circuit_1")
        cb2 = get_circuit_breaker("new_circuit_2")

        assert cb1 is not cb2
        assert cb1.name == "new_circuit_1"
        assert cb2.name == "new_circuit_2"

    def test_get_circuit_breaker_returns_existing(self):
        """Happy path: Registry returns existing circuit breaker"""
        cb1 = get_circuit_breaker("existing_circuit")
        cb2 = get_circuit_breaker("existing_circuit")

        assert cb1 is cb2

    def test_preconfigured_breakers_exist(self):
        """Happy path: Pre-configured breakers exist"""
        from src.core.resilience.circuit_breaker import (
            deepseek_api_breaker,
            google_api_breaker,
            stripe_api_breaker,
        )

        assert google_api_breaker.name == "google_api"
        assert stripe_api_breaker.name == "stripe_api"
        assert deepseek_api_breaker.name == "deepseek_api"


class TestCircuitBreakerConcurrency:
    """Test circuit breaker thread safety"""

    @pytest.mark.asyncio
    async def test_concurrent_calls_handled_safely(self):
        """Happy path: Concurrent calls are handled safely"""
        cb = CircuitBreaker("concurrent")

        call_count = 0

        async def mock_func():
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)
            return f"result_{call_count}"

        # Make concurrent calls
        tasks = [cb.call(mock_func) for _ in range(5)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 5
        assert cb.state == CircuitState.CLOSED


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
