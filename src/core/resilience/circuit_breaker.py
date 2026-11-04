"""
Circuit Breaker Pattern - Fault Tolerance for External Services

Provides:
- Circuit breaker with CLOSED -> OPEN -> HALF_OPEN states
- Per-provider tracking (separate breakers per LLM provider)
- Metrics tracking (calls, failures, state changes)
- Configurable thresholds and recovery timeouts
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, TypeVar
from collections.abc import Callable

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation - calls pass through
    OPEN = "open"  # Failing fast - calls rejected immediately
    HALF_OPEN = "half_open"  # Testing recovery - limited calls allowed


@dataclass
class CircuitBreakerConfig:
    """Backward-compatible circuit breaker configuration."""

    failure_threshold: int = 5
    recovery_timeout: float | None = None
    timeout_seconds: float | None = None
    half_open_max_calls: int | None = None
    half_open_requests: int | None = None
    success_threshold: int | None = None
    success_threshold_half_open: int | None = None
    failure_window_seconds: float | None = None

    def __post_init__(self) -> None:
        if self.recovery_timeout is None:
            self.recovery_timeout = (
                self.timeout_seconds if self.timeout_seconds is not None else 60.0
            )
        self.timeout_seconds = self.recovery_timeout

        if self.half_open_max_calls is None:
            self.half_open_max_calls = (
                self.half_open_requests if self.half_open_requests is not None else 3
            )
        self.half_open_requests = self.half_open_max_calls

        if self.success_threshold is None:
            self.success_threshold = (
                self.success_threshold_half_open
                if self.success_threshold_half_open is not None
                else 2
            )
        self.success_threshold_half_open = self.success_threshold


class CircuitOpenError(Exception):
    """Raised when circuit breaker is OPEN."""

    def __init__(self, provider: str, message: str | None = None) -> None:
        self.provider = provider
        self.message = message or f"Circuit '{provider}' is OPEN"
        super().__init__(self.message)

    def __str__(self) -> str:
        return self.message


@dataclass
class CircuitMetrics:
    """Metrics for circuit breaker."""

    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    rejected_calls: int = 0  # Calls rejected due to OPEN circuit
    state_changes: int = 0
    last_failure_time: float | None = None
    last_success_time: float | None = None

    def record_call(self, success: bool) -> None:
        """Record a call result."""
        self.total_calls += 1
        if success:
            self.successful_calls += 1
            self.last_success_time = time.time()
        else:
            self.failed_calls += 1
            self.last_failure_time = time.time()

    def record_rejection(self) -> None:
        """Record a rejected call."""
        self.rejected_calls += 1

    def record_state_change(self) -> None:
        """Record a state change."""
        self.state_changes += 1

    @property
    def failure_rate(self) -> float:
        """Calculate failure rate (0.0 - 1.0)."""
        if self.total_calls == 0:
            return 0.0
        return self.failed_calls / self.total_calls

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert to dictionary."""
        return {
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "rejected_calls": self.rejected_calls,
            "state_changes": self.state_changes,
            "failure_rate": self.failure_rate,
            "last_failure_time": self.last_failure_time,
            "last_success_time": self.last_success_time,
        }


@dataclass
class CircuitStats:
    """Legacy stats view exposed by older call sites and tests."""

    metrics: CircuitMetrics

    @property
    def failures(self) -> int:
        return self.metrics.failed_calls

    @property
    def successes(self) -> int:
        return self.metrics.successful_calls

    @property
    def total_calls(self) -> int:
        return self.metrics.total_calls

    @property
    def rejected(self) -> int:
        return self.metrics.rejected_calls

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return self.metrics.to_dict()


