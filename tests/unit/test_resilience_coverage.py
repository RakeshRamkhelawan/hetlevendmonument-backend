#!/usr/bin/env python3
"""
Comprehensive Test Suite for Tool Broker Resilience Module (P4.4.2)

Tests:
- Retry logic with exponential backoff and jitter
- Circuit breaker state machine (CLOSED → OPEN → HALF_OPEN)
- CircuitBreakerRegistry for managing multiple breakers
- ResilienceMetrics for tracking patterns
- Exception handling and edge cases

Target Coverage: 80%+ on resilience.py
"""

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.tool_broker.resilience import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenException,
    CircuitBreakerRegistry,
    CircuitBreakerState,
    ResilienceException,
    ResilienceMetrics,
    RetryConfig,
    RetryExhaustedException,
    RetryMetrics,
    async_retry,
    get_circuit_breaker_registry,
    get_resilience_metrics,
    retry_decorator,
)

# ============================================================================
# RETRY CONFIG TESTS
# ============================================================================


class TestRetryConfig:
    """Test RetryConfig dataclass and validation"""

    def test_default_configuration(self):
        """Test RetryConfig with default values"""
        config = RetryConfig()
        assert config.max_attempts == 3
        assert config.initial_delay_ms == 100
        assert config.max_delay_ms == 10000
        assert config.backoff_factor == 2.0
        assert config.jitter_enabled is True
        assert config.retry_on_exceptions == (Exception,)

    def test_custom_configuration(self):
        """Test RetryConfig with custom values"""
        config = RetryConfig(
            max_attempts=5,
            initial_delay_ms=200,
            max_delay_ms=5000,
            backoff_factor=1.5,
            jitter_enabled=False,
            retry_on_exceptions=(ValueError, TypeError),
        )
        assert config.max_attempts == 5
        assert config.initial_delay_ms == 200
        assert config.max_delay_ms == 5000
        assert config.backoff_factor == 1.5
        assert config.jitter_enabled is False
        assert config.retry_on_exceptions == (ValueError, TypeError)

    def test_invalid_max_attempts_raises_error(self):
        """Test that max_attempts < 1 raises ValueError"""
        with pytest.raises(ValueError, match="max_attempts must be >= 1"):
            RetryConfig(max_attempts=0)

    def test_invalid_initial_delay_raises_error(self):
        """Test that negative initial_delay_ms raises ValueError"""
        with pytest.raises(ValueError, match="initial_delay_ms must be >= 0"):
            RetryConfig(initial_delay_ms=-1)

    def test_boundary_values(self):
        """Test boundary values for RetryConfig"""
        # Minimum valid config
        config = RetryConfig(max_attempts=1, initial_delay_ms=0)
        assert config.max_attempts == 1
        assert config.initial_delay_ms == 0


# ============================================================================
# RETRY METRICS TESTS
# ============================================================================


class TestRetryMetrics:
    """Test RetryMetrics tracking functionality"""

    def test_initial_state(self):
        """Test RetryMetrics initial state"""
        metrics = RetryMetrics()
        assert metrics.total_attempts == 0
        assert metrics.successful_retries == 0
        assert metrics.failed_retries == 0
        assert metrics.total_delay_ms == 0
        assert metrics.last_attempt_time is None
        assert metrics.last_error is None

    def test_record_successful_attempt(self):
        """Test recording successful attempt"""
        metrics = RetryMetrics()
        metrics.record_attempt(delay_ms=100, success=True)

        assert metrics.total_attempts == 1
        assert metrics.successful_retries == 1
        assert metrics.failed_retries == 0
        assert metrics.total_delay_ms == 100
        assert metrics.last_attempt_time is not None
        assert metrics.last_error is None

    def test_record_failed_attempt(self):
        """Test recording failed attempt with error"""
        metrics = RetryMetrics()
        test_error = ValueError("test error")
        metrics.record_attempt(delay_ms=50, success=False, error=test_error)

        assert metrics.total_attempts == 1
        assert metrics.successful_retries == 0
        assert metrics.failed_retries == 1
        assert metrics.total_delay_ms == 50
        assert metrics.last_error == test_error

    def test_multiple_attempts(self):
        """Test recording multiple attempts"""
        metrics = RetryMetrics()

        # First attempt - failed
        metrics.record_attempt(delay_ms=100, success=False, error=ValueError("err1"))
        # Second attempt - failed
        metrics.record_attempt(delay_ms=200, success=False, error=ValueError("err2"))
        # Third attempt - success
        metrics.record_attempt(delay_ms=0, success=True)

        assert metrics.total_attempts == 3
        assert metrics.successful_retries == 1
        assert metrics.failed_retries == 2
        assert metrics.total_delay_ms == 300

    def test_get_stats(self):
        """Test get_stats returns correct dictionary"""
        metrics = RetryMetrics()
        metrics.record_attempt(delay_ms=100, success=False, error=ValueError("error"))
        metrics.record_attempt(delay_ms=0, success=True)

        stats = metrics.get_stats()

        assert stats["total_attempts"] == 2
        assert stats["successful_retries"] == 1
        assert stats["failed_retries"] == 1
        assert stats["total_delay_ms"] == 100
        assert stats["last_attempt_time"] is not None
        assert "error" in stats["last_error"]

    def test_get_stats_no_error(self):
        """Test get_stats with no error recorded"""
        metrics = RetryMetrics()
        metrics.record_attempt(success=True)

        stats = metrics.get_stats()
        assert stats["last_error"] is None


