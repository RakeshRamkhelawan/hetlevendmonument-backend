"""
Workflow and Task Management Interfaces
Extended interfaces for multi-agent workflow orchestration
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from src.core.shared.interfaces import ExecutionResult, TaskData


class TaskStatus(str, Enum):
    """Enhanced task status for workflow management"""

    PENDING = "pending"
    QUEUED = "queued"
    ASSIGNED = "assigned"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    RETRYING = "retrying"
    BLOCKED = "blocked"  # Waiting for dependencies


class TaskPriority(str, Enum):
    """Task priority levels"""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"
    CRITICAL = "critical"


class WorkflowStatus(str, Enum):
    """Workflow execution status"""

    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RetryStrategy(str, Enum):
    """Task retry strategies"""

    NONE = "none"
    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    FIXED_INTERVAL = "fixed_interval"


@dataclass
class TaskMetrics:
    """Task execution metrics"""

    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    queued_at: datetime | None = None
    assigned_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    queue_time: float = 0.0  # seconds in queue
    execution_time: float = 0.0  # actual execution time
    total_time: float = 0.0  # total time from creation to completion

    retry_count: int = 0
    agent_changes: int = 0  # how many times agent was reassigned


@dataclass
class TaskDependency:
    """Task dependency specification"""

    task_id: str
    dependency_type: str = "completion"  # completion, data, resource
    required: bool = True
    timeout: int | None = None  # seconds to wait for dependency


@dataclass
class EnhancedTaskData:
    """Enhanced task data for workflow management"""

    # Core task info
    base_task: TaskData

    # Workflow management
    workflow_id: str | None = None
    parent_task_id: str | None = None
    subtask_ids: set[str] = field(default_factory=set)

    # Scheduling
    status: TaskStatus = TaskStatus.PENDING
    priority: TaskPriority = TaskPriority.NORMAL
    dependencies: list[TaskDependency] = field(default_factory=list)

    # Assignment
    assigned_agent_id: str | None = None
    preferred_agent_ids: list[str] = field(default_factory=list)
    excluded_agent_ids: list[str] = field(default_factory=list)

    # Retry configuration
    retry_strategy: RetryStrategy = RetryStrategy.EXPONENTIAL
    max_retries: int = 3
    retry_delay: float = 1.0  # base delay in seconds

    # Resource requirements
    estimated_duration: float | None = None
    resource_requirements: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type

    # Tracking
    metrics: TaskMetrics = field(default_factory=TaskMetrics)
    execution_history: list[ExecutionResult] = field(default_factory=list)

    # Context sharing
    input_data: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    output_data: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type

    @property
    def task_id(self) -> str:
        """Get task ID from base task"""
        return self.base_task.id

    def add_dependency(
        self,
        task_id: str,
        dependency_type: str = "completion",
        required: bool = True,
        timeout: int | None = None,
    ) -> None:
        """Add task dependency"""
        dep = TaskDependency(
            task_id=task_id,
            dependency_type=dependency_type,
            required=required,
            timeout=timeout,
        )
        self.dependencies.append(dep)

    def can_execute(self, completed_tasks: set[str]) -> bool:
        """Check if task can execute based on dependencies"""
        if self.status not in [
            TaskStatus.PENDING,
            TaskStatus.QUEUED,
            TaskStatus.RETRYING,
        ]:
            return False

        for dep in self.dependencies:
            if dep.required and dep.task_id not in completed_tasks:
                return False

        return True

    def update_status(self, new_status: TaskStatus, timestamp: datetime | None = None) -> None:
        """Update task status with metrics tracking"""
        if timestamp is None:
            timestamp = datetime.now(timezone.utc)

        old_status = self.status
        self.status = new_status

        # Update metrics based on status transition
        if new_status == TaskStatus.QUEUED and old_status == TaskStatus.PENDING:
            self.metrics.queued_at = timestamp

        elif new_status == TaskStatus.ASSIGNED and old_status == TaskStatus.QUEUED:
            self.metrics.assigned_at = timestamp
            if self.metrics.queued_at:
                self.metrics.queue_time = (timestamp - self.metrics.queued_at).total_seconds()

        elif new_status == TaskStatus.RUNNING and old_status == TaskStatus.ASSIGNED:
            self.metrics.started_at = timestamp

        elif new_status in [TaskStatus.COMPLETED, TaskStatus.FAILED] and self.metrics.started_at:
            self.metrics.completed_at = timestamp
            self.metrics.execution_time = (timestamp - self.metrics.started_at).total_seconds()
            self.metrics.total_time = (timestamp - self.metrics.created_at).total_seconds()


@dataclass
class WorkflowStep:
    """Individual step in a workflow"""

    step_id: str = field(default_factory=lambda: f"step_{uuid4().hex[:8]}")
    task: EnhancedTaskData | None = None

    # Step relationships
    depends_on: list[str] = field(default_factory=list)  # step IDs
    triggers: list[str] = field(default_factory=list)  # step IDs this triggers

    # Step configuration
    retry_on_failure: bool = True
    continue_on_failure: bool = False  # Continue workflow even if this fails
    timeout: int | None = None

    # Step status
    status: TaskStatus = TaskStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    result: ExecutionResult | None = None


@dataclass
class Workflow:
    """Multi-agent workflow definition"""

    workflow_id: str = field(default_factory=lambda: f"workflow_{uuid4().hex[:8]}")
    name: str = ""
    description: str = ""

    # Workflow structure
    steps: dict[str, WorkflowStep] = field(default_factory=dict)
    step_order: list[str] = field(default_factory=list)

    # Workflow metadata
    created_by: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # Workflow status
    status: WorkflowStatus = WorkflowStatus.CREATED
    started_at: datetime | None = None
    completed_at: datetime | None = None

    # Workflow configuration
    max_concurrent_steps: int = 3
    overall_timeout: int | None = None  # seconds

    # Results and context
    workflow_context: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    final_result: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    error_message: str | None = None

    def add_step(self, task: EnhancedTaskData, depends_on: list[str] | None = None) -> str:
        """Add step to workflow"""
        step = WorkflowStep(task=task, depends_on=depends_on or [])

        self.steps[step.step_id] = step
        self.step_order.append(step.step_id)

        # Update task with workflow info
        task.workflow_id = self.workflow_id

        return step.step_id

    def get_ready_steps(self) -> list[str]:
        """Get steps that are ready to execute"""
        ready_steps: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for step_id, step in self.steps.items():
            if step.status != TaskStatus.PENDING:
                continue

            # Check if all dependencies are completed
            dependencies_met = all(
                self.steps[dep_id].status == TaskStatus.COMPLETED
                for dep_id in step.depends_on
                if dep_id in self.steps
            )

            if dependencies_met:
                ready_steps.append(step_id)

        return ready_steps

    def is_completed(self) -> bool:
        """Check if workflow is completed"""
        if not self.steps:
            return True

        return all(
            step.status in [TaskStatus.COMPLETED, TaskStatus.FAILED] for step in self.steps.values()
        )

    def has_failed(self) -> bool:
        """Check if workflow has failed"""
        # Workflow fails if any non-optional step fails
        return any(
            step.status == TaskStatus.FAILED and not step.continue_on_failure
            for step in self.steps.values()
        )

    def get_completion_rate(self) -> float:
        """Get workflow completion percentage"""
        if not self.steps:
            return 1.0

        completed = sum(1 for step in self.steps.values() if step.status == TaskStatus.COMPLETED)

        return completed / len(self.steps)


@dataclass
class QueueStats:
    """Task queue statistics"""

    total_tasks: int = 0
    pending_tasks: int = 0
    running_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0

    avg_queue_time: float = 0.0
    avg_execution_time: float = 0.0
    throughput_per_hour: float = 0.0

    queue_by_priority: dict[TaskPriority, int] = field(default_factory=dict)
    queue_by_agent_type: dict[str, int] = field(default_factory=dict)
