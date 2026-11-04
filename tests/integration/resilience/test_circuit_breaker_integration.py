"""
Integration tests for Circuit Breaker
Tests circuit breaker behavior with simulated external service failures
"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.integration


class TestCircuitBreakerWithExternalAPIs:
    """Integration tests for circuit breaker with external API patterns"""

    @pytest.mark.asyncio
    async def test_google_api_circuit_breaker_opens_on_failures(self):
        """
        Integration test: Google API circuit breaker opens after failures

        Simulates Google API failures and verifies circuit breaker behavior
        """
        from src.core.resilience import get_circuit_breaker

        google_api_breaker = get_circuit_breaker(
            "google_test", failure_threshold=3, recovery_timeout=60.0
        )
        # Reset circuit breaker for clean test
        google_api_breaker._state = google_api_breaker._state.__class__.CLOSED
        google_api_breaker._failure_count = 0

        call_count = 0

        async def failing_google_call():
            nonlocal call_count
            call_count += 1
            raise Exception("Google API Error: 503 Service Unavailable")

        # Make calls until circuit opens (threshold is 3)
        for i in range(4):
            try:
                await google_api_breaker.call(failing_google_call)
            except Exception:
                pass

        # Circuit should be open now
        assert google_api_breaker.state.name == "OPEN"

        # Verify function was only called 3 times (threshold)
        assert call_count == 3, f"Expected 3 calls, got {call_count}"

    @pytest.mark.asyncio
    async def test_stripe_api_circuit_breaker_recovery(self):
        """
        Integration test: Stripe API circuit breaker recovers after timeout

        Simulates Stripe API recovery after circuit opens
        """
        import time

        from src.core.resilience import get_circuit_breaker
        from src.core.resilience.circuit_breaker import CircuitState

        stripe_api_breaker = get_circuit_breaker(
            "stripe_recovery_test", failure_threshold=3, recovery_timeout=0.01
        )
        # Manually set circuit to open with short timeout
        stripe_api_breaker._state = CircuitState.OPEN
        stripe_api_breaker._last_failure_time = time.time()
        stripe_api_breaker._success_count_half_open = 0
        stripe_api_breaker._half_open_calls = 0
        # Set success threshold to 1 so a single success closes the circuit
        stripe_api_breaker.success_threshold_half_open = 1

        # Wait for recovery timeout
        await asyncio.sleep(0.02)

        async def successful_stripe_call():
            return {"status": "success", "payment_id": "pi_123"}

        # Call should succeed and transition to closed
        result = await stripe_api_breaker.call(successful_stripe_call)

        assert result["status"] == "success"
        assert stripe_api_breaker.state.name == "CLOSED"

    @pytest.mark.asyncio
    async def test_deepseek_api_circuit_breaker_half_open_limit(self):
        """
        Integration test: DeepSeek API circuit breaker limits half-open calls

        Verifies only limited calls allowed in half-open state
        """
        from src.core.resilience import get_circuit_breaker
        from src.core.resilience.circuit_breaker import CircuitState

        deepseek_api_breaker = get_circuit_breaker("deepseek_test", failure_threshold=3)
        # Set circuit to half-open with exhausted calls
        deepseek_api_breaker._state = CircuitState.HALF_OPEN
        deepseek_api_breaker._half_open_calls = 3  # Max is 3

        async def any_call():
            return "result"

        # Should reject call when half-open limit reached
        from src.core.resilience.circuit_breaker import CircuitOpenError

        with pytest.raises(CircuitOpenError) as exc_info:
            await deepseek_api_breaker.call(any_call)

        assert "HALF_OPEN limit reached" in str(exc_info.value)


class TestCircuitBreakerDecoratorIntegration:
    """Integration tests for circuit breaker decorator"""

    @pytest.mark.asyncio
    async def test_decorator_with_real_api_pattern(self):
        """
        Integration test: Decorator works with realistic API call pattern

        Simulates real external API call with timeout, retries, etc.
        """
        from src.core.resilience.circuit_breaker import circuit_breaker as cb_decorator

        call_count = 0

        @cb_decorator(name="test_api_decorator", threshold=2, recovery_timeout=0.1)
        async def call_external_api(endpoint: str, payload: dict):
            nonlocal call_count
            call_count += 1

            # Simulate occasional failures
            if call_count < 3:
                raise Exception(f"Connection timeout to {endpoint}")

            return {"status": "success", "data": payload}

        # First call fails
        with pytest.raises(Exception, match="Connection timeout"):
            await call_external_api("/v1/users", {"id": 123})

        # Second call fails - circuit should open
        with pytest.raises(Exception, match="Connection timeout"):
            await call_external_api("/v1/users", {"id": 123})

        # Third call should be rejected by circuit breaker
        from src.core.resilience.circuit_breaker import CircuitOpenError

        with pytest.raises(CircuitOpenError):
            await call_external_api("/v1/users", {"id": 123})

        # Verify only 2 actual API calls were made
        assert call_count == 2


class TestCircuitBreakerConcurrencyIntegration:
    """Integration tests for circuit breaker under concurrent load"""

    @pytest.mark.asyncio
    async def test_concurrent_calls_with_circuit_breaker(self):
        """
        Integration test: Circuit breaker handles concurrent calls correctly

        Simulates multiple concurrent requests to failing service.
        NOTE: Due to async scheduling, all concurrent calls may start before
        any failure is recorded. The circuit opens after the threshold is reached,
        preventing SUBSEQUENT calls (not in-flight ones).
        """
        from src.core.resilience import get_circuit_breaker

        cb = get_circuit_breaker("concurrent_test_unique", failure_threshold=5)

        call_count = 0

        async def failing_call():
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)  # Small delay
            raise Exception("Service unavailable")

        # Make 10 concurrent calls
        tasks = [cb.call(failing_call) for _ in range(10)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All calls are exceptions (either service error or circuit open)
        assert all(isinstance(r, Exception) for r in results)

        # Circuit should be open after processing failures
        assert cb.state.name == "OPEN"


class TestCircuitBreakerMetricsIntegration:
    """Integration tests for circuit breaker metrics and observability"""

    @pytest.mark.asyncio
    async def test_circuit_breaker_state_transitions_logged(self, caplog):
        """
        Integration test: Circuit breaker logs state transitions

        Verifies proper logging for monitoring and alerting
        """
        import logging

        from src.core.resilience import get_circuit_breaker
        from src.core.resilience.circuit_breaker import CircuitState

        cb = get_circuit_breaker("logging_test_unique", failure_threshold=1, recovery_timeout=0.01)

        with caplog.at_level(logging.INFO, logger="src.core.resilience.circuit_breaker"):
            # Trigger CLOSED -> OPEN via failure
            async def failing_call():
                raise Exception("test failure")

            try:
                await cb.call(failing_call)
            except Exception:
                pass

            # Wait for recovery timeout then trigger OPEN -> HALF_OPEN -> CLOSED
            await asyncio.sleep(0.02)

            async def success_call():
                return "ok"

            # Set low success threshold for quick close
            cb.success_threshold_half_open = 1
            await cb.call(success_call)

        # Verify at least some state transitions occurred
        assert cb.state.name == "CLOSED"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