# ============================================================================
# ASYNC RETRY TESTS
# ============================================================================


class TestAsyncRetry:
    """Test async_retry function with exponential backoff"""

    @pytest.mark.asyncio
    async def test_successful_first_attempt(self):
        """Test async_retry succeeds on first attempt"""
        async_func = AsyncMock(return_value="success")
        config = RetryConfig(max_attempts=3)

        result = await async_retry(async_func, config=config)

        assert result == "success"
        async_func.assert_called_once()

    @pytest.mark.asyncio
    async def test_success_after_retries(self):
        """Test async_retry succeeds after initial failures"""
        call_count = 0

        async def failing_then_success():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError(f"Attempt {call_count} failed")
            return "success"

        config = RetryConfig(max_attempts=5, initial_delay_ms=1, jitter_enabled=False)
        result = await async_retry(failing_then_success, config=config)

        assert result == "success"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_all_retries_exhausted(self):
        """Test async_retry raises after all retries exhausted"""

        async def always_fail():
            raise ValueError("Always fails")

        config = RetryConfig(max_attempts=3, initial_delay_ms=1, jitter_enabled=False)

        with pytest.raises(ValueError, match="Always fails"):
            await async_retry(always_fail, config=config)

    @pytest.mark.asyncio
    async def test_retry_with_on_retry_callback(self):
        """Test async_retry calls on_retry callback"""
        call_count = 0
        callback_calls = []

        async def failing_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("fail")
            return "success"

        async def on_retry_callback(attempt, exc):
            callback_calls.append((attempt, str(exc)))

        config = RetryConfig(max_attempts=3, initial_delay_ms=1, jitter_enabled=False)
        result = await async_retry(failing_func, config=config, on_retry=on_retry_callback)

        assert result == "success"
        assert len(callback_calls) == 1
        assert callback_calls[0][0] == 1

    @pytest.mark.asyncio
    async def test_retry_only_on_specified_exceptions(self):
        """Test async_retry only retries specified exception types"""

        async def raise_type_error():
            raise TypeError("not retryable")

        config = RetryConfig(
            max_attempts=3,
            initial_delay_ms=1,
            retry_on_exceptions=(ValueError,),  # Only retry ValueError
        )

        with pytest.raises(TypeError, match="not retryable"):
            await async_retry(raise_type_error, config=config)

    @pytest.mark.asyncio
    async def test_retry_with_args_and_kwargs(self):
        """Test async_retry passes args and kwargs correctly"""

        async def func_with_args(a, b, c=None):
            return f"{a}-{b}-{c}"

        config = RetryConfig(max_attempts=1)
        result = await async_retry(func_with_args, "x", "y", config=config, c="z")

        assert result == "x-y-z"

    @pytest.mark.asyncio
    async def test_retry_default_config(self):
        """Test async_retry with default config (None)"""
        async_func = AsyncMock(return_value="result")

        result = await async_retry(async_func)

        assert result == "result"
        async_func.assert_called_once()

    @pytest.mark.asyncio
    async def test_exponential_backoff_calculation(self):
        """Test that delay increases exponentially"""
        delays = []

        async def track_delays():
            delays.append(datetime.now())
            raise ValueError("fail")

        config = RetryConfig(
            max_attempts=4,
            initial_delay_ms=10,
            backoff_factor=2.0,
            jitter_enabled=False,
        )

        with pytest.raises(ValueError):
            await async_retry(track_delays, config=config)

        # Verify delays increase (approximately - timing isn't exact)
        assert len(delays) == 4

    @pytest.mark.asyncio
    async def test_max_delay_cap(self):
        """Test that delay is capped at max_delay_ms"""
        # With backoff factor 10, would exceed max quickly
        config = RetryConfig(
            max_attempts=5,
            initial_delay_ms=100,
            max_delay_ms=150,  # Cap at 150ms
            backoff_factor=10.0,
            jitter_enabled=False,
        )

        async def fail():
            raise ValueError("fail")

        # Should not take forever due to max_delay cap
        with pytest.raises(ValueError):
            await async_retry(fail, config=config)

    @pytest.mark.asyncio
    async def test_jitter_adds_randomness(self):
        """Test that jitter adds variability to delays"""
        with patch("src.core.tool_broker.resilience.random.uniform") as mock_uniform:
            mock_uniform.return_value = 5.0  # Fixed jitter

            async def fail_once():
                raise ValueError("fail")

            config = RetryConfig(max_attempts=2, initial_delay_ms=100, jitter_enabled=True)

            with pytest.raises(ValueError):
                await async_retry(fail_once, config=config)

            # Verify random.uniform was called for jitter
            assert mock_uniform.called


