"""
Canvas Execution Service - Manages async execution of agent blocks.

Provides:
- Task queue for background execution
- Real-time streaming via WebSocket
- Execution history and logs
- Resource limits and timeouts
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set
from collections.abc import Callable
from uuid import UUID, uuid4

from loguru import logger

from src.domains.canvas.agent_blocks import (
    AgentBlock,
    AgentBlockConfig,
    AgentBlockRegistry,
    AgentBlockType,
    ExecutionResult,
    ExecutionStatus,
    StreamChunk,
    agent_block_registry,
)


@dataclass
class ExecutionTask:
    """A pending or active execution task."""

    task_id: UUID
    block_id: UUID
    canvas_id: UUID
    user_id: UUID
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    status: ExecutionStatus = ExecutionStatus.PENDING
    result: ExecutionResult | None = None

    # Callbacks for status changes
    _on_complete: list[Callable[..., Any]] = field(default_factory=list)  # TODO(TYPE): replace Any with concrete type
    _on_stream: list[Callable[..., Any]] = field(default_factory=list)  # TODO(TYPE): replace Any with concrete type
    _unsubscribe: Callable[..., Any] | None = None  # TODO(TYPE): replace Any with concrete type


class ExecutionQueue:
    """
    Priority queue for execution tasks.

    Manages concurrent execution limits and task prioritization.
    """

    def __init__(
        self,
        max_concurrent: int = 5,
        default_timeout: int = 300,
    ) -> None:
        self.max_concurrent = max_concurrent
        self.default_timeout = default_timeout

        self._queue: asyncio.Queue[ExecutionTask] = asyncio.Queue()
        self._running: dict[UUID, asyncio.Task[Any]] = {}  # task_id -> asyncio.Task  # TODO(TYPE): replace Any with concrete type
        self._completed: dict[UUID, ExecutionTask] = {}
        self._semaphore = asyncio.Semaphore(max_concurrent)

        self._running_flag = False
        self._worker_task: asyncio.Task[Any] | None = None  # TODO(TYPE): replace Any with concrete type

        logger.info(f"ExecutionQueue initialized (max_concurrent={max_concurrent})")

    async def start(self) -> None:
        """Start the queue processor."""
        if self._running_flag:
            return

        self._running_flag = True
        self._worker_task = asyncio.create_task(self._process_queue())
        logger.info("ExecutionQueue started")

    async def stop(self) -> None:
        """Stop the queue processor."""
        if not self._running_flag:
            return

        self._running_flag = False

        # Cancel all running tasks
        for task in self._running.values():
            task.cancel()

        # Wait for worker to finish
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

        logger.info("ExecutionQueue stopped")

    async def submit(
        self,
        block: AgentBlock,
        user_id: UUID,
        priority: int = 0,
    ) -> ExecutionTask:
        """Submit a block for execution."""
        task = ExecutionTask(
            task_id=uuid4(),
            block_id=block.block_id,
            canvas_id=block.canvas_id,
            user_id=user_id,
        )

        # Subscribe to block's output for streaming
        def on_chunk(chunk: StreamChunk) -> None:
            for callback in task._on_stream:
                try:
                    callback(chunk)
                except Exception as e:
                    logger.error(f"Stream callback error: {e}")

        block.subscribe(on_chunk)

        # Store reference to unsubscribe later
        task._unsubscribe = lambda: block.unsubscribe(on_chunk)

        await self._queue.put(task)
        logger.debug(f"Submitted task {task.task_id} for block {block.block_id}")

        return task

    def get_task(self, task_id: UUID) -> ExecutionTask | None:
        """Get task by ID."""
        # Check running tasks
        for running_task in self._running.values():
            # Note: This is a simplification, in production we'd track task IDs
            pass

        # Check completed
        return self._completed.get(task_id)

    def get_canvas_tasks(self, canvas_id: UUID) -> list[ExecutionTask]:
        """Get all tasks for a canvas."""
        tasks: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Check completed
        for task in self._completed.values():
            if task.canvas_id == canvas_id:
                tasks.append(task)

        return tasks

    async def cancel_task(self, task_id: UUID) -> bool:
        """Cancel a pending or running task."""
        # Check if running
        if task_id in self._running:
            self._running[task_id].cancel()
            return True

        # Note: Cancelling from queue would require tracking queue items
        return False

    async def _process_queue(self) -> None:
        """Main queue processing loop."""
        while self._running_flag:
            try:
                # Get next task with timeout
                task = await asyncio.wait_for(
                    self._queue.get(),
                    timeout=1.0,
                )

                # Process task with semaphore for concurrency control
                asyncio.create_task(self._execute_task(task))

            except TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Queue processing error: {e}")

    async def _execute_task(self, exec_task: ExecutionTask) -> None:
        """Execute a single task."""
        async with self._semaphore:
            exec_task.started_at = datetime.now(timezone.utc)
            exec_task.status = ExecutionStatus.RUNNING

            block = agent_block_registry.get(exec_task.block_id)
            if not block:
                exec_task.status = ExecutionStatus.FAILED
                exec_task.result = ExecutionResult(
                    status=ExecutionStatus.FAILED,
                    error="Block not found",
                )
                return

            # Create asyncio task for execution
            async def run_execution() -> None:
                try:
                    result = await asyncio.wait_for(
                        block.execute(),
                        timeout=self.default_timeout,
                    )
                    exec_task.result = result
                    exec_task.status = result.status
                except TimeoutError:
                    exec_task.status = ExecutionStatus.TIMEOUT
                    exec_task.result = ExecutionResult(
                        status=ExecutionStatus.TIMEOUT,
                        error=f"Execution timed out after {self.default_timeout}s",
                    )
                except Exception as e:
                    logger.exception(f"Task execution error: {e}")
                    exec_task.status = ExecutionStatus.FAILED
                    exec_task.result = ExecutionResult(
                        status=ExecutionStatus.FAILED,
                        error=str(e),
                    )
                finally:
                    # Unsubscribe from block
                    if exec_task._unsubscribe is not None:
                        exec_task._unsubscribe()

            task = asyncio.create_task(run_execution())
            self._running[exec_task.task_id] = task

            try:
                await task
            except asyncio.CancelledError:
                exec_task.status = ExecutionStatus.CANCELLED
                exec_task.result = ExecutionResult(
                    status=ExecutionStatus.CANCELLED,
                    error="Execution cancelled",
                )
            finally:
                del self._running[exec_task.task_id]
                exec_task.completed_at = datetime.now(timezone.utc)
                self._completed[exec_task.task_id] = exec_task

                # Notify callbacks
                if exec_task.result:
                    for callback in exec_task._on_complete:
                        try:
                            callback(exec_task.result)
                        except Exception as e:
                            logger.error(f"Complete callback error: {e}")

                logger.debug(f"Task {exec_task.task_id} completed with status {exec_task.status}")


class ExecutionHistory:
    """
    Persistent storage for execution history.

    Maintains logs of all executions for audit and replay.
    """

    def __init__(self, max_entries_per_block: int = 100) -> None:
        self.max_entries = max_entries_per_block
        self._history: dict[UUID, list[ExecutionResult]] = {}

    def record(
        self,
        block_id: UUID,
        result: ExecutionResult,
    ) -> None:
        """Record an execution result."""
        if block_id not in self._history:
            self._history[block_id] = []

        self._history[block_id].append(result)

        # Trim old entries
        if len(self._history[block_id]) > self.max_entries:
            self._history[block_id] = self._history[block_id][-self.max_entries :]

    def get_history(
        self,
        block_id: UUID,
        limit: int = 10,
    ) -> list[ExecutionResult]:
        """Get execution history for a block."""
        history = self._history.get(block_id, [])
        return history[-limit:] if limit else history

    def get_latest(self, block_id: UUID) -> ExecutionResult | None:
        """Get latest execution result for a block."""
        history = self._history.get(block_id, [])
        return history[-1] if history else None


class StreamingManager:
    """
    Manages WebSocket streaming for real-time execution output.

    Handles subscriptions and broadcasts for multiple clients.
    """

    def __init__(self) -> None:
        # canvas_id -> {websocket: {block_ids: set}}
        self._subscribers: dict[UUID, dict[Any, set[UUID]]] = {}  # TODO(TYPE): replace Any with concrete type

    def subscribe(
        self,
        canvas_id: UUID,
        websocket: Any,  # FastAPI WebSocket  # TODO(TYPE): replace Any with concrete type
        block_ids: set[UUID] | None = None,
    ) -> None:
        """Subscribe a WebSocket to streaming updates."""
        if canvas_id not in self._subscribers:
            self._subscribers[canvas_id] = {}

        self._subscribers[canvas_id][websocket] = block_ids or set()
        logger.debug(f"WebSocket subscribed to canvas {canvas_id}")

    def unsubscribe(
        self,
        canvas_id: UUID,
        websocket: Any,  # TODO(TYPE): replace Any with concrete type
    ) -> None:
        """Unsubscribe a WebSocket."""
        if canvas_id in self._subscribers:
            self._subscribers[canvas_id].pop(websocket, None)

    async def broadcast(
        self,
        canvas_id: UUID,
        block_id: UUID,
        chunk: StreamChunk,
    ) -> None:
        """Broadcast a chunk to subscribed WebSockets."""
        if canvas_id not in self._subscribers:
            return

        message = {
            "type": "execution_stream",
            "block_id": str(block_id),
            "chunk": chunk.to_dict(),
        }

        # Send to all subscribers interested in this block
        for websocket, block_ids in self._subscribers[canvas_id].items():
            if not block_ids or block_id in block_ids:
                try:
                    await websocket.send_json(message)
                except Exception as e:
                    logger.error(f"WebSocket send error: {e}")

    def create_block_stream_callback(
        self,
        canvas_id: UUID,
        block_id: UUID,
    ) -> Callable[..., Any]:  # TODO(TYPE): replace Any with concrete type
        """Create a callback that broadcasts to WebSockets."""

        async def callback(chunk: StreamChunk) -> None:
            await self.broadcast(canvas_id, block_id, chunk)

        # Return sync wrapper for AgentBlock compatibility
        def sync_callback(chunk: StreamChunk) -> None:
            asyncio.create_task(callback(chunk))

        return sync_callback


# Global service instances
execution_queue = ExecutionQueue()
execution_history = ExecutionHistory()
streaming_manager = StreamingManager()


class ExecutionService:
    """
    High-level service for managing agent block execution.

    Combines queue, history, and streaming into unified interface.
    """

    def __init__(self) -> None:
        self.queue = execution_queue
        self.history = execution_history
        self.streaming = streaming_manager
        self.registry = agent_block_registry

    async def start(self) -> None:
        """Start the execution service."""
        await self.queue.start()
        logger.info("ExecutionService started")

    async def stop(self) -> None:
        """Stop the execution service."""
        await self.queue.stop()
        logger.info("ExecutionService stopped")

    async def execute_block(
        self,
        block_id: UUID,
        user_id: UUID,
        stream_callback: Callable[..., Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> ExecutionTask:
        """
        Execute an agent block.

        Args:
            block_id: ID of block to execute
            user_id: ID of user triggering execution
            stream_callback: Optional callback for streaming output

        Returns:
            ExecutionTask with task ID for tracking
        """
        block = self.registry.get(block_id)
        if not block:
            raise ValueError(f"Block {block_id} not found")

        # Submit to queue
        task = await self.queue.submit(block, user_id)

        # Add streaming callback if provided
        if stream_callback:
            task._on_stream.append(stream_callback)

        # Record in history on completion
        def on_complete(result: ExecutionResult) -> None:
            self.history.record(block_id, result)

        task._on_complete.append(on_complete)

        return task

    async def execute_canvas_blocks(
        self,
        canvas_id: UUID,
        user_id: UUID,
        block_type: AgentBlockType | None = None,
    ) -> list[ExecutionTask]:
        """Execute all blocks in a canvas."""
        blocks = self.registry.get_canvas_blocks(canvas_id)

        if block_type:
            blocks = [b for b in blocks if b.block_type == block_type]

        tasks: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for block in blocks:
            task = await self.execute_block(block.block_id, user_id)
            tasks.append(task)

        return tasks

    def get_block_status(self, block_id: UUID) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get current status of a block."""
        block = self.registry.get(block_id)
        if not block:
            return {"error": "Block not found"}

        return {
            "block_id": str(block_id),
            "status": block.status.value,
            "result": block.result.to_dict() if block.result else None,
            "history": [r.to_dict() for r in self.history.get_history(block_id)],
        }


# Global service instance
execution_service = ExecutionService()
