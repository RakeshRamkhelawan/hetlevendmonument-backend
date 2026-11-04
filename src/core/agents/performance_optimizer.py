"""
Performance Optimizer for SanskritiSetu Agent System.

Provides caching, connection pooling, and parallel execution optimizations
for the orchestration layer.
"""

import asyncio
import functools
import hashlib
import logging
import time
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import (
    Any,  # TODO(TYPE): replace Any with concrete type
    Dict,
    Generic,
    List,
    Optional,
    Set,
    TypeVar,
    Union,
    cast,
)
from collections.abc import Callable, Coroutine

# Optional imports with error handling
HAS_ASYNCpg = False
HAS_AIOREDIS = False
HAS_PROMETHEUS = False


# Dummy metrics classes (fallback)
class DummyCounter:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.value: float = 0.0

    def labels(self, *args: Any, **kwargs: Any) -> "DummyCounter":
        return self

    def inc(self, amount: float = 1.0, *args: Any, **kwargs: Any) -> None:
        self.value += float(amount)


class DummyGauge:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.value: float = 0.0

    def labels(self, *args: Any, **kwargs: Any) -> "DummyGauge":
        return self

    def set(self, value: float, *args: Any, **kwargs: Any) -> None:
        self.value = float(value)

    def inc(self, amount: float = 1.0, *args: Any, **kwargs: Any) -> None:
        self.value += float(amount)

    def dec(self, amount: float = 1.0, *args: Any, **kwargs: Any) -> None:
        self.value -= float(amount)


class DummyHistogram:
    MAX_OBSERVATIONS = 1000

    def __init__(self, *args: Any, maxlen: int = MAX_OBSERVATIONS, **kwargs: Any) -> None:
        self.observations: deque[float] = deque(maxlen=maxlen)

    def labels(self, *args: Any, **kwargs: Any) -> "DummyHistogram":
        return self

    def observe(self, amount: float, *args: Any, **kwargs: Any) -> None:
        self.observations.append(float(amount))


# Try to import real implementations
try:
    import asyncpg

    HAS_ASYNCpg = True
except ImportError:
    pass

try:
    import aioredis

    HAS_AIOREDIS = True
except (ImportError, TypeError):
    # TypeError can occur with Python 3.13+ compatibility issues
    pass

try:
    from prometheus_client import Counter, Gauge, Histogram

    HAS_PROMETHEUS = True
except ImportError:
    Counter = DummyCounter  # type: ignore[misc,assignment]
    Gauge = DummyGauge  # type: ignore[misc,assignment]
    Histogram = DummyHistogram  # type: ignore[misc,assignment]

logger = logging.getLogger(__name__)

# Prometheus metrics
CACHE_HITS = Counter("agent_cache_hits_total", "Cache hits", ["cache_name"])
CACHE_MISSES = Counter("agent_cache_misses_total", "Cache misses", ["cache_name"])
CACHE_SIZE = Gauge("agent_cache_size", "Current cache size", ["cache_name"])
EXECUTION_TIME = Histogram("agent_execution_seconds", "Execution time", ["agent_type"])
ACTIVE_WORKERS = Gauge("agent_active_workers", "Number of active worker threads")

T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    """Generic cache entry with metadata."""

    value: T
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    access_count: int = 0
    last_accessed: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    size_bytes: int = 0