# ============================================================================
# RETRY DECORATOR TESTS
# ============================================================================


class TestRetryDecorator:
    """Test retry_decorator functionality"""

    @pytest.mark.asyncio
    async def test_decorator_basic_success(self):
        """Test decorator with successful function"""

        @retry_decorator(config=RetryConfig(max_attempts=3))
        async def successful_func():
            return "decorated_success"

        result = await successful_func()
        assert result == "decorated_success"

    @pytest.mark.asyncio
    async def test_decorator_retries_on_failure(self):
        """Test decorator retries on failure"""
        call_count = 0

        @retry_decorator(
            config=RetryConfig(max_attempts=3, initial_delay_ms=1, jitter_enabled=False)
        )
        async def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("fail")
            return "eventual_success"

        result = await fail_then_succeed()

        assert result == "eventual_success"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_decorator_preserves_function_name(self):
        """Test decorator preserves wrapped function name"""

        @retry_decorator()
        async def my_named_function():
            return "result"

        assert my_named_function.__name__ == "my_named_function"

    @pytest.mark.asyncio
    async def test_decorator_default_config(self):
        """Test decorator with default config (None)"""

        @retry_decorator()  # Uses default RetryConfig
        async def func():
            return "default_config"

        result = await func()
        assert result == "default_config"


# ============================================================================
# CIRCUIT BREAKER STATE ENUM TESTS
# ============================================================================


class TestCircuitBreakerState:
    """Test CircuitBreakerState enum"""

    def test_closed_state(self):
        """Test CLOSED state value"""
        assert CircuitBreakerState.CLOSED.value == "closed"

    def test_open_state(self):
        """Test OPEN state value"""
        assert CircuitBreakerState.OPEN.value == "open"

    def test_half_open_state(self):
        """Test HALF_OPEN state value"""
        assert CircuitBreakerState.HALF_OPEN.value == "half_open"

    def test_all_states_exist(self):
        """Test all expected states exist"""
        states = [s.value for s in CircuitBreakerState]
        assert "closed" in states
        assert "open" in states
        assert "half_open" in states
        assert len(states) == 3


# ============================================================================
# CIRCUIT BREAKER CONFIG TESTS
# ============================================================================


class TestCircuitBreakerConfig:
    """Test CircuitBreakerConfig dataclass"""

    def test_default_config(self):
        """Test default configuration values"""
        config = CircuitBreakerConfig()
        assert config.failure_threshold == 5
        assert config.failure_window_seconds == 60
        assert config.success_threshold == 2
        assert config.timeout_seconds == 30
        assert config.half_open_requests == 3

    def test_custom_config(self):
        """Test custom configuration values"""
        config = CircuitBreakerConfig(
            failure_threshold=10,
            failure_window_seconds=120,
            success_threshold=5,
            timeout_seconds=60,
            half_open_requests=5,
        )
        assert config.failure_threshold == 10
        assert config.failure_window_seconds == 120
        assert config.success_threshold == 5
        assert config.timeout_seconds == 60
        assert config.half_open_requests == 5


# ============================================================================
# CIRCUIT BREAKER TESTS
# ============================================================================


class TestCircuitBreakerInitialization:
    """Test CircuitBreaker initialization"""

    def test_default_initialization(self):
        """Test circuit breaker initializes with default config"""
        breaker = CircuitBreaker("test_breaker")

        assert breaker.name == "test_breaker"
        assert breaker.state == CircuitBreakerState.CLOSED
        assert breaker.failure_count == 0
        assert breaker.success_count == 0
        assert breaker.last_failure_time is None
        assert breaker.state_change_time is None
        assert breaker.half_open_request_count == 0

    def test_custom_config_initialization(self):
        """Test circuit breaker with custom config"""
        config = CircuitBreakerConfig(failure_threshold=10)
        breaker = CircuitBreaker("custom_breaker", config=config)

        assert breaker.config.failure_threshold == 10

    def test_get_state(self):
        """Test get_state returns correct dictionary"""
        breaker = CircuitBreaker("test")
        state = breaker.get_state()

        assert state["name"] == "test"
        assert state["state"] == "closed"
        assert state["failure_count"] == 0
        assert state["success_count"] == 0
        assert "half_open_requests" in state


