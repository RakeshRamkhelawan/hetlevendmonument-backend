"""
SD-11.2: Connection Retry Logic
Implements retry logic for database connections.
"""

import asyncio
import inspect
import logging
import random
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""

    max_retries: int = 3
    base_delay: float = 1.0  # seconds
    max_delay: float = 30.0  # seconds
    exponential_base: float = 2.0
    jitter: bool = True
    retryable_exceptions: tuple[type[BaseException], ...] = (
        ConnectionError,
        TimeoutError,
        OSError,
    )


def calculate_delay(attempt: int, config: RetryConfig) -> float:
    """Calculate delay with exponential backoff and jitter."""
    delay = min(config.base_delay * (config.exponential_base**attempt), config.max_delay)

    if config.jitter:
        # Add random jitter (0-100% of delay)
        delay = delay * (0.5 + random.random())

    return delay


def with_retry(
    config: RetryConfig | None = None,
    on_retry: Callable[..., Any] | None = None,  # TODO(TYPE): replace Any with concrete type
) -> Callable[..., Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Decorator to add retry logic to a function.

    Args:
        config: Retry configuration
        on_retry: Callback called before each retry

    Usage:
        @with_retry(RetryConfig(max_retries=5))
        async def connect_to_database():
            ...
    """
    config = config or RetryConfig()

    def decorator(
        func: Callable[..., Any],
    ) -> Callable[..., Any]:  # TODO(TYPE): replace Any with concrete type
        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: BaseException | None = None

            for attempt in range(config.max_retries + 1):
                try:
                    result = func(*args, **kwargs)
                    if inspect.isawaitable(result):
                        return await result
                    return result
                except config.retryable_exceptions as e:
                    last_exception = e

                    if attempt < config.max_retries:
                        delay = calculate_delay(attempt, config)

                        logger.warning(
                            f"Attempt {attempt + 1} failed: {e}. Retrying in {delay:.2f}s..."
                        )

                        if on_retry:
                            on_retry(attempt + 1, e)

                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            f"All {config.max_retries + 1} attempts failed. Last error: {e}"
                        )

            if last_exception is None:
                raise RuntimeError("Retry failed without captured exception")
            raise last_exception

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            import time

            last_exception: BaseException | None = None

            for attempt in range(config.max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except config.retryable_exceptions as e:
                    last_exception = e

                    if attempt < config.max_retries:
                        delay = calculate_delay(attempt, config)

                        logger.warning(
                            f"Attempt {attempt + 1} failed: {e}. Retrying in {delay:.2f}s..."
                        )

                        if on_retry:
                            on_retry(attempt + 1, e)

                        time.sleep(delay)
                    else:
                        logger.error(f"All attempts failed. Last error: {e}")

            if last_exception is None:
                raise RuntimeError("Retry failed without captured exception")
            raise last_exception

        # Return appropriate wrapper based on function type
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


class ConnectionRetryManager:
    """
    SD-11.2: Manages database connection retries.

    Features:
    - Exponential backoff
    - Jitter to prevent thundering herd
    - Configurable retry limits
    - Circuit breaker pattern
    """

    def __init__(self, config: RetryConfig | None = None) -> None:
        self.config = config or RetryConfig()
        self.consecutive_failures = 0
        self.circuit_open = False
        self.circuit_open_until: float | None = None

    async def execute_with_retry(self, func: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        """Execute a function with retry logic."""
        # Check circuit breaker
        if self.circuit_open:
            import time

            if self.circuit_open_until is not None and time.time() < self.circuit_open_until:
                raise ConnectionError("Circuit breaker is open")
            self.circuit_open = False

        last_exception: BaseException | None = None

        for attempt in range(self.config.max_retries + 1):
            try:
                result = func(*args, **kwargs)
                if inspect.isawaitable(result):
                    result = await result
                self.consecutive_failures = 0
                return result  # pyright: ignore[reportReturnType]

            except self.config.retryable_exceptions as e:
                last_exception = e
                self.consecutive_failures += 1

                # Open circuit breaker after too many failures
                if self.consecutive_failures >= self.config.max_retries * 2:
                    import time

                    self.circuit_open = True
                    self.circuit_open_until = time.time() + 60  # 1 minute
                    logger.error("Circuit breaker opened due to repeated failures")

                if attempt < self.config.max_retries:
                    delay = calculate_delay(attempt, self.config)
                    logger.warning(f"Retry {attempt + 1}: {e}")
                    await asyncio.sleep(delay)

        if last_exception is None:
            raise RuntimeError("Retry failed without captured exception")
        raise last_exception

    def reset_circuit_breaker(self) -> None:
        """Manually reset the circuit breaker."""
        self.circuit_open = False
        self.circuit_open_until = None
        self.consecutive_failures = 0
        logger.info("Circuit breaker reset")


# Database-specific retry configuration
DATABASE_RETRY_CONFIG = RetryConfig(
    max_retries=5,
    base_delay=0.5,
    max_delay=30.0,
    exponential_base=2.0,
    jitter=True,
    retryable_exceptions=(
        ConnectionError,
        TimeoutError,
        OSError,
        # Add database-specific exceptions
    ),
)

# Global retry manager
retry_manager = ConnectionRetryManager(DATABASE_RETRY_CONFIG)
