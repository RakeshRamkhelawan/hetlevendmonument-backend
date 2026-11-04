"""
Connection pooling for database and LLM clients.

Provides:
- Async connection pooling with health checks
- Circuit breaker pattern for failing connections
- Automatic retry with exponential backoff
- Connection lifecycle management
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, Generic, List, Optional, Set, TypeVar
from collections.abc import AsyncIterator, Callable

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ConnectionState(Enum):
    """Connection lifecycle states."""

    IDLE = "idle"
    IN_USE = "in_use"
    UNHEALTHY = "unhealthy"
    CLOSED = "closed"


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if recovered


@dataclass
class PoolConfig:
    """Connection pool configuration."""

    min_size: int = 5
    max_size: int = 20
    max_idle_time: float = 300.0  # 5 minutes
    max_lifetime: float = 3600.0  # 1 hour
    health_check_interval: float = 30.0
    acquire_timeout: float = 10.0

    # Retry settings
    max_retries: int = 3
    retry_delay_base: float = 1.0
    retry_delay_max: float = 60.0

    # Circuit breaker settings
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 3


@dataclass
class ConnectionWrapper(Generic[T]):
    """Wrapper for pooled connections with metadata."""

    connection: T
    state: ConnectionState = ConnectionState.IDLE
    created_at: float = field(default_factory=time.time)
    last_used_at: float = field(default_factory=time.time)
    use_count: int = 0
    failure_count: int = 0


class ConnectionFactory(ABC, Generic[T]):
    """Abstract factory for creating connections."""

    @abstractmethod
    async def create(self) -> T:
        """Create a new connection."""
        pass

    @abstractmethod
    async def close(self, connection: T) -> None:
        """Close a connection."""
        pass

    @abstractmethod
    async def is_healthy(self, connection: T) -> bool:
        """Check if connection is healthy."""
        pass

    @abstractmethod
    async def reset(self, connection: T) -> None:
        """Reset connection state before reuse."""
        pass


class CircuitBreaker:
    """
    Circuit breaker pattern for handling failing connections.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 3,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float | None = None
        self._half_open_calls = 0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        return self._state

    async def can_execute(self) -> bool:
        """Check if operation can be executed."""
        async with self._lock:
            if self._state == CircuitState.CLOSED:
                return True

            if self._state == CircuitState.OPEN:
                if self._should_attempt_reset():
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
                    logger.info("Circuit breaker entering HALF_OPEN state")
                    return True
                return False

            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_calls < self.half_open_max_calls:
                    self._half_open_calls += 1
                    return True
                return False

            return True

    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset."""
        if self._last_failure_time is None:
            return True
        return time.time() - self._last_failure_time >= self.recovery_timeout

    async def record_success(self) -> None:
        """Record successful operation."""
        async with self._lock:
            self._failure_count = 0

            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.half_open_max_calls:
                    self._state = CircuitState.CLOSED
                    self._success_count = 0
                    self._half_open_calls = 0
                    logger.info("Circuit breaker CLOSED (recovered)")

    async def record_failure(self) -> None:
        """Record failed operation."""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning("Circuit breaker OPEN (half-open test failed)")
            elif self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(f"Circuit breaker OPEN ({self._failure_count} failures)")


class AsyncConnectionPool(Generic[T]):
    """
    Advanced async connection pool with health checks and circuit breaker.

    Features:
    - Min/max pool size management
    - Connection health checks
    - Automatic retry with exponential backoff
    - Circuit breaker pattern
    - Connection lifecycle management
    """

    def __init__(
        self,
        name: str,
        factory: ConnectionFactory[T],
        config: PoolConfig | None = None,
    ) -> None:
        self.name = name
        self.factory = factory
        self.config = config or PoolConfig()

        self._pool: asyncio.Queue[ConnectionWrapper[T]] = asyncio.Queue()
        self._in_use: set[ConnectionWrapper[T]] = set()
        self._all_connections: list[ConnectionWrapper[T]] = []

        self._lock = asyncio.Lock()
        self._semaphore = asyncio.Semaphore(self.config.max_size)
        self._circuit_breaker = CircuitBreaker(
            failure_threshold=self.config.failure_threshold,
            recovery_timeout=self.config.recovery_timeout,
            half_open_max_calls=self.config.half_open_max_calls,
        )

        self._initialized = False
        self._closed = False
        self._maintenance_task: asyncio.Task[Any] | None = None  # TODO(TYPE): replace Any with concrete type

        # Metrics
        self._total_acquisitions = 0
        self._total_releases = 0
        self._failed_acquisitions = 0
        self._health_check_failures = 0

        logger.info(
            f"Connection pool '{name}' created (min={self.config.min_size}, max={self.config.max_size})"
        )

    async def initialize(self) -> None:
        """Initialize pool with minimum connections."""
        if self._initialized:
            return

        async with self._lock:
            for _ in range(self.config.min_size):
                try:
                    conn = await self._create_connection()
                    await self._pool.put(conn)
                except Exception as e:
                    logger.warning(f"Failed to create initial connection: {e}")

            self._initialized = True

            # Start maintenance task
            self._maintenance_task = asyncio.create_task(
                self._maintenance_loop(), name=f"pool_maintenance_{self.name}"
            )

            logger.info(f"Pool '{self.name}' initialized with {self._pool.qsize()} connections")

    async def close(self) -> None:
        """Close all connections and pool."""
        self._closed = True

        if self._maintenance_task:
            self._maintenance_task.cancel()
            try:
                await self._maintenance_task
            except asyncio.CancelledError:
                pass

        async with self._lock:
            # Close all connections
            for wrapper in self._all_connections:
                try:
                    await self.factory.close(wrapper.connection)
                except Exception as e:
                    logger.warning(f"Error closing connection: {e}")

            self._all_connections.clear()
            self._in_use.clear()

            # Clear the queue
            while not self._pool.empty():
                try:
                    self._pool.get_nowait()
                except asyncio.QueueEmpty:
                    break

        logger.info(f"Pool '{self.name}' closed")

    async def acquire(self) -> T:
        """Acquire connection from pool with retry logic."""
        if self._closed:
            raise RuntimeError("Pool is closed")

        self._total_acquisitions += 1

        # Check circuit breaker
        if not await self._circuit_breaker.can_execute():
            raise RuntimeError("Circuit breaker is OPEN")

        async with self._semaphore:
            for attempt in range(self.config.max_retries + 1):
                try:
                    conn = await asyncio.wait_for(
                        self._get_connection(), timeout=self.config.acquire_timeout
                    )
                    return conn.connection

                except TimeoutError:
                    if attempt == self.config.max_retries:
                        self._failed_acquisitions += 1
                        raise RuntimeError(
                            f"Timeout acquiring connection after {attempt + 1} attempts"
                        )

                    delay = min(
                        self.config.retry_delay_base * (2**attempt), self.config.retry_delay_max
                    )
                    logger.debug(f"Acquire attempt {attempt + 1} failed, retrying in {delay}s")
                    await asyncio.sleep(delay)

                except Exception as e:
                    if attempt == self.config.max_retries:
                        self._failed_acquisitions += 1
                        await self._circuit_breaker.record_failure()
                        raise
                    await asyncio.sleep(self.config.retry_delay_base)
            # Fallback: should never reach here due to raise in except blocks
            raise RuntimeError("Failed to acquire connection")

    async def release(self, connection: T, is_healthy: bool = True) -> None:
        """Release connection back to pool."""
        if self._closed:
            return

        self._total_releases += 1

        # Find wrapper
        wrapper = None
        for w in self._in_use:
            if w.connection is connection:
                wrapper = w
                break

        if not wrapper:
            logger.warning("Released connection not from this pool")
            return

        self._in_use.discard(wrapper)

        if not is_healthy:
            wrapper.failure_count += 1
            await self.factory.close(wrapper.connection)
            self._all_connections.remove(wrapper)

            # Create replacement if below min_size
            if len(self._all_connections) < self.config.min_size:
                try:
                    new_wrapper = await self._create_connection()
                    await self._pool.put(new_wrapper)
                except Exception as e:
                    logger.warning(f"Failed to create replacement connection: {e}")
            return

        # Connection is healthy
        await self._circuit_breaker.record_success()
        wrapper.state = ConnectionState.IDLE
        wrapper.last_used_at = time.time()
        wrapper.use_count += 1

        await self.factory.reset(wrapper.connection)

        try:
            self._pool.put_nowait(wrapper)
        except asyncio.QueueFull:
            # Pool is full, close connection
            await self.factory.close(wrapper.connection)
            self._all_connections.remove(wrapper)

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[T]:
        """Context manager for acquiring and releasing connections."""
        conn = None
        is_healthy = True
        try:
            conn = await self.acquire()
            yield conn
        except Exception:
            is_healthy = False
            raise
        finally:
            if conn:
                await self.release(conn, is_healthy)

    async def _get_connection(self) -> ConnectionWrapper[T]:
        """Get connection from pool or create new one."""
        # Try to get from pool
        if not self._pool.empty():
            wrapper = self._pool.get_nowait()

            # Check if connection is still healthy
            if await self.factory.is_healthy(wrapper.connection):
                wrapper.state = ConnectionState.IN_USE
                self._in_use.add(wrapper)
                return wrapper
            else:
                # Close unhealthy connection
                await self.factory.close(wrapper.connection)
                self._all_connections.remove(wrapper)

        # Create new connection
        wrapper = await self._create_connection()
        wrapper.state = ConnectionState.IN_USE
        self._in_use.add(wrapper)
        return wrapper

    async def _create_connection(self) -> ConnectionWrapper[T]:
        """Create new connection with retry."""
        for attempt in range(self.config.max_retries + 1):
            try:
                conn = await self.factory.create()
                wrapper = ConnectionWrapper(connection=conn)
                self._all_connections.append(wrapper)
                return wrapper
            except Exception as e:
                if attempt == self.config.max_retries:
                    raise

                delay = min(
                    self.config.retry_delay_base * (2**attempt), self.config.retry_delay_max
                )
                logger.warning(f"Connection creation failed (attempt {attempt + 1}), retrying: {e}")
                await asyncio.sleep(delay)

        raise RuntimeError("Failed to create connection after all retries")

    async def _maintenance_loop(self) -> None:
        """Background maintenance task."""
        while not self._closed:
            try:
                await asyncio.sleep(self.config.health_check_interval)
                await self._perform_maintenance()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Maintenance error: {e}")

    async def _perform_maintenance(self) -> None:
        """Perform pool maintenance (health checks, cleanup)."""
        now = time.time()

        async with self._lock:
            # Check idle connections
            to_remove: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for wrapper in self._all_connections:
                if wrapper.state == ConnectionState.IDLE:
                    # Check max idle time
                    idle_time = now - wrapper.last_used_at
                    if idle_time > self.config.max_idle_time:
                        if len(self._all_connections) > self.config.min_size:
                            to_remove.append(wrapper)
                            continue

                    # Health check
                    try:
                        is_healthy = await asyncio.wait_for(
                            self.factory.is_healthy(wrapper.connection), timeout=5.0
                        )
                        if not is_healthy:
                            to_remove.append(wrapper)
                            self._health_check_failures += 1
                    except TimeoutError:
                        to_remove.append(wrapper)
                        self._health_check_failures += 1

                elif wrapper.state == ConnectionState.IN_USE:
                    # Check max lifetime
                    lifetime = now - wrapper.created_at
                    if lifetime > self.config.max_lifetime:
                        # Mark for replacement after release
                        pass

            # Remove unhealthy connections
            for wrapper in to_remove:
                try:
                    await self.factory.close(wrapper.connection)
                except Exception:
                    pass
                self._all_connections.remove(wrapper)

                # Create replacement
                try:
                    new_wrapper = await self._create_connection()
                    await self._pool.put(new_wrapper)
                except Exception as e:
                    logger.warning(f"Failed to create replacement: {e}")

    def get_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get pool statistics."""
        return {
            "name": self.name,
            "initialized": self._initialized,
            "closed": self._closed,
            "circuit_state": self._circuit_breaker.state.value,
            "total_connections": len(self._all_connections),
            "idle_connections": self._pool.qsize(),
            "in_use_connections": len(self._in_use),
            "total_acquisitions": self._total_acquisitions,
            "total_releases": self._total_releases,
            "failed_acquisitions": self._failed_acquisitions,
            "health_check_failures": self._health_check_failures,
        }