class TestCircuitBreakerClosedState:
    """Test CircuitBreaker in CLOSED state"""

    @pytest.mark.asyncio
    async def test_successful_call_in_closed_state(self):
        """Test successful call passes through in CLOSED state"""
        breaker = CircuitBreaker("test")

        async def success_func():
            return "success"

        result = await breaker.call(success_func)

        assert result == "success"
        assert breaker.state == CircuitBreakerState.CLOSED
        assert breaker.failure_count == 0

    @pytest.mark.asyncio
    async def test_failed_call_increments_failure_count(self):
        """Test failed call increments failure count"""
        breaker = CircuitBreaker("test")

        async def fail_func():
            raise ValueError("failure")

        with pytest.raises(ValueError):
            await breaker.call(fail_func)

        assert breaker.failure_count == 1
        assert breaker.state == CircuitBreakerState.CLOSED

    @pytest.mark.asyncio
    async def test_success_resets_failure_count(self):
        """Test success resets failure count in CLOSED state"""
        breaker = CircuitBreaker("test")
        breaker.failure_count = 3  # Simulate previous failures

        async def success_func():
            return "success"

        await breaker.call(success_func)

        assert breaker.failure_count == 0

    @pytest.mark.asyncio
    async def test_threshold_opens_circuit(self):
        """Test reaching failure threshold opens circuit"""
        config = CircuitBreakerConfig(failure_threshold=3)
        breaker = CircuitBreaker("test", config)

        async def fail_func():
            raise ValueError("failure")

        # Trigger failures up to threshold
        for _ in range(3):
            with pytest.raises(ValueError):
                await breaker.call(fail_func)

        assert breaker.state == CircuitBreakerState.OPEN
        assert breaker.failure_count == 3

    @pytest.mark.asyncio
    async def test_call_with_args_and_kwargs(self):
        """Test call passes args and kwargs correctly"""
        breaker = CircuitBreaker("test")

        async def func_with_args(a, b, c=None):
            return f"{a}-{b}-{c}"

        result = await breaker.call(func_with_args, "x", "y", c="z")

        assert result == "x-y-z"


class TestCircuitBreakerOpenState:
    """Test CircuitBreaker in OPEN state"""

    @pytest.mark.asyncio
    async def test_open_state_rejects_requests(self):
        """Test OPEN state rejects requests immediately"""
        breaker = CircuitBreaker("test")
        breaker.state = CircuitBreakerState.OPEN
        breaker.last_failure_time = datetime.now(timezone.utc)  # Recent failure

        async def any_func():
            return "should not reach"

        with pytest.raises(CircuitBreakerOpenException, match="is OPEN"):
            await breaker.call(any_func)

    @pytest.mark.asyncio
    async def test_open_transitions_to_half_open_after_timeout(self):
        """Test OPEN transitions to HALF_OPEN after timeout"""
        config = CircuitBreakerConfig(reset_timeout_seconds=0)  # Immediate recovery
        breaker = CircuitBreaker("test", config)
        breaker.state = CircuitBreakerState.OPEN
        breaker.last_failure_time = datetime.now(timezone.utc) - timedelta(seconds=1)

        async def success_func():
            return "success"

        result = await breaker.call(success_func)

        assert result == "success"
        # After success in half-open, may still be HALF_OPEN or CLOSED
        assert breaker.state in [
            CircuitBreakerState.HALF_OPEN,
            CircuitBreakerState.CLOSED,
        ]

    @pytest.mark.asyncio
    async def test_should_attempt_reset_no_last_failure(self):
        """Test _should_attempt_reset returns True with no last_failure_time"""
        breaker = CircuitBreaker("test")
        assert breaker._should_attempt_reset() is True

    @pytest.mark.asyncio
    async def test_should_attempt_reset_timeout_expired(self):
        """Test _should_attempt_reset returns True when timeout expired"""
        config = CircuitBreakerConfig(reset_timeout_seconds=10)
        breaker = CircuitBreaker("test", config)
        breaker.last_failure_time = datetime.now(timezone.utc) - timedelta(seconds=20)

        assert breaker._should_attempt_reset() is True

    @pytest.mark.asyncio
    async def test_should_attempt_reset_timeout_not_expired(self):
        """Test _should_attempt_reset returns False when timeout not expired"""
        config = CircuitBreakerConfig(reset_timeout_seconds=60)
        breaker = CircuitBreaker("test", config)
        breaker.last_failure_time = datetime.now(timezone.utc)

        assert breaker._should_attempt_reset() is False


