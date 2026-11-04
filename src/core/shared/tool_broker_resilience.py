"""
Resilience Patterns: retry, circuit breaker, graceful degradation.

Canonical locatie: src/core/resilience/ (infra-laag, I=0.000).
Verplaatst uit tool_broker/resilience.py -- SP-DSM-015 dag 1.
Achterwaartse compatibiliteit via src/core/tool_broker/resilience.py (re-export shim).
"""

import asyncio
import random
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from enum import Enum
from functools import wraps
from typing import Any, TypeVar

from loguru import logger

T = TypeVar("T")

__all__ = [
    "RetryConfig",
    "RetryMetrics",
    "async_retry",
    "retry_decorator",
    "CircuitBreakerState",
    "CircuitBreakerConfig",
    "CircuitBreaker",
    "CircuitBreakerRegistry",
    "get_circuit_breaker_registry",
    "ResilienceException",
    "CircuitBreakerOpenException",
    "RetryExhaustedException",
    "ResilienceMetrics",
    "get_resilience_metrics",
]

# ============================================================================
# RETRY LOGIC WITH EXPONENTIAL BACKOFF
# ============================================================================


class RetryConfig:
    """Configuration for retry behavior"""

    def __init__(
        self,
        max_attempts: int = 3,
        initial_delay_ms: int = 100,
        max_delay_ms: int = 10000,
        backoff_factor: float = 2.0,
        jitter_enabled: bool = True,
        retry_on_exceptions: tuple[type[Exception], ...] | None = None,
    ) -> None:
        self.max_attempts = max_attempts
        self.initial_delay_ms = initial_delay_ms
        self.max_delay_ms = max_delay_ms
        self.backoff_factor = backoff_factor
        self.jitter_enabled = jitter_enabled
        self.retry_on_exceptions = retry_on_exceptions or (Exception,)

        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        if initial_delay_ms < 0:
            raise ValueError("initial_delay_ms must be >= 0")


