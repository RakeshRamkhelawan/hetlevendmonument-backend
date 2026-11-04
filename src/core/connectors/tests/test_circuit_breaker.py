"""
Tests voor Circuit Breaker

Happy paths:
- Requests doorlaten in closed state
- Successes resetten failure count
- Na timeout: half_open test
- Na successes: terug naar closed

Unhappy paths:
- Failures openen circuit
- Requests blokkeren in open state
- Half_open failure -> direct open
- Timeout niet verstreken -> nog steeds open
"""

import asyncio
from datetime import datetime

import pytest

from src.core.connectors.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerRegistry,
    CircuitState,
)


class TestCircuitBreakerStates:
    """Test circuit breaker state transitions."""

    @pytest.fixture
    def breaker(self):
        return CircuitBreaker(
            name="test_breaker",
            config=CircuitBreakerConfig(
                failure_threshold=3,
                success_threshold=2,
                timeout_duration_seconds=1,
            ),
        )

    def test_initial_state_closed(self, breaker):
        """Happy path: Initiele state is CLOSED."""
        assert breaker.state == CircuitState.CLOSED
        assert breaker.can_execute() is True

    def test_record_success_in_closed(self, breaker):
        """Happy path: Success in closed state."""
        breaker.record_success()
        assert breaker.state == CircuitState.CLOSED

    def test_record_failures_open_circuit(self, breaker):
        """Unhappy path: Failures openen circuit."""
        # Record failures
        for _ in range(3):
            breaker.record_failure("Test error")

        assert breaker.state == CircuitState.OPEN
        assert breaker.can_execute() is False

    @pytest.mark.asyncio
    async def test_half_open_after_timeout(self, breaker):
        """Happy path: Na timeout -> half_open."""
        # Open circuit
        for _ in range(3):
            breaker.record_failure("Test error")

        assert breaker.state == CircuitState.OPEN

        # Wait for timeout
        await asyncio.sleep(1.1)

        # Should be able to execute (half_open)
        assert breaker.can_execute() is True
        assert breaker.state == CircuitState.HALF_OPEN

    @pytest.mark.asyncio
    async def test_success_in_half_open_closes(self, breaker):
        """Happy path: Success in half_open -> closed."""
        # Open circuit
        for _ in range(3):
            breaker.record_failure("Test error")

        await asyncio.sleep(1.1)
        assert breaker.can_execute() is True  # half_open

        # Record successes
        breaker.record_success()
        breaker.record_success()

        assert breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_failure_in_half_open_reopens(self, breaker):
        """Unhappy path: Failure in half_open -> direct open."""
        # Open circuit
        for _ in range(3):
            breaker.record_failure("Test error")

        await asyncio.sleep(1.1)
        assert breaker.can_execute() is True

        # One failure should reopen
        breaker.record_failure("Still broken")

        assert breaker.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_open_blocks_requests(self, breaker):
        """Unhappy path: Open circuit blokkeert requests."""
        # Open circuit
        for _ in range(3):
            breaker.record_failure("Test error")

        assert breaker.state == CircuitState.OPEN
        assert breaker.can_execute() is False

        # Meerdere checks moeten allemaal False zijn
        for _ in range(5):
            assert breaker.can_execute() is False
            await asyncio.sleep(0.1)

    def test_stats_in_open_state(self, breaker):
        """Happy path: Stats in open state."""
        for _ in range(3):
            breaker.record_failure("Error")

        stats = breaker.get_stats()

        assert stats["name"] == "test_breaker"
        assert stats["state"] == "open"
        assert stats["failure_count"] == 3


class TestCircuitBreakerCallbacks:
    """Test circuit breaker callbacks."""

    @pytest.mark.asyncio
    async def test_on_open_callback(self):
        """Happy path: on_open callback wordt aangeroepen."""
        callback_called = False

        def on_open(name: str) -> None:
            nonlocal callback_called
            callback_called = True

        config = CircuitBreakerConfig(
            failure_threshold=2,
            on_open=on_open,
        )
        breaker = CircuitBreaker("test", config)

        # Trigger open
        breaker.record_failure("Error 1")
        breaker.record_failure("Error 2")

        assert callback_called is True

    @pytest.mark.asyncio
    async def test_on_close_callback(self):
        """Happy path: on_close callback wordt aangeroepen."""
        callback_called = False

        def on_close(name: str) -> None:
            nonlocal callback_called
            callback_called = True

        config = CircuitBreakerConfig(
            failure_threshold=2,
            success_threshold=1,
            timeout_duration_seconds=1,
            on_close=on_close,
        )
        breaker = CircuitBreaker("test", config)

        # Open circuit
        breaker.record_failure("Error 1")
        breaker.record_failure("Error 2")

        # Wait and close
        await asyncio.sleep(1.1)
        breaker.can_execute()  # Transition to half_open
        breaker.record_success()

        assert callback_called is True


class TestCircuitBreakerTimeWindow:
    """Test failure time window."""

    @pytest.mark.asyncio
    async def test_failures_outside_window_ignored(self):
        """Happy path: Oude failures worden genegeerd."""
        config = CircuitBreakerConfig(
            failure_threshold=3,
            failure_window_seconds=1,
        )
        breaker = CircuitBreaker("test", config)

        # Record 2 failures
        breaker.record_failure("Error 1")
        breaker.record_failure("Error 2")

        # Wait for window te verstrijken
        await asyncio.sleep(1.1)

        # Record 1 more failure (oude zijn nu verlopen)
        breaker.record_failure("Error 3")

        # Should still be closed (only 1 failure in current window)
        assert breaker.state == CircuitState.CLOSED


class TestCircuitBreakerRegistry:
    """Test circuit breaker registry."""

    def test_get_or_create(self):
        """Happy path: Get or create breaker."""
        registry = CircuitBreakerRegistry()

        breaker1 = registry.get_or_create("breaker1")
        breaker2 = registry.get_or_create("breaker1")  # Same name
        breaker3 = registry.get_or_create("breaker2")  # Different name

        assert breaker1 is breaker2  # Same instance
        assert breaker1 is not breaker3  # Different instance

    def test_get_existing(self):
        """Happy path: Get bestaande breaker."""
        registry = CircuitBreakerRegistry()

        registry.get_or_create("test")
        breaker = registry.get("test")

        assert breaker is not None
        assert breaker.name == "test"

    def test_get_nonexistent(self):
        """Happy path: Get non-existent breaker."""
        registry = CircuitBreakerRegistry()

        breaker = registry.get("nonexistent")

        assert breaker is None

    def test_remove(self):
        """Happy path: Remove breaker."""
        registry = CircuitBreakerRegistry()

        registry.get_or_create("test")
        registry.remove("test")

        assert registry.get("test") is None

    def test_get_all_stats(self):
        """Happy path: Get stats van alle breakers."""
        registry = CircuitBreakerRegistry()

        registry.get_or_create("breaker1")
        registry.get_or_create("breaker2")

        stats = registry.get_all_stats()

        assert "breaker1" in stats
        assert "breaker2" in stats