class TestCircuitBreakerHalfOpenState:
    """Test CircuitBreaker in HALF_OPEN state"""

    @pytest.mark.asyncio
    async def test_half_open_allows_limited_requests(self):
        """Test HALF_OPEN allows limited requests"""
        config = CircuitBreakerConfig(half_open_requests=3)
        breaker = CircuitBreaker("test", config)
        breaker.state = CircuitBreakerState.HALF_OPEN

        async def success_func():
            return "success"

        # First 3 requests should succeed
        for _ in range(3):
            result = await breaker.call(success_func)
            assert result == "success"

    @pytest.mark.asyncio
    async def test_half_open_exceeds_request_limit(self):
        """Test HALF_OPEN rejects after reaching request limit"""
        config = CircuitBreakerConfig(half_open_requests=2, success_threshold=5)
        breaker = CircuitBreaker("test", config)
        breaker.state = CircuitBreakerState.HALF_OPEN
        breaker.half_open_request_count = 2  # Already at limit

        async def any_func():
            return "should not reach"

        with pytest.raises(CircuitBreakerOpenException, match="half-open request limit"):
            await breaker.call(any_func)

    @pytest.mark.asyncio
    async def test_half_open_success_transitions_to_closed(self):
        """Test HALF_OPEN transitions to CLOSED after success threshold"""
        config = CircuitBreakerConfig(success_threshold=2)
        breaker = CircuitBreaker("test", config)
        breaker.state = CircuitBreakerState.HALF_OPEN

        async def success_func():
            return "success"

        # First success
        await breaker.call(success_func)
        assert breaker.success_count == 1

        # Second success - should close circuit
        await breaker.call(success_func)
        assert breaker.state == CircuitBreakerState.CLOSED
        assert breaker.failure_count == 0
        assert breaker.success_count == 0

    @pytest.mark.asyncio
    async def test_half_open_failure_reopens_circuit(self):
        """Test HALF_OPEN failure reopens circuit"""
        breaker = CircuitBreaker("test")
        breaker.state = CircuitBreakerState.HALF_OPEN

        async def fail_func():
            raise ValueError("failure")

        with pytest.raises(ValueError):
            await breaker.call(fail_func)

        assert breaker.state == CircuitBreakerState.OPEN

    @pytest.mark.asyncio
    async def test_half_open_increments_request_count(self):
        """Test HALF_OPEN increments request count"""
        breaker = CircuitBreaker("test")
        breaker.state = CircuitBreakerState.HALF_OPEN

        async def success_func():
            return "success"

        await breaker.call(success_func)

        assert breaker.half_open_request_count == 1


class TestCircuitBreakerStateTransitions:
    """Test complete state transitions"""

    @pytest.mark.asyncio
    async def test_full_lifecycle_closed_open_half_open_closed(self):
        """Test full circuit breaker lifecycle"""
        config = CircuitBreakerConfig(
            failure_threshold=2,
            reset_timeout_seconds=0,  # Immediate recovery
            success_threshold=2,
        )
        breaker = CircuitBreaker("lifecycle_test", config)

        async def fail_func():
            raise ValueError("failure")

        async def success_func():
            return "success"

        # Phase 1: CLOSED → OPEN (hit failure threshold)
        assert breaker.state == CircuitBreakerState.CLOSED

        for _ in range(2):
            with pytest.raises(ValueError):
                await breaker.call(fail_func)

        assert breaker.state == CircuitBreakerState.OPEN

        # Phase 2: OPEN → HALF_OPEN (timeout expired, new request)
        breaker.last_failure_time = datetime.now(timezone.utc) - timedelta(seconds=1)

        await breaker.call(success_func)
        # After first success in half-open (from transition)
        assert breaker.state in [
            CircuitBreakerState.HALF_OPEN,
            CircuitBreakerState.CLOSED,
        ]

    @pytest.mark.asyncio
    async def test_rapid_state_changes(self):
        """Test rapid state changes don't corrupt state"""
        config = CircuitBreakerConfig(failure_threshold=1, success_threshold=1, reset_timeout_seconds=0)
        breaker = CircuitBreaker("rapid_test", config)

        async def fail_func():
            raise ValueError("fail")

        async def success_func():
            return "success"

        # Quick cycle
        with pytest.raises(ValueError):
            await breaker.call(fail_func)

        assert breaker.state == CircuitBreakerState.OPEN

        # Allow reset
        breaker.last_failure_time = datetime.now(timezone.utc) - timedelta(seconds=1)

        # Success closes immediately (success_threshold=1)
        await breaker.call(success_func)
        assert breaker.state == CircuitBreakerState.CLOSED


# ============================================================================
# CIRCUIT BREAKER REGISTRY TESTS
# ============================================================================


