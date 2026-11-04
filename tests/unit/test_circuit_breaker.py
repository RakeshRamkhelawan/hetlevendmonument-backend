"""
Unit tests for Circuit Breaker

Tests:
- State transitions (CLOSED → OPEN → HALF_OPEN → CLOSED)
- Failure threshold handling
- Recovery timeout
- Per-provider isolation
- Metrics tracking
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.resilience.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerRegistry,
    CircuitOpenError,
    CircuitState,
)


class TestCircuitBreakerStates:
    """Tests for circuit breaker state transitions."""

    @pytest.fixture
    def breaker(self):
        return CircuitBreaker(
            provider="test-provider",
            failure_threshold=3,
            recovery_timeout=0.1,  # Short for testing
            half_open_max_calls=2,
        )

    @pytest.mark.asyncio
    async def test_initial_state_is_closed(self, breaker):
        """Test initial state is CLOSED."""
        assert breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_successful_call_stays_closed(self, breaker):
        """Test successful calls keep circuit closed."""

        async def success_func():
            return "success"

        result = await breaker.execute(success_func)

        assert result == "success"
        assert breaker.state == CircuitState.CLOSED
        assert breaker.metrics.successful_calls == 1

    @pytest.mark.asyncio
    async def test_opens_after_failure_threshold(self, breaker):
        """Test circuit opens after failure threshold."""

        async def fail_func():
            raise ValueError("Test error")

        # Fail 3 times (threshold)
        for _ in range(3):
            with pytest.raises(ValueError):
                await breaker.execute(fail_func)

        assert breaker.state == CircuitState.OPEN
        assert breaker.metrics.failed_calls == 3

    @pytest.mark.asyncio
    async def test_rejects_calls_when_open(self, breaker):
        """Test calls are rejected when circuit is OPEN."""

        # Force open state
        async def fail_func():
            raise ValueError("Test error")

        for _ in range(3):
            with pytest.raises(ValueError):
                await breaker.execute(fail_func)

        # Next call should be rejected
        async def any_func():
            return "should not execute"

        with pytest.raises(CircuitOpenError):
            await breaker.execute(any_func)

        assert breaker.metrics.rejected_calls == 1

    @pytest.mark.asyncio
    async def test_transitions_to_half_open_after_timeout(self, breaker):
        """Test transition to HALF_OPEN after recovery timeout."""

        async def fail_func():
            raise ValueError("Test error")

        # Open circuit
        for _ in range(3):
            with pytest.raises(ValueError):
                await breaker.execute(fail_func)

        assert breaker.state == CircuitState.OPEN

        # Wait for recovery timeout
        await asyncio.sleep(0.15)

        # Try call - should transition to HALF_OPEN
        async def success_func():
            return "success"

        result = await breaker.execute(success_func)

        assert result == "success"
        assert breaker.state == CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_closes_after_half_open_success(self, breaker):
        """Test circuit closes after successful calls in HALF_OPEN."""
        # Force HALF_OPEN state
        breaker._state = CircuitState.HALF_OPEN
        breaker._success_count_half_open = 0

        async def success_func():
            return "success"

        # Need 2 successful calls to close
        await breaker.execute(success_func)
        assert breaker.state == CircuitState.HALF_OPEN

        await breaker.execute(success_func)
        assert breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_reopens_on_half_open_failure(self, breaker):
        """Test circuit reopens on failure in HALF_OPEN."""
        # Force HALF_OPEN state
        breaker._state = CircuitState.HALF_OPEN
        breaker._success_count_half_open = 0

        async def fail_func():
            raise ValueError("Test error")

        with pytest.raises(ValueError):
            await breaker.execute(fail_func)

        assert breaker.state == CircuitState.OPEN


class TestCircuitBreakerMetrics:
    """Tests for circuit breaker metrics."""

    @pytest.fixture
    def breaker(self):
        return CircuitBreaker(provider="test", failure_threshold=3)

    @pytest.mark.asyncio
    async def test_metrics_tracked(self, breaker):
        """Test metrics are tracked correctly."""

        async def success_func():
            return "success"

        async def fail_func():
            raise ValueError("error")

        await breaker.execute(success_func)
        await breaker.execute(success_func)

        with pytest.raises(ValueError):
            await breaker.execute(fail_func)

        assert breaker.metrics.total_calls == 3
        assert breaker.metrics.successful_calls == 2
        assert breaker.metrics.failed_calls == 1

    @pytest.mark.asyncio
    async def test_failure_rate_calculation(self, breaker):
        """Test failure rate calculation."""

        async def fail_func():
            raise ValueError("error")

        # 2 failures out of 2 calls = 100% failure rate
        for _ in range(2):
            with pytest.raises(ValueError):
                await breaker.execute(fail_func)

        assert breaker.metrics.failure_rate == 1.0

    @pytest.mark.asyncio
    async def test_state_changes_tracked(self, breaker):
        """Test state changes are tracked."""

        async def fail_func():
            raise ValueError("error")

        initial_changes = breaker.metrics.state_changes

        # Trigger state change
        for _ in range(3):
            with pytest.raises(ValueError):
                await breaker.execute(fail_func)

        assert breaker.metrics.state_changes == initial_changes + 1


class TestCircuitBreakerRegistry:
    """Tests for circuit breaker registry."""

    @pytest.fixture
    def registry(self):
        return CircuitBreakerRegistry()

    @pytest.mark.asyncio
    async def test_get_breaker_creates_new(self, registry):
        """Test getting breaker creates new one."""
        breaker = await registry.get_breaker("gemini")

        assert breaker.provider == "gemini"
        assert breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_get_breaker_returns_existing(self, registry):
        """Test getting breaker returns existing one."""
        breaker1 = await registry.get_breaker("gemini")
        breaker2 = await registry.get_breaker("gemini")

        assert breaker1 is breaker2

    @pytest.mark.asyncio
    async def test_get_all_states(self, registry):
        """Test getting all breaker states."""
        await registry.get_breaker("gemini")
        await registry.get_breaker("openai")

        states = await registry.get_all_states()

        assert "gemini" in states
        assert "openai" in states
        assert states["gemini"]["state"] == "CLOSED"

    @pytest.mark.asyncio
    async def test_reset_all(self, registry):
        """Test resetting all breakers."""
        breaker = await registry.get_breaker("gemini")

        # Force open
        breaker._state = CircuitState.OPEN

        await registry.reset_all()

        assert breaker.state == CircuitState.CLOSED


class TestCircuitOpenError:
    """Tests for CircuitOpenError."""

    def test_error_message(self):
        """Test error message."""
        # Test with custom message
        error = CircuitOpenError("gemini", "Service unavailable")

        assert error.provider == "gemini"
        assert str(error) == "Service unavailable"

    def test_default_error_message(self):
        """Test default error message."""
        # Test without custom message
        error = CircuitOpenError("gemini")

        assert error.provider == "gemini"
        assert "gemini" in str(error)
        assert "OPEN" in str(error)
