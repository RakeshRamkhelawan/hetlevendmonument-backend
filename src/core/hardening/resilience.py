"""
TKT-F4-02: Reliability Hardening

Controlled degradation with timeouts, retries, and circuit breakers.
No silent failures.
"""

import asyncio
import random
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set, TypeVar, cast
from collections.abc import Awaitable, Callable

from src.core.shared.tool_broker_resilience import (
    CircuitBreaker,
    CircuitBreakerConfig,
    CircuitBreakerOpenException,
    CircuitBreakerRegistry,
    get_circuit_breaker_registry,
)

T = TypeVar("T")


class DegradationMode(Enum):
    """Service degradation mode"""

    FULL = "full"  # Normal operation
    DEGRADED = "degraded"  # Reduced functionality
    FAILSAFE = "failsafe"  # Minimal functionality
    OFFLINE = "offline"  # Service unavailable


@dataclass
class RetryPolicy:
    """Retry configuration"""

    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True

    def get_delay(self, attempt: int) -> float:
        """Calculate delay for attempt"""
        delay = self.base_delay * (self.exponential_base**attempt)
        delay = min(delay, self.max_delay)

        if self.jitter:
            delay = delay * (0.5 + random.random() * 0.5)

        return delay


@dataclass
class TimeoutPolicy:
    """Timeout configuration"""

    connect_timeout: float = 5.0
    read_timeout: float = 30.0
    total_timeout: float = 60.0


@dataclass
class CircuitBreakerPolicy:
    """Circuit breaker configuration"""

    failure_threshold: int = 5
    recovery_timeout: float = 60.0
    half_open_max_calls: int = 3
    success_threshold: int = 2


@dataclass
class ResilienceMetrics:
    """Metrics for resilience operations"""

    total_calls: int = 0
    successful_calls: int = 0
    failed_calls: int = 0
    retried_calls: int = 0
    circuit_open_calls: int = 0
    timeout_calls: int = 0
    fallback_calls: int = 0
    avg_latency_ms: float = 0.0

    def record_success(self, latency_ms: float) -> None:
        self.total_calls += 1
        self.successful_calls += 1
        # Update running average
        self.avg_latency_ms = (
            self.avg_latency_ms * (self.total_calls - 1) + latency_ms
        ) / self.total_calls

    def record_failure(self) -> None:
        self.total_calls += 1
        self.failed_calls += 1

    def record_retry(self) -> None:
        self.retried_calls += 1

    def record_circuit_open(self) -> None:
        self.circuit_open_calls += 1

    def record_timeout(self) -> None:
        self.timeout_calls += 1

    def record_fallback(self) -> None:
        self.fallback_calls += 1

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        return {
            "total_calls": self.total_calls,
            "successful_calls": self.successful_calls,
            "failed_calls": self.failed_calls,
            "retried_calls": self.retried_calls,
            "circuit_open_calls": self.circuit_open_calls,
            "timeout_calls": self.timeout_calls,
            "fallback_calls": self.fallback_calls,
            "success_rate": (
                (self.successful_calls / self.total_calls * 100) if self.total_calls > 0 else 0
            ),
            "avg_latency_ms": self.avg_latency_ms,
        }