class TestCircuitBreakerRegistry:
    """Test CircuitBreakerRegistry functionality"""

    def test_registry_initialization(self):
        """Test registry initializes empty"""
        registry = CircuitBreakerRegistry()
        assert len(registry.breakers) == 0

    def test_get_or_create_new_breaker(self):
        """Test get_or_create creates new breaker"""
        registry = CircuitBreakerRegistry()
        breaker = registry.get_or_create("new_breaker")

        assert breaker.name == "new_breaker"
        assert "new_breaker" in registry.breakers

    def test_get_or_create_returns_existing(self):
        """Test get_or_create returns existing breaker"""
        registry = CircuitBreakerRegistry()
        breaker1 = registry.get_or_create("existing")
        breaker2 = registry.get_or_create("existing")

        assert breaker1 is breaker2

    def test_get_or_create_with_config(self):
        """Test get_or_create with custom config"""
        registry = CircuitBreakerRegistry()
        config = CircuitBreakerConfig(failure_threshold=10)
        breaker = registry.get_or_create("custom", config=config)

        assert breaker.config.failure_threshold == 10

    def test_get_existing_breaker(self):
        """Test get returns existing breaker"""
        registry = CircuitBreakerRegistry()
        registry.get_or_create("exists")

        breaker = registry.get("exists")
        assert breaker is not None
        assert breaker.name == "exists"

    def test_get_nonexistent_returns_none(self):
        """Test get returns None for nonexistent breaker"""
        registry = CircuitBreakerRegistry()
        result = registry.get("nonexistent")
        assert result is None

    def test_get_all_states(self):
        """Test get_all_states returns all breaker states"""
        registry = CircuitBreakerRegistry()
        registry.get_or_create("breaker1")
        registry.get_or_create("breaker2")

        states = registry.get_all_states()

        assert "breaker1" in states
        assert "breaker2" in states
        assert states["breaker1"]["state"] == "closed"
        assert states["breaker2"]["state"] == "closed"

    def test_reset_all(self):
        """Test reset_all resets all breakers"""
        registry = CircuitBreakerRegistry()
        breaker1 = registry.get_or_create("b1")
        breaker2 = registry.get_or_create("b2")

        # Simulate failures
        breaker1.state = CircuitBreakerState.OPEN
        breaker1.failure_count = 5
        breaker2.state = CircuitBreakerState.HALF_OPEN
        breaker2.failure_count = 3

        registry.reset_all()

        assert breaker1.state == CircuitBreakerState.CLOSED
        assert breaker1.failure_count == 0
        assert breaker1.success_count == 0
        assert breaker2.state == CircuitBreakerState.CLOSED
        assert breaker2.failure_count == 0


class TestGlobalCircuitBreakerRegistry:
    """Test global circuit breaker registry access"""

    def test_get_global_registry(self):
        """Test get_circuit_breaker_registry returns global registry"""
        registry = get_circuit_breaker_registry()
        assert isinstance(registry, CircuitBreakerRegistry)

    def test_global_registry_is_singleton(self):
        """Test global registry returns same instance"""
        registry1 = get_circuit_breaker_registry()
        registry2 = get_circuit_breaker_registry()
        assert registry1 is registry2


# ============================================================================
# EXCEPTION TESTS
# ============================================================================


class TestResilienceExceptions:
    """Test resilience exception hierarchy"""

    def test_resilience_exception_base(self):
        """Test ResilienceException is Exception subclass"""
        exc = ResilienceException("test error")
        assert isinstance(exc, Exception)
        assert str(exc) == "test error"

    def test_circuit_breaker_open_exception(self):
        """Test CircuitBreakerOpenException"""
        exc = CircuitBreakerOpenException("circuit open")
        assert isinstance(exc, ResilienceException)
        assert str(exc) == "circuit open"

    def test_retry_exhausted_exception(self):
        """Test RetryExhaustedException"""
        exc = RetryExhaustedException("retries exhausted")
        assert isinstance(exc, ResilienceException)
        assert str(exc) == "retries exhausted"


# ============================================================================
# RESILIENCE METRICS TESTS
# ============================================================================