class LRUCache(Generic[T]):
    """
    Thread-safe LRU Cache with size-based eviction and TTL support.

    Features:
    - O(1) get and set operations
    - Size-based eviction (max_size)
    - TTL support (max_age_seconds)
    - Memory usage tracking
    - Hit/miss statistics
    """

    def __init__(
        self,
        name: str,
        max_size: int = 1000,
        max_age_seconds: int | None = None,
        max_memory_mb: float | None = None,
    ) -> None:
        self.name = name
        self.max_size = max_size
        self.max_age = timedelta(seconds=max_age_seconds) if max_age_seconds else None
        self.max_memory_bytes = max_memory_mb * 1024 * 1024 if max_memory_mb else None

        self._cache: dict[str, CacheEntry[T]] = {}
        self._lock = asyncio.Lock()
        self._access_order: list[str] = []

        # Statistics
        self._hits = 0
        self._misses = 0
        self._evictions = 0

        logger.info(
            f"Initialized LRUCache '{name}' (max_size={max_size}, "
            f"max_age={max_age_seconds}s, max_memory={max_memory_mb}MB)"
        )

    async def get(self, key: str) -> T | None:
        """Get value from cache. Updates access order."""
        async with self._lock:
            entry = self._cache.get(key)

            if entry is None:
                self._misses += 1
                CACHE_MISSES.labels(cache_name=self.name).inc()
                return None

            # Check TTL
            if self.max_age and (datetime.now(timezone.utc) - entry.created_at) > self.max_age:
                self._cache.pop(key, None)
                if key in self._access_order:
                    self._access_order.remove(key)
                self._misses += 1
                CACHE_MISSES.labels(cache_name=self.name).inc()
                return None

            # Update access metadata
            entry.access_count += 1
            entry.last_accessed = datetime.now(timezone.utc)

            # Move to end (most recently used)
            if key in self._access_order:
                self._access_order.remove(key)
            self._access_order.append(key)

            self._hits += 1
            CACHE_HITS.labels(cache_name=self.name).inc()

            return entry.value

    async def set(self, key: str, value: T, size_bytes: int = 0) -> None:
        """Set value in cache with automatic eviction."""
        async with self._lock:
            # Create entry
            entry = CacheEntry(value=value, size_bytes=size_bytes)

            # Check if we need to evict
            await self._maybe_evict(size_bytes)

            # Add/update entry
            if key in self._cache:
                # Update existing
                self._access_order.remove(key)
            elif len(self._cache) >= self.max_size:
                # Evict oldest
                await self._evict_oldest()

            self._cache[key] = entry
            self._access_order.append(key)

            CACHE_SIZE.labels(cache_name=self.name).set(len(self._cache))

    async def _maybe_evict(self, new_entry_size: int) -> None:
        """Evict entries if memory limit would be exceeded."""
        if not self.max_memory_bytes:
            return

        current_size = sum(e.size_bytes for e in self._cache.values())
        while current_size + new_entry_size > self.max_memory_bytes and self._cache:
            await self._evict_oldest()
            current_size = sum(e.size_bytes for e in self._cache.values())

    async def _evict_oldest(self) -> None:
        """Evict least recently used entry."""
        if not self._access_order:
            return

        oldest_key = self._access_order.pop(0)
        self._cache.pop(oldest_key, None)
        self._evictions += 1

        logger.debug(f"LRUCache '{self.name}' evicted key: {oldest_key}")

    async def invalidate(self, key: str) -> bool:
        """Remove specific key from cache."""
        async with self._lock:
            if key in self._cache:
                self._cache.pop(key)
                self._access_order.remove(key)
                CACHE_SIZE.labels(cache_name=self.name).set(len(self._cache))
                return True
            return False

    async def invalidate_pattern(self, pattern: str) -> int:
        """Remove all keys matching pattern (supports * wildcard)."""
        async with self._lock:
            if pattern == "*":
                count = len(self._cache)
                self._cache.clear()
                self._access_order.clear()
                CACHE_SIZE.labels(cache_name=self.name).set(0)
                return count

            # Simple prefix matching
            prefix = pattern.rstrip("*")
            keys_to_remove = [k for k in self._cache.keys() if k.startswith(prefix)]

            for key in keys_to_remove:
                self._cache.pop(key)
                self._access_order.remove(key)

            CACHE_SIZE.labels(cache_name=self.name).set(len(self._cache))
            return len(keys_to_remove)

    async def clear(self) -> None:
        """Clear entire cache."""
        async with self._lock:
            self._cache.clear()
            self._access_order.clear()
            CACHE_SIZE.labels(cache_name=self.name).set(0)

    def get_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get cache statistics."""
        total_requests = self._hits + self._misses
        hit_rate = self._hits / total_requests if total_requests > 0 else 0.0

        return {
            "name": self.name,
            "size": len(self._cache),
            "max_size": self.max_size,
            "hits": self._hits,
            "misses": self._misses,
            "evictions": self._evictions,
            "hit_rate": round(hit_rate, 4),
            "memory_usage_bytes": sum(e.size_bytes for e in self._cache.values()),
        }


class AsyncConnectionPool:
    """
    Generic async connection pool for LLM clients, databases, etc.
    """

    def __init__(
        self,
        name: str,
        factory: Callable[..., Any],  # TODO(TYPE): replace Any with concrete type
        min_size: int = 2,
        max_size: int = 10,
        max_idle_seconds: int = 300,
    ) -> None:
        self.name = name
        self.factory = factory
        self.min_size = min_size
        self.max_size = max_size
        self.max_idle = timedelta(seconds=max_idle_seconds)

        # TODO(TYPE): replace Any with concrete type
        self._pool: asyncio.Queue[Any] = (
            asyncio.Queue(  # TODO(TYPE): replace Any with concrete type
                maxsize=max_size
            )
        )  # TODO(TYPE): replace Any with concrete type
        self._in_use: set[int] = set()
        self._lock = asyncio.Lock()
        self._initialized = False

        logger.info(f"Initialized AsyncConnectionPool '{name}' (min={min_size}, max={max_size})")

    async def initialize(self) -> None:
        """Pre-populate pool with minimum connections."""
        if self._initialized:
            return

        for _ in range(self.min_size):
            try:
                conn = await self.factory()
                await self._pool.put(conn)
            except Exception as e:
                logger.warning(f"Failed to create initial connection: {e}")

        self._initialized = True
        logger.info(
            f"Connection pool '{self.name}' initialized with {self._pool.qsize()} connections"
        )

    async def acquire(self) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Acquire connection from pool."""
        ACTIVE_WORKERS.inc()

        try:
            # Try to get from pool (non-blocking)
            try:
                conn = self._pool.get_nowait()
                self._in_use.add(id(conn))
                return conn
            except asyncio.QueueEmpty:
                pass

            # Create new if under max_size
            async with self._lock:
                if len(self._in_use) < self.max_size:
                    conn = await self.factory()
                    self._in_use.add(id(conn))
                    return conn

            # Wait for available connection
            conn = await self._pool.get()
            self._in_use.add(id(conn))
            return conn

        except Exception as e:
            ACTIVE_WORKERS.dec()
            raise

    async def release(self, conn: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        """Release connection back to pool."""
        ACTIVE_WORKERS.dec()
        self._in_use.discard(id(conn))

        try:
            # Try to return to pool (non-blocking)
            self._pool.put_nowait(conn)
        except asyncio.QueueFull:
            # Pool is full, close connection
            await self._close_connection(conn)

    async def _close_connection(
        self,
        conn: Any,  # TODO(TYPE): replace Any with concrete type
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        """Close a connection."""
        if hasattr(conn, "close"):
            if asyncio.iscoroutinefunction(conn.close):
                await conn.close()
            else:
                conn.close()

    async def close(self) -> None:
        """Close all connections in pool."""
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                await self._close_connection(conn)
            except Exception as e:
                logger.warning(f"Error closing connection: {e}")


class ParallelExecutor:
    """
    Execute tasks in parallel with rate limiting and backpressure.
    """

    def __init__(
        self,
        max_concurrent: int = 10,
        max_workers: int = 4,
        rate_limit_per_second: float | None = None,
    ) -> None:
        self.max_concurrent = max_concurrent
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.rate_limit = rate_limit_per_second
        self.last_request_time: float | None = None

        # Thread pool for CPU-bound tasks
        self.thread_pool = ThreadPoolExecutor(max_workers=max_workers)

        logger.info(
            f"Initialized ParallelExecutor (max_concurrent={max_concurrent}, "
            f"max_workers={max_workers})"
        )

    async def execute(
        self,
        tasks: list[
            # TODO(TYPE): replace Any with concrete type
            Callable[..., Coroutine[Any, Any, T]]
        ],  # TODO(TYPE): replace Any with concrete type
        *args: Any,
        **kwargs: Any,  # TODO(TYPE): replace with concrete type
    ) -> list[Any]:  # TODO(TYPE): replace Any with concrete type
        """Execute multiple coroutines in parallel with rate limiting."""

        async def _execute_single(
            task_fn: Callable[
                # TODO(TYPE): replace Any with concrete type
                ..., Coroutine[Any, Any, T]
            ],  # TODO(TYPE): replace Any with concrete type
        ) -> Any:  # TODO(TYPE): replace Any with concrete type
            async with self.semaphore:
                # Rate limiting
                if self.rate_limit:
                    await self._apply_rate_limit()

                return await task_fn(*args, **kwargs)

        # Create all tasks
        coroutines = [_execute_single(task) for task in tasks]

        # Execute with gather
        results: list[Any] = list(  # TODO(TYPE): replace Any with concrete type
            await asyncio.gather(*coroutines, return_exceptions=True)
        )  # TODO(TYPE): replace Any with concrete type
        return results

    async def execute_with_results(
        self,
        tasks: dict[
            str, Callable[..., Coroutine[Any, Any, T]]  # TODO(TYPE): replace Any with concrete type
        ],  # TODO(TYPE): replace Any with concrete type
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, T | Exception]:
        """Execute named tasks and return results with names."""

        async def _execute_named(
            name: str,
            task_fn: Callable[
                ..., Coroutine[Any, Any, T]  # TODO(TYPE): replace Any with concrete type
            ],  # TODO(TYPE): replace Any with concrete type
        ) -> tuple[str, Any]:  # TODO(TYPE): replace Any with concrete type
            async with self.semaphore:
                if self.rate_limit:
                    await self._apply_rate_limit()

                try:
                    result = await task_fn(*args, **kwargs)
                    return (name, result)
                except Exception as e:
                    return (name, e)

        coroutines = [_execute_named(name, task) for name, task in tasks.items()]
        results = await asyncio.gather(*coroutines)

        return dict(results)

    async def _apply_rate_limit(self) -> None:
        """Apply rate limiting between requests."""
        if not self.rate_limit or not self.last_request_time:
            self.last_request_time = time.time()
            return

        min_interval = 1.0 / self.rate_limit
        elapsed = time.time() - self.last_request_time

        if elapsed < min_interval:
            await asyncio.sleep(min_interval - elapsed)

        self.last_request_time = time.time()

    def run_in_thread(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> "asyncio.Future[T]":
        """Run CPU-bound function in thread pool."""
        loop = asyncio.get_event_loop()
        return loop.run_in_executor(self.thread_pool, functools.partial(fn, *args, **kwargs))

    def shutdown(self) -> None:
        """Shutdown thread pool."""
        self.thread_pool.shutdown(wait=True)


# Decorator for caching


def cached(
    cache_name: str,
    key_fn: Callable[..., str] | None = None,
    ttl_seconds: int = 300,
    max_size: int = 1000,
) -> Callable[..., Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Decorator to cache function results.

    Usage:
        @cached("agent_results", key_fn=lambda self, task: task.id)
        async def process_task(self, task):
            return await expensive_operation(task)
    """
    cache: LRUCache[Any] = LRUCache(  # TODO(TYPE): replace Any with concrete type
        name=cache_name, max_size=max_size, max_age_seconds=ttl_seconds
    )  # TODO(TYPE): replace Any with concrete type

    def decorator(
        fn: Callable[..., Coroutine[Any, Any, T]],  # TODO(TYPE): replace Any with concrete type
    ) -> Callable[..., Coroutine[Any, Any, T]]:  # TODO(TYPE): replace Any with concrete type
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            # Generate cache key
            if key_fn:
                cache_key = key_fn(*args, **kwargs)
            else:
                # Default: hash of args + kwargs
                key_data = str(args) + str(sorted(kwargs.items()))
                cache_key = hashlib.sha256(key_data.encode()).hexdigest()

            # Try cache
            cached_value = await cache.get(cache_key)
            if cached_value is not None:
                logger.debug(f"Cache hit for {fn.__name__}: {cache_key}")
                return cached_value  # type: ignore[no-any-return]  # NOTE: LRUCache[Any].get() returns Any, always T here

            # Execute and cache
            result = await fn(*args, **kwargs)
            await cache.set(cache_key, result)

            return result

        # Attach cache for external access
        cast(Any, wrapper).cache = cache  # TODO(TYPE): replace Any with concrete type
        return wrapper

    return decorator


def timed(metric_name: str) -> Callable[..., Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Decorator to time function execution.

    Usage:
        @timed("agent_process_task")
        async def process_task(self, task):
            return await do_work(task)
    """

    def decorator(
        fn: Callable[..., Coroutine[Any, Any, T]],  # TODO(TYPE): replace Any with concrete type
    ) -> Callable[..., Coroutine[Any, Any, T]]:  # TODO(TYPE): replace Any with concrete type
        @functools.wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            start = time.time()
            try:
                return await fn(*args, **kwargs)
            finally:
                elapsed = time.time() - start
                EXECUTION_TIME.labels(agent_type=metric_name).observe(elapsed)

        return wrapper

    return decorator


# Global instances
_cache_instances: dict[str, LRUCache[Any]] = {}  # TODO(TYPE): replace Any with concrete type
_pool_instances: dict[str, AsyncConnectionPool] = {}
_executor_instance: ParallelExecutor | None = None


def get_cache(name: str, **kwargs: Any) -> LRUCache[Any]:  # TODO(TYPE): replace with concrete type
    """Get or create named cache instance."""
    if name not in _cache_instances:
        _cache_instances[name] = LRUCache(name=name, **kwargs)
    return _cache_instances[name]


def get_executor(max_concurrent: int = 10) -> ParallelExecutor:
    """Get global parallel executor."""
    global _executor_instance
    if _executor_instance is None:
        _executor_instance = ParallelExecutor(max_concurrent=max_concurrent)
    return _executor_instance


async def get_performance_stats() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get comprehensive performance statistics."""
    return {
        "caches": {name: cache.get_stats() for name, cache in _cache_instances.items()},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def clear_all_caches() -> int:
    """Clear all caches and return total cleared entries."""
    total = 0
    for cache in _cache_instances.values():
        total += len(cache._cache)
        await cache.clear()
    return total
