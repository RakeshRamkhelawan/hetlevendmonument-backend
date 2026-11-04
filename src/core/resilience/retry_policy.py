"""
Retry Policy - Configurable retry strategies

Provides:
- Exponential backoff with jitter
- Linear backoff
- Max duration and max attempts limits
- Circuit breaker integration
"""

import asyncio
import logging
import random
import time
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, TypeVar, cast
from collections.abc import Callable

from src.core.resilience.circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)

T = TypeVar("T")


class RetryStrategy(Enum):
    """Retry backoff strategies."""

    EXPONENTIAL = auto()  # 2^attempt * base_delay
    LINEAR = auto()  # attempt * base_delay
    FIXED = auto()  # constant delay


@dataclass
class RetryConfig:
    """Configuration for retry policy."""

    max_attempts: int = 3
    base_delay: float = 1.0  # Base delay in seconds
    max_delay: float = 60.0  # Max delay between retries
    max_duration: float | None = None  # Max total time for all retries
    strategy: RetryStrategy = RetryStrategy.EXPONENTIAL
    jitter: bool = True  # Add randomization to prevent thundering herd
    jitter_max: float = 1.0  # Max jitter in seconds
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,)
    circuit_breaker: CircuitBreaker | None = None


class RetryExhaustedError(Exception):
    """Raised when all retry attempts are exhausted."""

    def __init__(
        self, message: str, attempts: int, last_exception: Exception | None = None
    ) -> None:
        self.attempts = attempts
        self.last_exception = last_exception
        super().__init__(message)


class RetryPolicy:
    """
    Configurable retry policy with multiple backoff strategies.

    Usage:
        # Exponential backoff with jitter
        policy = RetryPolicy.with_exponential_backoff(max_attempts=5)

        result = await policy.execute(async_function, arg1, arg2)

        # With circuit breaker
        policy = RetryPolicy(
            max_attempts=3,
            strategy=RetryStrategy.EXPONENTIAL,
            circuit_breaker=circuit_breaker,
        )
    """

    def __init__(
        self,
        max_attempts: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        max_duration: float | None = None,
        strategy: RetryStrategy = RetryStrategy.EXPONENTIAL,
        jitter: bool = True,
        jitter_max: float = 1.0,
        retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
        circuit_breaker: CircuitBreaker | None = None,
    ):
        """
        Initialize retry policy.

        Args:
            max_attempts: Maximum number of retry attempts
            base_delay: Base delay between retries
            max_delay: Maximum delay between retries
            max_duration: Maximum total duration for all retries
            strategy: Backoff strategy (EXPONENTIAL, LINEAR, FIXED)
            jitter: Add randomization to delays
            jitter_max: Maximum jitter in seconds
            retryable_exceptions: Exception types to retry on
            circuit_breaker: Optional circuit breaker to check
        """
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.max_duration = max_duration
        self.strategy = strategy
        self.jitter = jitter
        self.jitter_max = jitter_max
        self.retryable_exceptions = retryable_exceptions
        self.circuit_breaker = circuit_breaker

    @classmethod
    def with_exponential_backoff(
        cls, max_attempts: int = 3, base_delay: float = 1.0, **kwargs: Any
    ) -> "RetryPolicy":
        """Create policy with exponential backoff."""
        return cls(
            max_attempts=max_attempts,
            base_delay=base_delay,
            strategy=RetryStrategy.EXPONENTIAL,
            **kwargs,
        )

    @classmethod
    def with_linear_backoff(
        cls, max_attempts: int = 3, base_delay: float = 1.0, **kwargs: Any
    ) -> "RetryPolicy":
        """Create policy with linear backoff."""
        return cls(
            max_attempts=max_attempts,
            base_delay=base_delay,
            strategy=RetryStrategy.LINEAR,
            **kwargs,
        )

    @classmethod
    def with_fixed_delay(
        cls, max_attempts: int = 3, delay: float = 1.0, **kwargs: Any
    ) -> "RetryPolicy":
        """Create policy with fixed delay."""
        return cls(
            max_attempts=max_attempts, base_delay=delay, strategy=RetryStrategy.FIXED, **kwargs
        )

    def calculate_delay(self, attempt: int) -> float:
        """
        Calculate delay for a retry attempt.

        Args:
            attempt: Current attempt number (0-indexed)

        Returns:
            Delay in seconds
        """
        if self.strategy == RetryStrategy.EXPONENTIAL:
            delay = self.base_delay * (2**attempt)
        elif self.strategy == RetryStrategy.LINEAR:
            delay = self.base_delay * (attempt + 1)
        else:  # FIXED
            delay = self.base_delay

        # Cap at max delay
        delay = min(delay, self.max_delay)

        # Add jitter to prevent thundering herd
        if self.jitter:
            jitter = random.uniform(0, self.jitter_max)
            delay += jitter

        return cast(float, delay)

    async def execute(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """
        Execute a function with retry logic.

        Args:
            func: Async function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Result from func

        Raises:
            RetryExhaustedError: If all retries exhausted
            Exception: If non-retryable exception occurs
        """
        start_time = time.time()
        last_exception: Exception | None = None

        for attempt in range(self.max_attempts):
            try:
                # Check circuit breaker if provided
                if self.circuit_breaker:
                    from .circuit_breaker import CircuitOpenError

                    try:
                        return await self.circuit_breaker.execute(func, *args, **kwargs)
                    except CircuitOpenError:
                        # Don't retry if circuit is open
                        raise
                else:
                    return await func(*args, **kwargs)

            except Exception as e:
                last_exception = e

                # Check if exception is retryable
                if not isinstance(e, self.retryable_exceptions):
                    raise

                # Check max duration
                if self.max_duration:
                    elapsed = time.time() - start_time
                    if elapsed >= self.max_duration:
                        logger.warning(
                            f"Retry policy: Max duration ({self.max_duration}s) exceeded "
                            f"after {attempt + 1} attempts"
                        )
                        raise RetryExhaustedError(
                            f"Max duration exceeded after {attempt + 1} attempts",
                            attempts=attempt + 1,
                            last_exception=last_exception,
                        )

                # Check if we should retry
                if attempt < self.max_attempts - 1:
                    delay = self.calculate_delay(attempt)
                    logger.warning(
                        f"Retry policy: Attempt {attempt + 1}/{self.max_attempts} failed: {e}. "
                        f"Retrying in {delay:.2f}s..."
                    )
                    await asyncio.sleep(delay)
                else:
                    # All attempts exhausted
                    logger.error(
                        f"Retry policy: All {self.max_attempts} attempts failed. Last error: {e}"
                    )

        # Should not reach here, but just in case
        raise RetryExhaustedError(
            f"All {self.max_attempts} attempts exhausted",
            attempts=self.max_attempts,
            last_exception=last_exception,
        )

    def get_config(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get retry policy configuration."""
        return {
            "max_attempts": self.max_attempts,
            "base_delay": self.base_delay,
            "max_delay": self.max_delay,
            "max_duration": self.max_duration,
            "strategy": self.strategy.name,
            "jitter": self.jitter,
            "jitter_max": self.jitter_max,
            "has_circuit_breaker": self.circuit_breaker is not None,
        }


# For backward compatibility with existing code
__all__ = [
    "RetryPolicy",
    "RetryStrategy",
    "RetryConfig",
    "RetryExhaustedError",
]