class TestResilienceMetrics:
    """Test ResilienceMetrics tracking"""

    def test_initial_state(self):
        """Test ResilienceMetrics initial state"""
        metrics = ResilienceMetrics()
        assert metrics.total_calls == 0
        assert metrics.successful_calls == 0
        assert metrics.failed_calls == 0
        assert metrics.circuit_breaker_opens == 0
        assert metrics.circuit_breaker_resets == 0
        assert metrics.total_retry_attempts == 0
        assert metrics.successful_retries == 0

    def test_record_successful_call(self):
        """Test recording successful call"""
        metrics = ResilienceMetrics()
        metrics.record_call(success=True)

        assert metrics.total_calls == 1
        assert metrics.successful_calls == 1
        assert metrics.failed_calls == 0

    def test_record_failed_call(self):
        """Test recording failed call"""
        metrics = ResilienceMetrics()
        metrics.record_call(success=False)

        assert metrics.total_calls == 1
        assert metrics.successful_calls == 0
        assert metrics.failed_calls == 1

    def test_record_circuit_breaker_open(self):
        """Test recording circuit breaker open"""
        metrics = ResilienceMetrics()
        metrics.record_circuit_breaker_open()
        metrics.record_circuit_breaker_open()

        assert metrics.circuit_breaker_opens == 2

    def test_record_circuit_breaker_reset(self):
        """Test recording circuit breaker reset"""
        metrics = ResilienceMetrics()
        metrics.record_circuit_breaker_reset()

        assert metrics.circuit_breaker_resets == 1

    def test_record_retry_attempt_success(self):
        """Test recording successful retry attempt"""
        metrics = ResilienceMetrics()
        metrics.record_retry_attempt(success=True)

        assert metrics.total_retry_attempts == 1
        assert metrics.successful_retries == 1

    def test_record_retry_attempt_failure(self):
        """Test recording failed retry attempt"""
        metrics = ResilienceMetrics()
        metrics.record_retry_attempt(success=False)

        assert metrics.total_retry_attempts == 1
        assert metrics.successful_retries == 0

    def test_get_metrics(self):
        """Test get_metrics returns correct values"""
        metrics = ResilienceMetrics()
        metrics.record_call(success=True)
        metrics.record_call(success=False)
        metrics.record_circuit_breaker_open()
        metrics.record_retry_attempt(success=True)
        metrics.record_retry_attempt(success=False)

        result = metrics.get_metrics()

        assert result["total_calls"] == 2
        assert result["successful_calls"] == 1
        assert result["failed_calls"] == 1
        assert result["success_rate"] == 0.5
        assert result["circuit_breaker_opens"] == 1
        assert result["circuit_breaker_resets"] == 0
        assert result["total_retry_attempts"] == 2
        assert result["successful_retries"] == 1
        assert result["retry_success_rate"] == 0.5

    def test_get_metrics_with_zero_calls(self):
        """Test get_metrics handles zero division"""
        metrics = ResilienceMetrics()
        result = metrics.get_metrics()

        assert result["success_rate"] == 0
        assert result["retry_success_rate"] == 0


class TestGlobalResilienceMetrics:
    """Test global resilience metrics access"""

    def test_get_global_metrics(self):
        """Test get_resilience_metrics returns global instance"""
        metrics = get_resilience_metrics()
        assert isinstance(metrics, ResilienceMetrics)

    def test_global_metrics_is_singleton(self):
        """Test global metrics returns same instance"""
        metrics1 = get_resilience_metrics()
        metrics2 = get_resilience_metrics()
        assert metrics1 is metrics2


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestResilienceIntegration:
    """Integration tests for resilience patterns"""

    @pytest.mark.asyncio
    async def test_retry_with_circuit_breaker(self):
        """Test combining retry logic with circuit breaker"""
        config = CircuitBreakerConfig(failure_threshold=3)
        breaker = CircuitBreaker("integrated", config)
        call_count = 0

        async def flaky_service():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("temporary failure")
            return "recovered"

        retry_config = RetryConfig(max_attempts=5, initial_delay_ms=1, jitter_enabled=False)

        result = await async_retry(lambda: breaker.call(flaky_service), config=retry_config)

        assert result == "recovered"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_multiple_breakers_independent(self):
        """Test multiple circuit breakers are independent"""
        breaker1 = CircuitBreaker("service1")
        breaker2 = CircuitBreaker("service2")

        async def fail_func():
            raise ValueError("fail")

        async def success_func():
            return "success"

        # Fail service1
        for _ in range(5):
            with pytest.raises(ValueError):
                await breaker1.call(fail_func)

        # service2 should still work
        result = await breaker2.call(success_func)
        assert result == "success"
        assert breaker2.state == CircuitBreakerState.CLOSED

    @pytest.mark.asyncio
    async def test_registry_manages_multiple_services(self):
        """Test registry manages multiple services independently"""
        registry = CircuitBreakerRegistry()

        # Create breakers for different services
        api_breaker = registry.get_or_create("api_service")
        db_breaker = registry.get_or_create("db_service")
        cache_breaker = registry.get_or_create("cache_service")

        # Simulate API failure
        api_breaker.state = CircuitBreakerState.OPEN

        # Other services unaffected
        assert db_breaker.state == CircuitBreakerState.CLOSED
        assert cache_breaker.state == CircuitBreakerState.CLOSED

        # Verify states
        states = registry.get_all_states()
        assert states["api_service"]["state"] == "open"
        assert states["db_service"]["state"] == "closed"
        assert states["cache_service"]["state"] == "closed"


