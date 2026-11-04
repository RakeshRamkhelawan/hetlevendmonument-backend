"""
Engine Worker Manager
======================

This module provides a minimal Worker abstraction and three concrete
implementations for Async, Batch, and Realtime modes.

It is intentionally small and testable without external services.
The idea is to provide a stable interface that can later be wired to
Dramatiq, Redis, or realtime transports.

Usage:
    from src.core.engine.worker_manager import AsyncWorker
    worker = AsyncWorker(engine_factory=create_workflow_engine)
    await worker.start()
    await worker.submit("execution-id")
    await worker.stop()

"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Optional, cast
from collections.abc import Callable


logger = logging.getLogger(__name__)


@dataclass
class WorkerConfig:
    name: str = "worker"
    batch_size: int = 10
    batch_interval_seconds: int = 5
    timeout_seconds: int = 3600


class WorkerBase:
    """Base API for workers.

    Implementations must override:
    - start()
    - stop()
    - submit(*args, **kwargs)
    """

    def __init__(
        self,
        engine_factory: Callable[..., Any],  # TODO(TYPE): replace Any with concrete type
        config: WorkerConfig | None = None,
    ) -> None:
        self.engine_factory: Callable[..., Any] = engine_factory  # TODO(TYPE): replace Any with concrete type
        self.config: WorkerConfig = config or WorkerConfig()
        self._running: bool = False

    async def start(self) -> None:
        logger.info(f"Starting {self.config.name}")
        self._running = True

    async def stop(self) -> None:
        logger.info(f"Stopping {self.config.name}")
        self._running = False

    async def submit(self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError()


class AsyncWorker(WorkerBase):
    """A simple in-process async worker that runs jobs in an asyncio queue.

    This is a test-friendly implementation of an "async worker" without
    requiring Dramatiq or Redis.
    """

    def __init__(
        self,
        engine_factory: Callable[..., Any],  # TODO(TYPE): replace Any with concrete type
        config: WorkerConfig | None = None,
    ) -> None:
        super().__init__(engine_factory, config)
        self._queue: asyncio.Queue[Any] = asyncio.Queue()  # TODO(TYPE): replace Any with concrete type
        self._task: asyncio.Task[Any] | None = None  # TODO(TYPE): replace Any with concrete type

    async def start(self) -> None:
        await super().start()
        self._task = asyncio.create_task(self._worker_loop())

    async def stop(self) -> None:
        await super().stop()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def submit(self, execution_id: str) -> None:
        await self._queue.put(execution_id)

    async def _worker_loop(self) -> None:
        logger.info("AsyncWorker loop started")
        while self._running:
            try:
                execution_id = await self._queue.get()
                logger.debug(f"Processing {execution_id} from AsyncWorker queue")
                # For now, call engine factory with None session (in tests this is mocked)
                try:
                    engine = self.engine_factory(None)
                    # Execution method may be async
                    if asyncio.iscoroutinefunction(engine.execute_workflow):
                        await engine.execute_workflow(execution_id)
                    else:
                        engine.execute_workflow(execution_id)
                except Exception as e:
                    logger.error(f"AsyncWorker failed processing {execution_id}: {e}")
            except asyncio.CancelledError:
                logger.info("AsyncWorker loop cancelled")
                break


class BatchWorker(WorkerBase):
    """Worker that buffers execution requests and processes them in batches."""

    def __init__(
        self,
        engine_factory: Callable[..., Any],  # TODO(TYPE): replace Any with concrete type
        config: WorkerConfig | None = None,
    ) -> None:
        super().__init__(engine_factory, config)
        self._buffer: list[str] = []
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[Any] | None = None  # TODO(TYPE): replace Any with concrete type

    async def start(self) -> None:
        await super().start()
        self._task = asyncio.create_task(self._batch_loop())

    async def stop(self) -> None:
        await super().stop()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def submit(self, execution_id: str) -> None:
        async with self._lock:
            self._buffer.append(execution_id)
            if len(self._buffer) >= self.config.batch_size:
                await self._process_batch()

    async def _batch_loop(self) -> None:
        while self._running:
            await asyncio.sleep(self.config.batch_interval_seconds)
            async with self._lock:
                if self._buffer:
                    await self._process_batch()

    async def _process_batch(self) -> None:
        if not self._buffer:
            return
        batch = self._buffer.copy()
        self._buffer.clear()
        logger.info(f"Processing batch of size {len(batch)}: {batch}")
        try:
            engine = self.engine_factory(None)
            for execution_id in batch:
                if asyncio.iscoroutinefunction(engine.execute_workflow):
                    await engine.execute_workflow(execution_id)
                else:
                    engine.execute_workflow(execution_id)
        except Exception as e:
            logger.exception(f"BatchWorker failed processing batch: {e}")


class RealtimeWorker(WorkerBase):
    """Worker for real-time workloads (placeholder).

    The real-time implementation would integrate with WebSocket / gRPC / HTTP
    long-lived connections. For now, it's a simple pass-through that calls
    the engine synchronously and returns the result.
    """

    async def submit(self, execution_id: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        logger.debug(f"RealtimeWorker executing {execution_id}")
        engine = self.engine_factory(None)
        if asyncio.iscoroutinefunction(engine.execute_workflow):
            result = cast(dict[str, Any], await engine.execute_workflow(execution_id))  # TODO(TYPE): replace Any with concrete type
        else:
            result = cast(dict[str, Any], engine.execute_workflow(execution_id))  # TODO(TYPE): replace Any with concrete type
        return result


# Simple factory
def create_worker(
    mode: str,
    engine_factory: Callable[..., Any],  # TODO(TYPE): replace Any with concrete type
    config: WorkerConfig | None = None,
) -> WorkerBase:
    mode = mode.lower()
    if mode == "async":
        return AsyncWorker(engine_factory, config)
    if mode == "batch":
        return BatchWorker(engine_factory, config)
    if mode == "realtime":
        return RealtimeWorker(engine_factory, config)
    raise ValueError(f"Unknown worker mode: {mode}")