class ResilienceManager:
    """
    Manages resilience patterns for critical paths.

    Provides:
    - Timeouts with cancellation
    - Exponential backoff retries
    - Circuit breaker protection
    - Graceful degradation
    - No silent failures

    Usage:
        manager = ResilienceManager()

        # Configure for a service
        manager.configure_service(
            "payment_gateway",
            retry_policy=RetryPolicy(max_attempts=5),
            timeout_policy=TimeoutPolicy(total_timeout=30),
            circuit_breaker=CircuitBreakerPolicy()
        )

        # Execute with resilience
        result = await manager.execute(
            "payment_gateway",
            process_payment,
            args=(payment_data,),
            fallback=fallback_handler
        )
    """

    def __init__(self) -> None:
        self._services: dict[str, dict[str, Any]] = {}  # TODO(TYPE): replace Any with concrete type
        self._circuit_breakers: dict[str, CircuitBreaker] = {}
        self._metrics: dict[str, ResilienceMetrics] = {}
        self._degradation_modes: dict[str, DegradationMode] = {}
        self._fallback_handlers: dict[
            str, Callable[..., Awaitable[object]]
        ] = {}

    def configure_service(
        self,
        service_name: str,
        retry_policy: RetryPolicy | None = None,
        timeout_policy: TimeoutPolicy | None = None,
        circuit_breaker: CircuitBreakerPolicy | None = None,
        fallback: Callable[..., Awaitable[object]]
        | None = None,
    ) -> None:
        """Configure resilience for a service"""
        self._services[service_name] = {
            "retry_policy": retry_policy or RetryPolicy(),
            "timeout_policy": timeout_policy or TimeoutPolicy(),
            "circuit_breaker": circuit_breaker or CircuitBreakerPolicy(),
        }

        # Create circuit breaker
        if circuit_breaker:
            config = CircuitBreakerConfig(
                failure_threshold=circuit_breaker.failure_threshold,
                timeout_seconds=int(circuit_breaker.recovery_timeout),
                half_open_requests=circuit_breaker.half_open_max_calls,
                success_threshold=circuit_breaker.success_threshold,
            )
            registry = get_circuit_breaker_registry()
            self._circuit_breakers[service_name] = registry.get_or_create(service_name, config)

        self._metrics[service_name] = ResilienceMetrics()
        self._degradation_modes[service_name] = DegradationMode.FULL

        if fallback:
            self._fallback_handlers[service_name] = fallback

    async def execute(
        self,
        service_name: str,
        func: Callable[..., Awaitable[T]],
        args: tuple[Any, ...] = (),  # TODO(TYPE): replace Any with concrete type
        kwargs: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        fallback: Callable[..., Awaitable[T]] | None = None,
    ) -> T:
        """
        Execute function with full resilience protection.

        Args:
            service_name: Service identifier
            func: Function to execute
            args: Positional arguments
            kwargs: Keyword arguments
            fallback: Optional fallback function

        Returns:
            Function result

        Raises:
            Exception: If all retries fail and no fallback
        """
        kwargs = kwargs or {}
        config = self._services.get(service_name, {})
        retry_policy = config.get("retry_policy", RetryPolicy())
        timeout_policy = config.get("timeout_policy", TimeoutPolicy())
        circuit_breaker = self._circuit_breakers.get(service_name)
        metrics = self._metrics[service_name]

        last_exception = None

        # Check circuit breaker
        if circuit_breaker and circuit_breaker.state.value == "open":
            metrics.record_circuit_open()
            return await self._handle_fallback(service_name, fallback, args, kwargs, metrics)

        # Try with retries
        for attempt in range(retry_policy.max_attempts):
            start_time = time.time()

            try:
                # Execute with timeout
                result = await asyncio.wait_for(
                    func(*args, **kwargs), timeout=timeout_policy.total_timeout
                )

                latency_ms = (time.time() - start_time) * 1000
                metrics.record_success(latency_ms)

                return result

            except TimeoutError:
                metrics.record_timeout()
                last_exception = Exception("Operation timed out")

            except CircuitBreakerOpenException:
                metrics.record_circuit_open()
                return await self._handle_fallback(service_name, fallback, args, kwargs, metrics)

            except Exception as e:
                last_exception = e
                metrics.record_failure()

                # Don't retry on certain errors
                if self._is_non_retryable(e):
                    break

            # Retry with delay
            if attempt < retry_policy.max_attempts - 1:
                metrics.record_retry()
                delay = retry_policy.get_delay(attempt)
                await asyncio.sleep(delay)

        # All retries exhausted, try fallback
        return await self._handle_fallback(
            service_name, fallback, args, kwargs, metrics, last_exception
        )

    async def _handle_fallback(
        self,
        service_name: str,
        fallback: Callable[..., Awaitable[T]] | None,
        args: tuple[Any, ...],  # TODO(TYPE): replace Any with concrete type
        kwargs: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        metrics: ResilienceMetrics,
        last_exception: Exception | None = None,
    ) -> T:
        """Handle fallback execution"""
        # Use configured fallback or provided fallback
        handler = fallback or self._fallback_handlers.get(service_name)

        if handler:
            metrics.record_fallback()
            try:
                result = handler(*args, **kwargs)
                if asyncio.iscoroutine(result):
                    return cast(T, await result)
                return cast(T, result)
            except Exception as e:
                # Fallback also failed
                raise FallbackFailedException(
                    f"Primary and fallback both failed: {e}"
                ) from last_exception

        # No fallback available
        if last_exception:
            raise last_exception
        raise ResilienceException("Service unavailable and no fallback configured")

    def _is_non_retryable(self, exception: Exception) -> bool:
        """Check if exception should not be retried"""
        # Don't retry on client errors (4xx)
        error_str = str(exception).lower()
        if any(code in error_str for code in ["400", "401", "403", "404", "409"]):
            return True
        return False

    def set_degradation_mode(self, service_name: str, mode: DegradationMode) -> None:
        """Set degradation mode for service"""
        self._degradation_modes[service_name] = mode

    def get_metrics(
        self, service_name: str | None = None
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get metrics for service(s)"""
        if service_name:
            return self._metrics.get(service_name, ResilienceMetrics()).to_dict()

        return {name: metrics.to_dict() for name, metrics in self._metrics.items()}

    def get_health_status(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get overall health status"""
        total_services = len(self._services)
        healthy_services = 0
        degraded_services = 0

        for service_name in self._services:
            mode = self._degradation_modes.get(service_name, DegradationMode.FULL)
            if mode == DegradationMode.FULL:
                healthy_services += 1
            elif mode in [DegradationMode.DEGRADED, DegradationMode.FAILSAFE]:
                degraded_services += 1

        return {
            "total_services": total_services,
            "healthy": healthy_services,
            "degraded": degraded_services,
            "offline": total_services - healthy_services - degraded_services,
            "overall_health": "healthy" if healthy_services == total_services else "degraded",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


class ResilienceException(Exception):
    """Base exception for resilience failures"""

    pass


class FallbackFailedException(ResilienceException):
    """Raised when both primary and fallback fail"""

    pass