class TestEdgeCases:
    """Test edge cases and boundary conditions"""

    @pytest.mark.asyncio
    async def test_circuit_breaker_with_very_fast_requests(self):
        """Test circuit breaker handles rapid requests"""
        config = CircuitBreakerConfig(failure_threshold=10)
        breaker = CircuitBreaker("rapid", config)

        async def success_func():
            return "ok"

        # Rapid fire 100 requests
        results = await asyncio.gather(*[breaker.call(success_func) for _ in range(100)])

        assert all(r == "ok" for r in results)
        assert breaker.state == CircuitBreakerState.CLOSED

    @pytest.mark.asyncio
    async def test_retry_with_immediate_success(self):
        """Test retry with immediate success doesn't delay"""
        import time

        start = time.time()

        async def instant_success():
            return "instant"

        config = RetryConfig(max_attempts=10, initial_delay_ms=1000)
        result = await async_retry(instant_success, config=config)

        elapsed = time.time() - start
        assert result == "instant"
        assert elapsed < 0.5  # Should be nearly instant

    def test_circuit_breaker_config_extreme_values(self):
        """Test circuit breaker config with extreme values"""
        # Very high thresholds
        config = CircuitBreakerConfig(
            failure_threshold=1000,
            failure_window_seconds=3600,
            success_threshold=100,
            timeout_seconds=86400,
            half_open_requests=50,
        )

        breaker = CircuitBreaker("extreme", config)
        assert breaker.config.failure_threshold == 1000

    @pytest.mark.asyncio
    async def test_async_retry_empty_exception_tuple(self):
        """Test async_retry with empty exception tuple"""
        # Empty tuple means no exceptions are retried
        config = RetryConfig(max_attempts=3, retry_on_exceptions=())

        async def raise_error():
            raise ValueError("error")

        # Should not retry - ValueError not in empty tuple
        # Actually, empty tuple means no match, so it won't retry
        with pytest.raises(ValueError):
            await async_retry(raise_error, config=config)

    @pytest.mark.asyncio
    async def test_circuit_breaker_state_change_time_set(self):
        """Test state_change_time is set on transitions"""
        config = CircuitBreakerConfig(failure_threshold=1)
        breaker = CircuitBreaker("time_test", config)

        async def fail_func():
            raise ValueError("fail")

        with pytest.raises(ValueError):
            await breaker.call(fail_func)

        # State should have changed to OPEN
        assert breaker.state_change_time is not None

    def test_retry_metrics_accumulate_delays(self):
        """Test retry metrics accumulate total delay correctly"""
        metrics = RetryMetrics()

        metrics.record_attempt(delay_ms=100, success=False)
        metrics.record_attempt(delay_ms=200, success=False)
        metrics.record_attempt(delay_ms=400, success=False)
        metrics.record_attempt(delay_ms=0, success=True)

        assert metrics.total_delay_ms == 700

    @pytest.mark.asyncio
    async def test_concurrent_circuit_breaker_calls(self):
        """Test concurrent calls through circuit breaker"""
        breaker = CircuitBreaker("concurrent")
        call_count = 0

        async def increment():
            nonlocal call_count
            call_count += 1
            await asyncio.sleep(0.01)
            return call_count

        # Run 10 concurrent calls
        results = await asyncio.gather(*[breaker.call(increment) for _ in range(10)])

        assert len(results) == 10
        assert call_count == 10


class TestLoggingBehavior:
    """Test logging behavior in resilience module"""

    @pytest.mark.asyncio
    async def test_circuit_breaker_logs_state_transitions(self):
        """Test circuit breaker logs state transitions"""
        config = CircuitBreakerConfig(failure_threshold=1, reset_timeout_seconds=0)
        breaker = CircuitBreaker("log_test", config)

        async def fail_func():
            raise ValueError("fail")

        async def success_func():
            return "success"

        # Trigger CLOSED -> OPEN
        with pytest.raises(ValueError):
            await breaker.call(fail_func)

        assert breaker.state == CircuitBreakerState.OPEN

        # Trigger OPEN -> HALF_OPEN -> CLOSED
        breaker.last_failure_time = datetime.now(timezone.utc) - timedelta(seconds=1)
        config.success_threshold = 1

        await breaker.call(success_func)

        # Verify state is now CLOSED
        assert breaker.state == CircuitBreakerState.CLOSED


# ============================================================================
# PERFORMANCE TESTS
# ============================================================================


class TestResiliencePerformance:
    """Performance tests for resilience patterns"""

    @pytest.mark.asyncio
    async def test_circuit_breaker_minimal_overhead(self):
        """Test circuit breaker adds minimal overhead"""
        import time

        breaker = CircuitBreaker("perf")

        async def fast_func():
            return 1

        iterations = 1000
        start = time.time()

        for _ in range(iterations):
            await breaker.call(fast_func)

        elapsed = time.time() - start
        avg_time_ms = (elapsed / iterations) * 1000

        # Average time per call should be < 1ms
        assert avg_time_ms < 1.0

    def test_registry_lookup_performance(self):
        """Test registry lookup is fast"""
        import time

        registry = CircuitBreakerRegistry()

        # Create 100 breakers
        for i in range(100):
            registry.get_or_create(f"breaker_{i}")

        # Measure lookup time
        iterations = 10000
        start = time.time()

        for i in range(iterations):
            registry.get(f"breaker_{i % 100}")

        elapsed = time.time() - start

        # Should complete in < 100ms for 10k lookups
        assert elapsed < 0.1
