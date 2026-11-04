"""
AsyncIO optimizations for reducing context switches and improving performance.

Provides:
- Zero-copy data structures
- Lock-free algorithms where possible
- Optimized event loop configuration
- Batch processing utilities
"""

import asyncio
import collections
import functools
import logging
import os
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import (
    Any,  # TODO(TYPE): replace Any with concrete type
    Deque,
    Dict,
    Generic,
    List,
    Optional,
    Set,
    TypeVar,
    cast,
)
from collections.abc import Awaitable, Callable, Coroutine

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Context variables for request tracking
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")
tenant_id_ctx: ContextVar[int] = ContextVar("tenant_id", default=0)


class ZeroCopyBuffer(Generic[T]):
    """
    Lock-free ring buffer for high-throughput scenarios.

    Uses pre-allocated circular buffer to avoid memory allocation
    during hot paths.
    """

    def __init__(self, size: int = 1024) -> None:
        self.size = size
        self._buffer: list[T | None] = [None] * size
        self._read_idx = 0
        self._write_idx = 0
        self._lock = asyncio.Lock()

    async def put(self, item: T) -> bool:
        """Add item to buffer. Returns False if full."""
        async with self._lock:
            next_write = (self._write_idx + 1) % self.size
            if next_write == self._read_idx:
                return False  # Buffer full

            self._buffer[self._write_idx] = item
            self._write_idx = next_write
            return True

    async def get(self) -> T | None:
        """Get item from buffer. Returns None if empty."""
        async with self._lock:
            if self._read_idx == self._write_idx:
                return None  # Buffer empty

            item = self._buffer[self._read_idx]
            self._buffer[self._read_idx] = None  # Help GC
            self._read_idx = (self._read_idx + 1) % self.size
            return item

    def is_empty(self) -> bool:
        """Check if buffer is empty (not thread-safe, for stats only)."""
        return self._read_idx == self._write_idx

    def is_full(self) -> bool:
        """Check if buffer is full (not thread-safe, for stats only)."""
        return (self._write_idx + 1) % self.size == self._read_idx


class Batcher(Generic[T]):
    """
    Batches items for efficient processing.

    Reduces context switches by processing multiple items
    in a single batch instead of one-by-one.
    """

    def __init__(
        self,
        processor: Callable[..., Any],  # TODO(TYPE): replace Any with concrete type
        max_batch_size: int = 100,
        max_wait_ms: float = 10.0,
    ) -> None:
        self.processor = processor
        self.max_batch_size = max_batch_size
        self.max_wait_seconds = max_wait_ms / 1000

        self._buffer: Deque[T] = collections.deque()
        self._lock = asyncio.Lock()
        self._flush_event = asyncio.Event()
        self._task: asyncio.Task[Any] | None = None  # TODO(TYPE): replace Any with concrete type
        self._running = False

        # Metrics
        self._batches_processed = 0
        self._items_processed = 0
        self._total_wait_time = 0.0

    async def start(self) -> None:
        """Start the batch processor."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._process_loop())
        logger.info(
            f"Batcher started (max_size={self.max_batch_size}, max_wait={self.max_wait_seconds}s)"
        )

    async def stop(self) -> None:
        """Stop the batch processor and flush remaining items."""
        if not self._running:
            return

        self._running = False
        self._flush_event.set()

        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5.0)
            except TimeoutError:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass

        # Final flush
        await self._flush()
        logger.info(
            f"Batcher stopped. Processed {self._items_processed} items in {self._batches_processed} batches"
        )

    async def add(self, item: T) -> None:
        """Add item to batch."""
        async with self._lock:
            self._buffer.append(item)

            if len(self._buffer) >= self.max_batch_size:
                self._flush_event.set()

    async def _process_loop(self) -> None:
        """Main processing loop."""
        while self._running:
            try:
                # Wait for items or timeout
                wait_start = time.time()
                await asyncio.wait_for(self._flush_event.wait(), timeout=self.max_wait_seconds)
                wait_time = time.time() - wait_start
                self._total_wait_time += wait_time

                await self._flush()
                self._flush_event.clear()

            except TimeoutError:
                # Timeout, flush what we have
                await self._flush()

    async def _flush(self) -> None:
        """Process current batch."""
        async with self._lock:
            if not self._buffer:
                return

            # Take batch
            batch_size = min(len(self._buffer), self.max_batch_size)
            batch = [self._buffer.popleft() for _ in range(batch_size)]

        # Process outside lock
        if batch:
            try:
                await self.processor(batch)
                self._batches_processed += 1
                self._items_processed += len(batch)
            except Exception as e:
                logger.error(f"Batch processing error: {e}")

    def get_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get batcher statistics."""
        avg_batch_size = (
            self._items_processed / self._batches_processed if self._batches_processed > 0 else 0
        )
        avg_wait_time = (
            self._total_wait_time / self._batches_processed if self._batches_processed > 0 else 0
        )

        return {
            "running": self._running,
            "buffer_size": len(self._buffer),
            "batches_processed": self._batches_processed,
            "items_processed": self._items_processed,
            "avg_batch_size": round(avg_batch_size, 2),
            "avg_wait_time_ms": round(avg_wait_time * 1000, 2),
        }