class CircuitBreaker:
    """
    Circuit breaker for protecting against cascading failures.

    State transitions:
    - CLOSED -> OPEN: When failure_threshold is reached
    - OPEN -> HALF_OPEN: After recovery_timeout seconds
    - HALF_OPEN -> CLOSED: After half_open_max_calls successful calls
    - HALF_OPEN -> OPEN: After any failure in half-open state

    Usage:
        breaker = CircuitBreaker("gemini", failure_threshold=5)

        try:
            result = await breaker.execute(gemini_api_call, prompt)
        except CircuitOpenError:
            # Circuit is open, use fallback
            result = await fallback_call(prompt)
    """

    def __init__(
        self,
        provider: str,
        failure_threshold: int | CircuitBreakerConfig = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 3,
        success_threshold_half_open: int = 2,
    ) -> None:
        """
        Initialize circuit breaker.

        Args:
            provider: Provider name (e.g., "gemini", "openai")
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Seconds to wait before trying half-open
            half_open_max_calls: Max calls allowed in half-open state
            success_threshold_half_open: Successful calls needed to close
        """
        self.provider = provider
        self.name = provider

        if isinstance(failure_threshold, CircuitBreakerConfig):
            config = failure_threshold
        else:
            config = CircuitBreakerConfig(
                failure_threshold=failure_threshold,
                recovery_timeout=recovery_timeout,
                half_open_max_calls=half_open_max_calls,
                success_threshold=success_threshold_half_open,
            )

        self.config = config
        self.failure_threshold = config.failure_threshold
        # __post_init__ guarantees non-None; assert to narrow the Optional types
        assert config.recovery_timeout is not None
        assert config.half_open_max_calls is not None
        assert config.success_threshold is not None
        self.recovery_timeout = float(config.recovery_timeout)
        self.half_open_max_calls = int(config.half_open_max_calls)
        self.success_threshold_half_open = int(config.success_threshold)

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count_half_open = 0
        self._half_open_calls = 0
        self._last_failure_time: float | None = None
        self._metrics = CircuitMetrics()
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        """Get current circuit state."""
        return self._state

    @property
    def metrics(self) -> CircuitMetrics:
        """Get circuit metrics."""
        return self._metrics

    @property
    def stats(self) -> CircuitStats:
        """Legacy stats accessor."""
        return CircuitStats(self._metrics)

    @property
    def half_open_calls(self) -> int:
        """Legacy accessor for half-open call count."""
        return self._half_open_calls

    @property
    def success_threshold(self) -> int:
        """Legacy accessor for half-open success threshold."""
        return self.success_threshold_half_open

    async def execute(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """
        Execute a function with circuit breaker protection.

        Args:
            func: Async function to execute
            *args: Positional arguments for func
            **kwargs: Keyword arguments for func

        Returns:
            Result from func

        Raises:
            CircuitOpenError: If circuit is OPEN
            Exception: Any exception from func  # TODO(TYPE): replace Any with concrete type
        """
        async with self._lock:
            # Check if we should transition from OPEN to HALF_OPEN
            if self._state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    logger.info(f"Circuit {self.provider}: Transitioning to HALF_OPEN")
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
                    self._success_count_half_open = 0
                    self._metrics.record_state_change()
                else:
                    # Circuit is open, reject call
                    self._metrics.record_rejection()
                    logger.debug(f"Circuit {self.provider}: Rejecting call (OPEN)")
                    retry_after = 0.0
                    if self._last_failure_time is not None:
                        elapsed = time.time() - self._last_failure_time
                        retry_after = max(0.0, self.recovery_timeout - elapsed)
                    raise CircuitOpenError(
                        self.provider,
                        f"Circuit '{self.provider}' is OPEN. Retry after {retry_after:.2f}s",
                    )

            # In HALF_OPEN, limit concurrent calls
            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self.half_open_max_calls:
                    self._metrics.record_rejection()
                    raise CircuitOpenError(
                        self.provider,
                        f"Circuit '{self.provider}' HALF_OPEN limit reached ({self.half_open_max_calls})",
                    )
                self._half_open_calls += 1

        # Execute the function (outside lock)
        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        except Exception as e:
            await self._on_failure()
            raise

    async def call(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """Backward-compatible alias for execute()."""
        return await self.execute(func, *args, **kwargs)

    async def _on_success(self) -> None:
        """Handle successful call."""
        async with self._lock:
            self._metrics.record_call(success=True)

            if self._state == CircuitState.HALF_OPEN:
                self._success_count_half_open += 1

                # Check if we can close the circuit
                if self._success_count_half_open >= self.success_threshold_half_open:
                    logger.info(f"Circuit {self.provider}: Transitioning to CLOSED")
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._metrics.record_state_change()

    async def _on_failure(self) -> None:
        """Handle failed call."""
        async with self._lock:
            self._metrics.record_call(success=False)

            if self._state == CircuitState.HALF_OPEN:
                # Any failure in half-open goes back to open
                logger.warning(f"Circuit {self.provider}: Failure in HALF_OPEN, returning to OPEN")
                self._state = CircuitState.OPEN
                self._last_failure_time = time.time()
                self._metrics.record_state_change()
            elif self._state == CircuitState.CLOSED:
                self._failure_count += 1

                if self._failure_count >= self.failure_threshold:
                    logger.warning(
                        f"Circuit {self.provider}: Failure threshold ({self.failure_threshold}) "
                        f"reached, transitioning to OPEN"
                    )
                    self._state = CircuitState.OPEN
                    self._last_failure_time = time.time()
                    self._metrics.record_state_change()

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to try half-open."""
        if self._last_failure_time is None:
            return True
        return time.time() - self._last_failure_time >= self.recovery_timeout

    def get_state(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get current circuit state as dictionary."""
        return {
            "provider": self.provider,
            "state": self._state.name,
            "failure_count": self._failure_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
            "metrics": self._metrics.to_dict(),
        }

    def get_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Backward-compatible stats dictionary."""
        return {
            "name": self.name,
            "provider": self.provider,
            "state": self.state.value,
            "failure_count": self._failure_count,
            **self._metrics.to_dict(),
        }

    async def reset(self) -> None:
        """Manually reset circuit to CLOSED state (for testing/admin)."""
        async with self._lock:
            old_state = self._state
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count_half_open = 0
            self._half_open_calls = 0
            if old_state != CircuitState.CLOSED:
                self._metrics.record_state_change()
            logger.info(f"Circuit {self.provider}: Manually reset to CLOSED")


class CircuitBreakerRegistry:
    """
    Registry for managing multiple circuit breakers (per-provider).

    Usage:
        registry = CircuitBreakerRegistry()

        # Get or create breaker for provider
        breaker = registry.get_breaker("gemini")
        result = await breaker.execute(gemini_call, prompt)
    """

    def __init__(self) -> None:
        self._breakers: dict[str, CircuitBreaker] = {}
        self._lock = asyncio.Lock()

    async def get_breaker(
        self,
        provider: str,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
    ) -> CircuitBreaker:
        """
        Get or create a circuit breaker for a provider.

        Args:
            provider: Provider name
            failure_threshold: Failures before opening (for new breaker)
            recovery_timeout: Recovery timeout seconds (for new breaker)

        Returns:
            CircuitBreaker for the provider
        """
        async with self._lock:
            if provider not in self._breakers:
                self._breakers[provider] = CircuitBreaker(
                    provider=provider,
                    failure_threshold=failure_threshold,
                    recovery_timeout=recovery_timeout,
                )
                logger.info(f"Created circuit breaker for {provider}")
            return self._breakers[provider]

    async def get_all_states(
        self,
    ) -> dict[str, dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get states of all circuit breakers."""
        async with self._lock:
            return {provider: breaker.get_state() for provider, breaker in self._breakers.items()}

    async def reset_all(self) -> None:
        """Reset all circuit breakers to CLOSED."""
        async with self._lock:
            for breaker in self._breakers.values():
                await breaker.reset()

    async def reset_provider(self, provider: str) -> bool:
        """Reset a specific provider's circuit breaker."""
        async with self._lock:
            if provider in self._breakers:
                await self._breakers[provider].reset()
                return True
            return False


CircuitBreakerOpen = CircuitOpenError

_breaker_cache: dict[str, CircuitBreaker] = {}


def get_circuit_breaker(
    provider: str,
    config: CircuitBreakerConfig | None = None,
    failure_threshold: int = 5,
    recovery_timeout: float = 60.0,
) -> CircuitBreaker:
    """Backward-compatible global circuit breaker factory."""
    if provider not in _breaker_cache:
        breaker_config = config or CircuitBreakerConfig(
            failure_threshold=failure_threshold,
            recovery_timeout=recovery_timeout,
        )
        _breaker_cache[provider] = CircuitBreaker(provider, breaker_config)
    return _breaker_cache[provider]


def circuit_breaker(
    name: str,
    threshold: int = 5,
    recovery_timeout: float = 60.0,
) -> Callable[..., Any]:  # TODO(TYPE): replace Any with concrete type
    """Backward-compatible decorator using a cached breaker per function name."""

    breaker = get_circuit_breaker(
        name,
        CircuitBreakerConfig(
            failure_threshold=threshold,
            recovery_timeout=recovery_timeout,
        ),
    )

    def decorator(
        func: Callable[..., Any],
    ) -> Callable[..., Any]:  # TODO(TYPE): replace Any with concrete type
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            return await breaker.call(func, *args, **kwargs)

        return wrapper

    return decorator


google_api_breaker = get_circuit_breaker("google_api")
stripe_api_breaker = get_circuit_breaker("stripe_api")
deepseek_api_breaker = get_circuit_breaker("deepseek_api")


__all__ = [
    "CircuitBreaker",
    "CircuitBreakerConfig",
    "CircuitBreakerOpen",
    "CircuitBreakerRegistry",
    "CircuitMetrics",
    "CircuitOpenError",
    "CircuitState",
    "circuit_breaker",
    "deepseek_api_breaker",
    "get_circuit_breaker",
    "google_api_breaker",
    "stripe_api_breaker",
]
