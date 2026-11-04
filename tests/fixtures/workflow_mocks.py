"""
tests/fixtures/workflow_mocks.py - Workflow & Process Execution Mocks

Provides mock implementations for workflow execution, task management,
and process orchestration. Essential for testing complex multi-step operations
without external dependencies.

KEY PRINCIPLES:
1. Deterministic workflow execution (no randomness)
2. Configurable task outcomes and timing
3. Call tracking for assertions
4. Thread-safe and async-compatible
5. Production-like error scenarios

MOCKED COMPONENTS:
- Workflow execution engine
- Task scheduler and executor
- Process lifecycle management
- Execution history and state
- Error handling and recovery

Created: 2025-12-13
Version: 1.0 (P4.0.4)
"""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Callable, Coroutine, Dict, List, Optional, Set
from unittest.mock import AsyncMock, MagicMock

import pytest

# ============================================================================
# WORKFLOW STATE ENUMS
# ============================================================================


class WorkflowState(str, Enum):
    """Workflow execution state."""

    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class TaskState(str, Enum):
    """Individual task state."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    RETRYING = "retrying"


class TaskPriority(str, Enum):
    """Task priority for scheduling."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ============================================================================
# DATA CLASSES FOR WORKFLOW STATE
# ============================================================================


@dataclass
class TaskDefinition:
    """Definition of a task within a workflow."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    description: str = ""
    handler: Optional[Callable] = None  # Async function to execute
    timeout_seconds: int = 300
    max_retries: int = 0
    priority: TaskPriority = TaskPriority.MEDIUM
    dependencies: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskExecution:
    """Record of a task execution."""

    task_id: str
    state: TaskState
    output: Optional[Any] = None
    error: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    attempts: int = 0
    duration_ms: int = 0
    input_params: Dict[str, Any] = field(default_factory=dict)
    retry_count: int = 0

    def is_complete(self) -> bool:
        """Check if task is in terminal state."""
        return self.state in (TaskState.COMPLETED, TaskState.FAILED, TaskState.SKIPPED)

    def get_duration(self) -> float:
        """Get execution duration in seconds."""
        if not self.start_time or not self.end_time:
            return 0
        return (self.end_time - self.start_time).total_seconds()


@dataclass
class WorkflowExecution:
    """Record of a workflow execution."""

    workflow_id: str
    execution_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    state: WorkflowState = WorkflowState.PENDING
    tasks: Dict[str, TaskExecution] = field(default_factory=dict)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def get_duration(self) -> float:
        """Get workflow execution duration in seconds."""
        if not self.start_time or not self.end_time:
            return 0
        return (self.end_time - self.start_time).total_seconds()

    def get_task_count(self) -> int:
        """Get total task count."""
        return len(self.tasks)

    def get_completed_count(self) -> int:
        """Get completed task count."""
        return sum(1 for t in self.tasks.values() if t.state == TaskState.COMPLETED)

    def get_failed_count(self) -> int:
        """Get failed task count."""
        return sum(1 for t in self.tasks.values() if t.state == TaskState.FAILED)

    def success_rate(self) -> float:
        """Get success rate as percentage."""
        total = self.get_task_count()
        if total == 0:
            return 0
        completed = self.get_completed_count()
        return (completed / total) * 100


# ============================================================================
# MOCK WORKFLOW ENGINE
# ============================================================================


class MockWorkflowEngine:
    """
    Deterministic mock workflow execution engine.

    Features:
    - Execute workflows with configurable task handlers
    - Track execution state and history
    - Simulate errors and retries
    - Deterministic timing (no real delays)
    - Full call logging for assertions

    Example:
        >>> engine = MockWorkflowEngine()
        >>>
        >>> # Define tasks
        >>> task1 = TaskDefinition(name="fetch_data", timeout_seconds=30)
        >>> task2 = TaskDefinition(name="process_data", dependencies=["fetch_data"])
        >>>
        >>> # Configure handlers
        >>> engine.set_task_handler("fetch_data", async_handler_func)
        >>> engine.set_task_handler("process_data", async_handler_func)
        >>>
        >>> # Execute
        >>> result = await engine.execute_workflow("wf1", [task1, task2])
        >>> assert result.state == WorkflowState.SUCCEEDED
    """

    def __init__(self, should_fail: bool = False, default_delay_ms: int = 0):
        """
        Initialize MockWorkflowEngine.

        Args:
            should_fail: If True, all workflows fail
            default_delay_ms: Default delay per task in milliseconds (0 for instant)
        """
        self.should_fail = should_fail
        self.default_delay_ms = default_delay_ms

        # State management
        self.executions: Dict[str, WorkflowExecution] = {}
        self.task_handlers: Dict[str, Callable] = {}
        self.task_outcomes: Dict[str, Any] = {}  # Pre-configured outcomes
        self.task_failures: Dict[str, str] = {}  # Pre-configured failures

        # Call tracking
        self.call_log: List[Dict[str, Any]] = []
        self.execution_count = 0

    def set_task_handler(
        self,
        task_name: str,
        handler: Callable[..., Coroutine[Any, Any, Any]],
    ) -> None:
        """Set async handler for a task."""
        self.task_handlers[task_name] = handler
        self.call_log.append({"action": "set_task_handler", "task": task_name})

    def set_task_outcome(self, task_name: str, output: Any) -> None:
        """Pre-configure task outcome."""
        self.task_outcomes[task_name] = output
        self.call_log.append({"action": "set_task_outcome", "task": task_name})

    def set_task_failure(self, task_name: str, error: str) -> None:
        """Pre-configure task to fail."""
        self.task_failures[task_name] = error
        self.call_log.append({"action": "set_task_failure", "task": task_name})

    async def execute_workflow(
        self,
        workflow_id: str,
        tasks: List[TaskDefinition],
        input_params: Optional[Dict[str, Any]] = None,
    ) -> WorkflowExecution:
        """
        Execute a workflow with given tasks.

        Args:
            workflow_id: Unique workflow identifier
            tasks: List of task definitions (with dependencies)
            input_params: Input parameters for workflow

        Returns:
            WorkflowExecution with complete execution history
        """
        execution = WorkflowExecution(
            workflow_id=workflow_id,
            start_time=datetime.now(timezone.utc),
        )

        self.execution_count += 1
        self.call_log.append(
            {
                "action": "execute_workflow",
                "workflow_id": workflow_id,
                "task_count": len(tasks),
            }
        )

        if self.should_fail:
            execution.state = WorkflowState.FAILED
            execution.error = "Workflow configured to fail"
            execution.end_time = datetime.now(timezone.utc)
            self.executions[execution.execution_id] = execution
            return execution

        # Execute tasks respecting dependencies
        completed_tasks: Set[str] = set()
        failed_tasks: Set[str] = set()

        for task in tasks:
            # Check dependencies
            if not all(dep in completed_tasks for dep in task.dependencies):
                task_exec = TaskExecution(
                    task_id=task.id,
                    state=TaskState.SKIPPED,
                    error="Unmet dependencies",
                )
                execution.tasks[task.id] = task_exec
                continue

            # Execute task
            task_exec = await self._execute_task(task, input_params)
            execution.tasks[task.id] = task_exec

            if task_exec.state == TaskState.COMPLETED:
                completed_tasks.add(task.id)
            else:
                failed_tasks.add(task.id)

        # Determine workflow state
        if failed_tasks:
            execution.state = WorkflowState.FAILED
            execution.error = f"{len(failed_tasks)} task(s) failed"
        else:
            execution.state = WorkflowState.SUCCEEDED

        execution.end_time = datetime.now(timezone.utc)
        self.executions[execution.execution_id] = execution
        return execution

    async def _execute_task(
        self,
        task: TaskDefinition,
        input_params: Optional[Dict[str, Any]] = None,
    ) -> TaskExecution:
        """Execute a single task."""
        task_exec = TaskExecution(
            task_id=task.id,
            state=TaskState.IN_PROGRESS,
            input_params=input_params or {},
            start_time=datetime.now(timezone.utc),
        )

        # Check for pre-configured failure
        if task.name in self.task_failures:
            task_exec.state = TaskState.FAILED
            task_exec.error = self.task_failures[task.name]
            task_exec.end_time = datetime.now(timezone.utc)
            return task_exec

        try:
            # Simulate delay if configured
            if self.default_delay_ms > 0:
                await asyncio.sleep(self.default_delay_ms / 1000)

            # Execute handler or use pre-configured outcome
            if task.name in self.task_outcomes:
                task_exec.output = self.task_outcomes[task.name]
            elif task.name in self.task_handlers:
                handler = self.task_handlers[task.name]
                task_exec.output = await handler(input_params or {})
            else:
                task_exec.output = {"status": "completed", "task": task.name}

            task_exec.state = TaskState.COMPLETED
        except Exception as e:
            task_exec.state = TaskState.FAILED
            task_exec.error = str(e)

        task_exec.end_time = datetime.now(timezone.utc)
        return task_exec

    def get_execution(self, execution_id: str) -> Optional[WorkflowExecution]:
        """Retrieve execution by ID."""
        return self.executions.get(execution_id)

    def get_all_executions(self) -> List[WorkflowExecution]:
        """Get all recorded executions."""
        return list(self.executions.values())

    def clear(self) -> None:
        """Clear all execution history."""
        self.executions.clear()
        self.call_log.clear()
        self.execution_count = 0


# ============================================================================
# MOCK TASK SCHEDULER
# ============================================================================


class MockTaskScheduler:
    """
    Mock task scheduler for queuing and scheduling tasks.

    Features:
    - Queue tasks with priority
    - Schedule tasks for later execution
    - Track task scheduling history
    - Simulate scheduling failures

    Example:
        >>> scheduler = MockTaskScheduler()
        >>> task = TaskDefinition(name="process", priority=TaskPriority.HIGH)
        >>> result = await scheduler.schedule(task)
        >>> assert result is True
    """

    def __init__(self):
        self.queue: List[TaskDefinition] = []
        self.scheduled: Dict[str, List[TaskDefinition]] = {}
        self.call_log: List[Dict[str, Any]] = []
        self.should_fail = False

    async def schedule(self, task: TaskDefinition) -> bool:
        """
        Schedule a task for execution.

        Args:
            task: Task to schedule

        Returns:
            True if successfully scheduled, False otherwise
        """
        if self.should_fail:
            self.call_log.append({"action": "schedule", "task": task.name, "result": "failed"})
            return False

        # Add to queue in priority order
        self.queue.append(task)
        self.queue.sort(
            key=lambda t: {"critical": 0, "high": 1, "medium": 2, "low": 3}[t.priority.value]
        )

        self.call_log.append({"action": "schedule", "task": task.name, "result": "success"})
        return True

    async def schedule_at(self, task: TaskDefinition, when: datetime) -> bool:
        """
        Schedule a task for a specific time.

        Args:
            task: Task to schedule
            when: When to execute (datetime)

        Returns:
            True if successfully scheduled
        """
        if self.should_fail:
            return False

        key = when.isoformat()
        if key not in self.scheduled:
            self.scheduled[key] = []
        self.scheduled[key].append(task)

        self.call_log.append(
            {
                "action": "schedule_at",
                "task": task.name,
                "when": when.isoformat(),
                "result": "success",
            }
        )
        return True

    async def get_next(self) -> Optional[TaskDefinition]:
        """Get next task from queue."""
        if self.queue:
            return self.queue.pop(0)
        return None

    async def get_pending_count(self) -> int:
        """Get count of pending tasks."""
        return len(self.queue)

    def clear(self) -> None:
        """Clear queue and history."""
        self.queue.clear()
        self.scheduled.clear()
        self.call_log.clear()


# ============================================================================
# MOCK EXECUTION MONITOR
# ============================================================================


class MockExecutionMonitor:
    """
    Mock execution monitor for tracking workflow and task metrics.

    Features:
    - Track execution metrics (duration, success rate)
    - Monitor task performance
    - Alert on anomalies
    - Generate execution reports

    Example:
        >>> monitor = MockExecutionMonitor()
        >>> await monitor.record_execution(execution)
        >>> stats = await monitor.get_stats()
        >>> assert stats['total_executions'] > 0
    """

    def __init__(self):
        self.metrics: Dict[str, Any] = {
            "total_executions": 0,
            "successful": 0,
            "failed": 0,
            "avg_duration_ms": 0,
            "task_metrics": {},
        }
        self.call_log: List[Dict[str, Any]] = []

    async def record_execution(self, execution: WorkflowExecution) -> None:
        """Record workflow execution metrics."""
        self.metrics["total_executions"] += 1

        if execution.state == WorkflowState.SUCCEEDED:
            self.metrics["successful"] += 1
        elif execution.state == WorkflowState.FAILED:
            self.metrics["failed"] += 1

        # Update duration average
        duration = execution.get_duration() * 1000  # Convert to ms
        current_avg = self.metrics["avg_duration_ms"]
        total = self.metrics["total_executions"]
        self.metrics["avg_duration_ms"] = (current_avg * (total - 1) + duration) / total

        self.call_log.append(
            {
                "action": "record_execution",
                "workflow_id": execution.workflow_id,
                "state": execution.state.value,
            }
        )

    async def record_task(self, task_exec: TaskExecution) -> None:
        """Record task execution metrics."""
        task_id = task_exec.task_id
        if task_id not in self.metrics["task_metrics"]:
            self.metrics["task_metrics"][task_id] = {
                "executions": 0,
                "successful": 0,
                "failed": 0,
                "avg_duration_ms": 0,
            }

        metrics = self.metrics["task_metrics"][task_id]
        metrics["executions"] += 1

        if task_exec.state == TaskState.COMPLETED:
            metrics["successful"] += 1
        elif task_exec.state == TaskState.FAILED:
            metrics["failed"] += 1

        duration = task_exec.get_duration() * 1000
        metrics["avg_duration_ms"] = (
            metrics["avg_duration_ms"] * (metrics["executions"] - 1) + duration
        ) / metrics["executions"]

    async def get_stats(self) -> Dict[str, Any]:
        """Get aggregated metrics."""
        return self.metrics.copy()

    async def get_task_stats(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get metrics for specific task."""
        return self.metrics["task_metrics"].get(task_id)

    def clear(self) -> None:
        """Clear all metrics."""
        self.metrics = {
            "total_executions": 0,
            "successful": 0,
            "failed": 0,
            "avg_duration_ms": 0,
            "task_metrics": {},
        }
        self.call_log.clear()


# ============================================================================
# PYTEST FIXTURES
# ============================================================================


@pytest.fixture
def mock_workflow_engine() -> MockWorkflowEngine:
    """
    Provide mock workflow engine for testing.

    Usage:
        async def test_workflow(mock_workflow_engine):
            task = TaskDefinition(name="test_task")
            result = await mock_workflow_engine.execute_workflow("wf1", [task])
            assert result.state == WorkflowState.SUCCEEDED
    """
    engine = MockWorkflowEngine()
    yield engine
    engine.clear()


@pytest.fixture
async def mock_task_scheduler() -> MockTaskScheduler:
    """Provide mock task scheduler for testing."""
    scheduler = MockTaskScheduler()
    yield scheduler
    scheduler.clear()


@pytest.fixture
async def mock_execution_monitor() -> MockExecutionMonitor:
    """Provide mock execution monitor for testing."""
    monitor = MockExecutionMonitor()
    yield monitor
    monitor.clear()