class AsyncLazyLoader(Generic[T]):
    """
    Lazy loader that defers expensive initialization until first access.

    Reduces startup time by loading resources on-demand.
    """

    def __init__(self, factory: Callable[..., Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        self.factory = factory
        self._instance: T | None = None
        self._lock = asyncio.Lock()
        self._loading = False

    async def get(self) -> T:
        """Get instance, initializing if necessary."""
        if self._instance is not None:
            return self._instance

        async with self._lock:
            if self._instance is not None:
                return self._instance

            if self._loading:
                # Wait for loading to complete
                while self._loading:
                    await asyncio.sleep(0.001)
                if self._instance is None:
                    raise RuntimeError(
                        "AsyncLazyLoader: factory produced no instance after loading"
                    )
                return self._instance

            self._loading = True
            try:
                self._instance = await self.factory()
                if self._instance is None:
                    raise RuntimeError("AsyncLazyLoader: factory returned None")
                return self._instance
            finally:
                self._loading = False

    def is_loaded(self) -> bool:
        """Check if instance is loaded."""
        return self._instance is not None

    async def reset(self) -> None:
        """Reset loader, forcing re-initialization on next access."""
        async with self._lock:
            self._instance = None


class CoalescingDebouncer:
    """
    Debouncer that coalesces rapid calls into single execution.

    Useful for scenarios like:
    - Cache invalidation (wait for burst to end)
    - Config reload (don't reload on every change)
    - Bulk indexing (batch rapid updates)
    """

    def __init__(
        self,
        callback: Callable[..., Any],  # TODO(TYPE): replace Any with concrete type
        delay_seconds: float = 1.0,
        max_delay_seconds: float = 5.0,
    ) -> None:
        self.callback = callback
        self.delay_seconds = delay_seconds
        self.max_delay_seconds = max_delay_seconds

        self._timer: asyncio.Task[Any] | None = None  # TODO(TYPE): replace Any with concrete type
        self._first_call_time: float | None = None
        self._lock = asyncio.Lock()

    async def trigger(self) -> None:
        """Trigger debounced execution."""
        async with self._lock:
            now = time.time()

            if self._first_call_time is None:
                self._first_call_time = now

            # Cancel existing timer
            if self._timer and not self._timer.done():
                self._timer.cancel()
                try:
                    await self._timer
                except asyncio.CancelledError:
                    pass

            # Check max delay
            elapsed = now - self._first_call_time
            if elapsed >= self.max_delay_seconds:
                # Execute immediately, don't wait anymore
                await self._execute()
                return

            # Schedule new timer
            self._timer = asyncio.create_task(self._execute_after_delay())

    async def _execute_after_delay(self) -> None:
        """Execute callback after delay."""
        await asyncio.sleep(self.delay_seconds)
        await self._execute()

    async def _execute(self) -> None:
        """Execute callback and reset state."""
        async with self._lock:
            self._first_call_time = None
            self._timer = None

        try:
            await self.callback()
        except Exception as e:
            logger.error(f"Debounced callback error: {e}")

    async def flush(self) -> None:
        """Execute immediately if pending."""
        async with self._lock:
            if self._timer and not self._timer.done():
                self._timer.cancel()
                try:
                    await self._timer
                except asyncio.CancelledError:
                    pass
                await self._execute()


def configure_event_loop() -> None:
    """
    Configure event loop for optimal performance.

    Should be called once at application startup.
    """
    try:
        import uvloop

        asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
        logger.info("Using uvloop for better performance")
    except ImportError:
        logger.info("uvloop not available, using default asyncio")

    # Get current loop and configure
    loop = asyncio.get_event_loop()

    # Set debug mode based on environment
    # loop.set_debug(False)  # Disable in production for better performance

    # Optimize executor (for CPU-bound tasks)
    import concurrent.futures

    executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=min(32, (os.cpu_count() or 1) + 4), thread_name_prefix="asyncio_worker_"
    )
    loop.set_default_executor(executor)

    logger.info("Event loop configured for optimal performance")


def optimized_gather(
    *coros: Coroutine[Any, Any, T],  # TODO(TYPE): replace Any with concrete type
    limit: int | None = None,
    return_exceptions: bool = False,
) -> Awaitable[list[T]]:
    """
    Optimized asyncio.gather with concurrency limiting.

    Prevents resource exhaustion when gathering many coroutines.
    """
    if limit is None or len(coros) <= limit:
        return cast(Awaitable[list[T]], asyncio.gather(*coros, return_exceptions=return_exceptions))

    async def _limited_gather() -> list[T]:
        semaphore = asyncio.Semaphore(limit)

        async def _run_with_limit(coro: Coroutine[Any, Any, T]) -> T:  # TODO(TYPE): replace Any with concrete type
            async with semaphore:
                return await coro

        gathered: list[T] = cast(
            list[T],
            await asyncio.gather(
                *(_run_with_limit(c) for c in coros), return_exceptions=return_exceptions
            ),
        )
        return gathered

    return _limited_gather()


class TaskGroup:
    """
    Manages a group of related tasks with automatic cleanup.

    Ensures all tasks are properly cancelled on exit.
    """

    def __init__(self, name: str = "task_group") -> None:
        self.name = name
        self._tasks: set[asyncio.Task[Any]] = set()  # TODO(TYPE): replace Any with concrete type
        self._lock = asyncio.Lock()

    async def spawn(self, coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:  # TODO(TYPE): replace Any with concrete type
        """Spawn a new task in the group."""
        task = asyncio.create_task(coro)

        async with self._lock:
            self._tasks.add(task)

        # Auto-remove on completion
        task.add_done_callback(lambda t: asyncio.create_task(self._remove(t)))

        return task

    async def _remove(self, task: asyncio.Task[Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        """Remove completed task from group."""
        async with self._lock:
            self._tasks.discard(task)

    async def close(self, timeout: float = 5.0) -> None:
        """Cancel all tasks and wait for completion."""
        async with self._lock:
            tasks = list(self._tasks)

        if not tasks:
            return

        # Cancel all
        for task in tasks:
            if not task.done():
                task.cancel()

        # Wait with timeout
        try:
            await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=timeout)
        except TimeoutError:
            logger.warning(f"Timeout waiting for {len(tasks)} tasks to cancel")

        logger.info(f"TaskGroup '{self.name}' closed")

    def get_stats(self) -> dict[str, int]:
        """Get task group statistics."""
        return {
            "active_tasks": len(self._tasks),
            "completed_tasks": sum(1 for t in self._tasks if t.done()),
        }


def with_timeout(
    timeout_seconds: float,
    message: str | None = None,
) -> Callable[..., Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Decorator to add timeout to async functions.
    """

    def decorator(
        func: Callable[..., Coroutine[Any, Any, T]],  # TODO(TYPE): replace Any with concrete type
    ) -> Callable[..., Coroutine[Any, Any, T]]:  # TODO(TYPE): replace Any with concrete type
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            try:
                return await asyncio.wait_for(func(*args, **kwargs), timeout=timeout_seconds)
            except TimeoutError:
                raise TimeoutError(
                    message or f"{func.__name__} timed out after {timeout_seconds}s"
                )

        return wrapper

    return decorator


# Pre-warmed connection pools
class ConnectionPoolManager:
    """
    Manages pre-warmed connection pools for common resources.
    """

    _pools: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
    # Lazy, niet aangemaakt bij class-definitie (ADR-036 OP-16): `asyncio.Lock()` bindt zich
    # anders aan de loop van de import, en de kritieke secties hieronder bevatten `await`,
    # dus `threading.Lock` (het patroon dat critique_store.py kreeg) is hier niet veilig --
    # dat zou de loop blokkeren tijdens de await. `_get_lock()` maakt hem aan binnen de
    # draaiende loop bij eerste gebruik.
    _lock: asyncio.Lock | None = None

    @classmethod
    def _get_lock(cls) -> asyncio.Lock:
        if cls._lock is None:
            cls._lock = asyncio.Lock()
        return cls._lock

    @classmethod
    async def get_pool(cls, name: str, factory: Callable[..., Any]) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Get or create connection pool."""
        if name not in cls._pools:
            async with cls._get_lock():
                if name not in cls._pools:
                    cls._pools[name] = await factory()

        return cls._pools[name]

    @classmethod
    async def close_all(cls) -> None:
        """Close all managed pools."""
        async with cls._get_lock():
            for name, pool in cls._pools.items():
                try:
                    if hasattr(pool, "close"):
                        await pool.close()
                    elif hasattr(pool, "disconnect"):
                        await pool.disconnect()
                except Exception as e:
                    logger.warning(f"Error closing pool {name}: {e}")

            cls._pools.clear()
