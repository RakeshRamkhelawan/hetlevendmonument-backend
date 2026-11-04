"""
SC-5.1: Background Task Manager
Manages async background tasks with tracking and retry capabilities.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from functools import wraps
from typing import Any, Optional, cast
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"


@dataclass
class BackgroundTask:
    """Represents a background task."""

    id: str
    name: str
    status: TaskStatus = TaskStatus.PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: Any = None
    error: str | None = None
    retry_count: int = 0
    max_retries: int = 3
    metadata: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type


class BackgroundTaskManager:
    """
    SC-5.1: Manages background tasks with tracking and retry support.

    Features:
    - Task tracking and status monitoring
    - Automatic retries with exponential backoff
    - Task cancellation
    - Result storage
    """

    def __init__(self, max_concurrent: int = 10) -> None:
        self.tasks: dict[str, BackgroundTask] = {}
        self.running_tasks: dict[str, asyncio.Task[Any]] = {}  # TODO(TYPE): replace Any with concrete type
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self._cleanup_interval = 3600  # 1 hour

    async def submit(
        self,
        func: Callable[..., Any],  # TODO(TYPE): replace Any with concrete type
        *args: Any,
        name: str | None = None,
        max_retries: int = 3,
        metadata: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        **kwargs: Any,
    ) -> str:
        """
        Submit a background task for execution.

        Args:
            func: Async function to execute
            name: Task name for identification
            max_retries: Maximum retry attempts
            metadata: Additional metadata to store

        Returns:
            Task ID
        """
        task_id = str(uuid.uuid4())
        task_name = name or cast(Any, func).__name__  # TODO(TYPE): replace Any with concrete type

        task = BackgroundTask(
            id=task_id, name=task_name, max_retries=max_retries, metadata=metadata or {}
        )
        self.tasks[task_id] = task

        # Start the task
        async_task = asyncio.create_task(self._run_task(task, func, *args, **kwargs))
        self.running_tasks[task_id] = async_task

        logger.info(f"Submitted background task: {task_name} ({task_id})")
        return task_id

    async def _run_task(
        self, task: BackgroundTask, func: Callable[..., Any], *args: Any, **kwargs: Any
    ) -> None:
        """Execute a task with retry logic."""
        async with self.semaphore:
            task.status = TaskStatus.RUNNING
            task.started_at = datetime.now(timezone.utc)

            while task.retry_count <= task.max_retries:
                try:
                    if asyncio.iscoroutinefunction(func):
                        result = await func(*args, **kwargs)
                    else:
                        result = await asyncio.to_thread(func, *args, **kwargs)

                    task.status = TaskStatus.COMPLETED
                    task.result = result
                    task.completed_at = datetime.now(timezone.utc)

                    logger.info(f"Task completed: {task.name} ({task.id})")
                    break

                except asyncio.CancelledError:
                    task.status = TaskStatus.CANCELLED
                    logger.info(f"Task cancelled: {task.name} ({task.id})")
                    raise

                except Exception as e:
                    task.retry_count += 1
                    task.error = str(e)

                    if task.retry_count <= task.max_retries:
                        task.status = TaskStatus.RETRYING
                        backoff = 2**task.retry_count
                        logger.warning(
                            f"Task failed, retrying in {backoff}s: {task.name} "
                            f"(attempt {task.retry_count}/{task.max_retries})"
                        )
                        await asyncio.sleep(backoff)
                    else:
                        task.status = TaskStatus.FAILED
                        task.completed_at = datetime.now(timezone.utc)
                        logger.error(f"Task failed permanently: {task.name} - {e}")

            # Cleanup running task reference
            self.running_tasks.pop(task.id, None)

    def get_task(self, task_id: str) -> BackgroundTask | None:
        """Get task by ID."""
        return self.tasks.get(task_id)

    def get_task_status(self, task_id: str) -> TaskStatus | None:
        """Get task status by ID."""
        task = self.tasks.get(task_id)
        return task.status if task else None

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a running task."""
        if task_id in self.running_tasks:
            self.running_tasks[task_id].cancel()
            return True
        return False

    def list_tasks(
        self, status: TaskStatus | None = None, limit: int = 100
    ) -> list[BackgroundTask]:
        """List tasks, optionally filtered by status."""
        tasks = list(self.tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        return sorted(tasks, key=lambda t: t.created_at, reverse=True)[:limit]

    def get_stats(self) -> dict[str, int]:
        """Get task statistics."""
        stats = {status.value: 0 for status in TaskStatus}
        for task in self.tasks.values():
            stats[task.status.value] += 1
        stats["total"] = len(self.tasks)
        return stats


# Singleton instance
task_manager = BackgroundTaskManager()


def background_task(
    name: str | None = None, max_retries: int = 3
) -> Callable[[Callable[..., Any]], Callable[..., Awaitable[str]]]:  # TODO(TYPE): replace Any with concrete type
    """
    Decorator to run a function as a background task.

    Usage:
        @background_task(name="send_email", max_retries=5)
        async def send_email(to: str, subject: str):
            ...
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Awaitable[str]]:  # TODO(TYPE): replace Any with concrete type
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> str:
            return await task_manager.submit(
                func,
                *args,
                name=name or cast(Any, func).__name__,  # TODO(TYPE): replace Any with concrete type
                max_retries=max_retries,
                **kwargs,
            )

        return wrapper

    return decorator