class RetryMetrics:
    """Tracks retry attempt statistics"""

    def __init__(self) -> None:
        self.total_attempts = 0
        self.successful_retries = 0
        self.failed_retries = 0
        self.total_delay_ms = 0
        self.last_attempt_time: datetime | None = None
        self.last_error: Exception | None = None

    def record_attempt(
        self,
        delay_ms: int = 0,
        success: bool = False,
        error: Exception | None = None,
    ) -> None:
        """Record a retry attempt"""
        self.total_attempts += 1
        self.total_delay_ms += delay_ms
        self.last_attempt_time = datetime.now(timezone.utc)

        if success:
            self.successful_retries += 1
        else:
            self.failed_retries += 1
            self.last_error = error

    def get_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get retry statistics"""
        return {
            "total_attempts": self.total_attempts,
            "successful_retries": self.successful_retries,
            "failed_retries": self.failed_retries,
            "total_delay_ms": self.total_delay_ms,
            "last_attempt_time": self.last_attempt_time,
            "last_error": str(self.last_error) if self.last_error else None,
        }


async def async_retry(
    func: Callable[..., Awaitable[T]],
    *args: Any,
    config: RetryConfig | None = None,
    on_retry: Callable[..., Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    **kwargs: Any,
) -> T:
    """Execute async function with exponential backoff retry logic."""
    if config is None:
        config = RetryConfig()

    metrics = RetryMetrics()
    last_exception: Exception | None = None

    for attempt in range(config.max_attempts):
        try:
            result = await func(*args, **kwargs)
            metrics.record_attempt(success=True)
            logger.debug(
                "Async retry succeeded on attempt %d/%d",
                attempt + 1,
                config.max_attempts,
            )
            return result
        except config.retry_on_exceptions as e:
            last_exception = e
            metrics.record_attempt(success=False, error=e)

            if attempt == config.max_attempts - 1:
                logger.error(
                    "Async retry failed after %d attempts: %s",
                    config.max_attempts,
                    e,
                    exc_info=True,
                )
                break

            delay_ms = min(
                config.initial_delay_ms * (config.backoff_factor**attempt),
                config.max_delay_ms,
            )

            if config.jitter_enabled:
                jitter = random.uniform(0, delay_ms * 0.1)
                delay_ms += jitter

            logger.warning(
                "Async retry attempt %d failed, retrying in %.0fms: %s",
                attempt + 1,
                delay_ms,
                e,
            )

            if on_retry:
                await on_retry(attempt + 1, e)

            await asyncio.sleep(delay_ms / 1000.0)

    if last_exception:
        raise last_exception
    raise RuntimeError("Retry loop failed without exception")


def retry_decorator(
    config: RetryConfig | None = None,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    """Decorator for async functions with automatic retry logic."""

    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            return await async_retry(func, *args, config=config, **kwargs)

        return wrapper

    return decorator


# ============================================================================
# CIRCUIT BREAKER PATTERN
# ============================================================================


class CircuitBreakerState(Enum):
    """States of the circuit breaker state machine"""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerConfig:
    """Configuration for circuit breaker behavior"""

    def __init__(
        self,
        failure_threshold: int = 5,
        failure_window_seconds: int = 60,
        success_threshold: int = 2,
        timeout_seconds: int = 30,
        half_open_requests: int = 3,
        reset_timeout_seconds: int = 30,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.failure_window_seconds = failure_window_seconds
        self.success_threshold = success_threshold
        self.timeout_seconds = timeout_seconds
        self.half_open_requests = half_open_requests
        self.reset_timeout_seconds = reset_timeout_seconds


class CircuitBreaker:
    """Circuit breaker with CLOSED/OPEN/HALF_OPEN state machine."""

    def __init__(self, name: str, config: CircuitBreakerConfig | None = None) -> None:
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: datetime | None = None
        self.state_change_time: datetime | None = None
        self.half_open_request_count = 0
        logger.info("Circuit breaker '%s' initialized in CLOSED state", name)

    def call(self, func: Callable[..., Awaitable[T]], *args: Any, **kwargs: Any) -> Awaitable[T]:
        """Execute function through circuit breaker"""
        return self._protected_call(func, *args, **kwargs)

    async def _protected_call(
        self, func: Callable[..., Awaitable[T]], *args: Any, **kwargs: Any
    ) -> T:
        if self.state == CircuitBreakerState.OPEN:
            if self._should_attempt_reset():
                logger.info("Circuit breaker '%s' transitioning to HALF_OPEN", self.name)
                self.state = CircuitBreakerState.HALF_OPEN
                self.success_count = 0
                self.half_open_request_count = 0
                self.state_change_time = datetime.now(timezone.utc)
            else:
                raise CircuitBreakerOpenException(
                    f"Circuit breaker '{self.name}' is OPEN, request rejected"
                )

        if self.state == CircuitBreakerState.HALF_OPEN:
            if self.half_open_request_count >= self.config.half_open_requests:
                raise CircuitBreakerOpenException(
                    f"Circuit breaker '{self.name}' reached half-open request limit"
                )
            self.half_open_request_count += 1

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception:
            self._on_failure()
            raise

    def _on_success(self) -> None:
        if self.state == CircuitBreakerState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                logger.info("Circuit breaker '%s' transitioning to CLOSED (recovered)", self.name)
                self.state = CircuitBreakerState.CLOSED
                self.failure_count = 0
                self.success_count = 0
                self.state_change_time = datetime.now(timezone.utc)
        elif self.state == CircuitBreakerState.CLOSED:
            self.failure_count = 0

    def _on_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = datetime.now(timezone.utc)

        if self.state == CircuitBreakerState.HALF_OPEN:
            logger.warning(
                "Circuit breaker '%s' failed during recovery, reopening circuit", self.name
            )
            self.state = CircuitBreakerState.OPEN
            self.state_change_time = datetime.now(timezone.utc)
        elif self.state == CircuitBreakerState.CLOSED:
            if self.failure_count >= self.config.failure_threshold:
                logger.error(
                    "Circuit breaker '%s' threshold reached, opening circuit (failures: %d)",
                    self.name,
                    self.failure_count,
                )
                self.state = CircuitBreakerState.OPEN
                self.state_change_time = datetime.now(timezone.utc)

    def _should_attempt_reset(self) -> bool:
        if not self.last_failure_time:
            return True
        time_since_failure = datetime.now(timezone.utc) - self.last_failure_time
        return time_since_failure >= timedelta(seconds=self.config.reset_timeout_seconds)

    def get_state(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "success_count": self.success_count,
            "last_failure_time": self.last_failure_time,
            "state_change_time": self.state_change_time,
            "half_open_requests": self.half_open_request_count,
        }


class CircuitBreakerRegistry:
    """Manages multiple circuit breakers"""

    def __init__(self) -> None:
        self.breakers: dict[str, CircuitBreaker] = {}
        logger.info("Circuit breaker registry initialized")

    def get_or_create(
        self, name: str, config: CircuitBreakerConfig | None = None
    ) -> CircuitBreaker:
        if name not in self.breakers:
            self.breakers[name] = CircuitBreaker(name, config)
        return self.breakers[name]

    def get(self, name: str) -> CircuitBreaker | None:
        return self.breakers.get(name)

    def get_all_states(
        self,
    ) -> dict[str, dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        return {name: breaker.get_state() for name, breaker in self.breakers.items()}

    def reset_all(self) -> None:
        for breaker in self.breakers.values():
            breaker.state = CircuitBreakerState.CLOSED
            breaker.failure_count = 0
            breaker.success_count = 0
            logger.info("Circuit breaker '%s' reset to CLOSED", breaker.name)


_circuit_breaker_registry: CircuitBreakerRegistry | None = None


def get_circuit_breaker_registry() -> CircuitBreakerRegistry:
    """Get global circuit breaker registry"""
    global _circuit_breaker_registry
    if _circuit_breaker_registry is None:
        _circuit_breaker_registry = CircuitBreakerRegistry()
    return _circuit_breaker_registry


# ============================================================================
# EXCEPTIONS
# ============================================================================


class ResilienceException(Exception):
    """Base exception for resilience module"""


class CircuitBreakerOpenException(ResilienceException):
    """Raised when circuit breaker is open"""


class RetryExhaustedException(ResilienceException):
    """Raised when all retry attempts are exhausted"""


# ============================================================================
# RESILIENCE METRICS
# ============================================================================


class ResilienceMetrics:
    """Tracks resilience pattern metrics"""

    def __init__(self) -> None:
        self.total_calls = 0
        self.successful_calls = 0
        self.failed_calls = 0
        self.circuit_breaker_opens = 0
        self.circuit_breaker_resets = 0
        self.total_retry_attempts = 0
        self.successful_retries = 0

    def record_call(self, success: bool) -> None:
        self.total_calls += 1
        if success:
            self.successful_calls += 1
        else:
            self.failed_calls += 1

    def record_circuit_breaker_open(self) -> None:
        self.circuit_breaker_opens += 1

    def record_circuit_breaker_reset(self) -> None:
        self.circuit_breaker_resets += 1

    def record_retry_attempt(self, success: bool) -> None:
        self.total_retry_attempts += 1
        if success:
            self.successful_retries += 1

    def get_metrics(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "success_rate": (
                self.successful_calls / self.total_calls if self.total_calls > 0 else 0
            ),
            "circuit_breaker_opens": self.circuit_breaker_opens,
            "circuit_breaker_resets": self.circuit_breaker_resets,
            "total_retry_attempts": self.total_retry_attempts,
            "successful_retries": self.successful_retries,
            "retry_success_rate": (
                self.successful_retries / self.total_retry_attempts
                if self.total_retry_attempts > 0
                else 0
            ),
        }


_resilience_metrics = ResilienceMetrics()


def get_resilience_metrics() -> ResilienceMetrics:
    """Get global resilience metrics"""
    return _resilience_metrics
