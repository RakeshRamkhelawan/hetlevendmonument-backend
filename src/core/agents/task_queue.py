"""
Task Queue & Workflow Management System
Advanced task scheduling and multi-agent workflow orchestration
"""

import asyncio
import heapq
import logging
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Optional
from collections.abc import Callable

from src.core.agents.agent_registry import AgentRegistry as AgentRegistryService
from src.core.agents.workflow_interfaces import (
    EnhancedTaskData,
    QueueStats,
    RetryStrategy,
    TaskPriority,
    TaskStatus,
    Workflow,
    WorkflowStatus,
    WorkflowStep,
)
from src.core.shared.interfaces import ExecutionResult

# Unicode-safe logging (lessons learned!)
logger = logging.getLogger(__name__)


def safe_log(message: str) -> None:
    """Unicode-safe logging function"""
    try:
        logger.info(message)
    except UnicodeEncodeError:
        ascii_message = message.encode("ascii", "replace").decode("ascii")
        logger.info(f"[UNICODE_SAFE] {ascii_message}")


class TaskQueue:
    """Priority-based task queue with dependency management"""

    def __init__(self) -> None:
        # Priority queue: (priority_score, timestamp, task_id, task)
        self._heap: list[tuple[float, datetime, str, EnhancedTaskData]] = []
        self._tasks: dict[str, EnhancedTaskData] = {}
        self._completed_tasks: set[str] = set()
        self._running_tasks: dict[str, EnhancedTaskData] = {}

        # Statistics
        self._stats = QueueStats()
        self._last_stats_update = datetime.now(timezone.utc)

        safe_log("TaskQueue initialized")

    def _calculate_priority_score(self, task: EnhancedTaskData) -> float:
        """Calculate numeric priority score (lower = higher priority)"""
        base_scores = {
            TaskPriority.CRITICAL: 1.0,
            TaskPriority.URGENT: 2.0,
            TaskPriority.HIGH: 3.0,
            TaskPriority.NORMAL: 4.0,
            TaskPriority.LOW: 5.0,
        }

        base_score = base_scores.get(task.priority, 4.0)

        # Adjust for waiting time (older tasks get higher priority)
        age_minutes = (datetime.now(timezone.utc) - task.metrics.created_at).total_seconds() / 60
        age_bonus = min(age_minutes * 0.01, 1.0)  # Max 1.0 bonus after 100 minutes

        # Adjust for retry count (more retries = higher priority)
        retry_bonus = task.metrics.retry_count * 0.1

        return max(0.1, base_score - age_bonus - retry_bonus)

    async def enqueue(self, task: EnhancedTaskData) -> bool:
        """Add task to queue"""
        try:
            if task.task_id in self._tasks:
                safe_log(f"Task {task.task_id} already in queue")
                return False

            # Update task status
            task.update_status(TaskStatus.QUEUED)

            # Calculate priority score
            priority_score = self._calculate_priority_score(task)

            # Add to heap and tracking
            timestamp = datetime.now(timezone.utc)
            heapq.heappush(self._heap, (priority_score, timestamp, task.task_id, task))
            self._tasks[task.task_id] = task

            # Update statistics
            self._update_stats()

            safe_log(f"Task {task.task_id} queued with priority {task.priority.value}")
            return True

        except Exception as e:
            safe_log(f"Failed to enqueue task {task.task_id}: {e}")
            return False

    async def dequeue(self, max_tasks: int = 1) -> list[EnhancedTaskData]:
        """Get next available tasks that can execute"""
        available_tasks: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        temp_heap: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        try:
            # Look through heap for executable tasks
            while self._heap and len(available_tasks) < max_tasks:
                priority_score, timestamp, task_id, task = heapq.heappop(self._heap)

                # Skip if task was removed
                if task_id not in self._tasks:
                    continue

                # Check if task can execute (dependencies met)
                if task.can_execute(self._completed_tasks):
                    available_tasks.append(task)
                    task.update_status(TaskStatus.ASSIGNED)
                else:
                    # Put back in heap if dependencies not met
                    temp_heap.append((priority_score, timestamp, task_id, task))

            # Put non-executable tasks back in heap
            for item in temp_heap:
                heapq.heappush(self._heap, item)

            # Update statistics
            self._update_stats()

            if available_tasks:
                task_ids = [t.task_id for t in available_tasks]
                safe_log(f"Dequeued {len(available_tasks)} tasks: {task_ids}")

            return available_tasks

        except Exception as e:
            safe_log(f"Error dequeuing tasks: {e}")
            return []

    async def mark_running(self, task_id: str, agent_id: str) -> bool:
        """Mark task as running with assigned agent"""
        if task_id not in self._tasks:
            return False

        try:
            task = self._tasks[task_id]
            task.assigned_agent_id = agent_id
            task.update_status(TaskStatus.RUNNING)

            # Move to running tasks
            self._running_tasks[task_id] = task

            safe_log(f"Task {task_id} marked as running on agent {agent_id}")
            return True

        except Exception as e:
            safe_log(f"Error marking task {task_id} as running: {e}")
            return False

    async def mark_completed(self, task_id: str, result: ExecutionResult) -> bool:
        """Mark task as completed with result"""
        if task_id not in self._tasks:
            return False

        try:
            task = self._tasks[task_id]
            task.execution_history.append(result)

            if result.success:
                task.update_status(TaskStatus.COMPLETED)
                task.output_data = result.result_data or {}
                self._completed_tasks.add(task_id)
            else:
                task.update_status(TaskStatus.FAILED)

            # Remove from running tasks
            self._running_tasks.pop(task_id, None)

            # Update statistics
            self._update_stats()

            status_str = "completed" if result.success else "failed"
            safe_log(f"Task {task_id} marked as {status_str}")
            return True

        except Exception as e:
            safe_log(f"Error marking task {task_id} as completed: {e}")
            return False

    async def retry_task(self, task_id: str, delay: float | None = None) -> bool:
        """Retry a failed task with backoff strategy"""
        if task_id not in self._tasks:
            return False

        try:
            task = self._tasks[task_id]

            if task.metrics.retry_count >= task.max_retries:
                safe_log(f"Task {task_id} exceeded max retries ({task.max_retries})")
                return False

            # Calculate retry delay
            if delay is None:
                delay = self._calculate_retry_delay(task)

            # Schedule retry
            if delay > 0:
                safe_log(f"Retrying task {task_id} in {delay:.1f} seconds")
                await asyncio.sleep(delay)

            # Update retry metrics
            task.metrics.retry_count += 1
            task.update_status(TaskStatus.RETRYING)

            # Re-enqueue task
            priority_score = self._calculate_priority_score(task)
            timestamp = datetime.now(timezone.utc)
            heapq.heappush(self._heap, (priority_score, timestamp, task_id, task))

            safe_log(f"Task {task_id} requeued for retry (attempt {task.metrics.retry_count})")
            return True

        except Exception as e:
            safe_log(f"Error retrying task {task_id}: {e}")
            return False

    def _calculate_retry_delay(self, task: EnhancedTaskData) -> float:
        """Calculate retry delay based on strategy"""
        base_delay = float(task.retry_delay)
        retry_count = int(task.metrics.retry_count)

        if task.retry_strategy == RetryStrategy.NONE:
            return 0.0
        elif task.retry_strategy == RetryStrategy.LINEAR:
            return base_delay * (retry_count + 1)
        elif task.retry_strategy == RetryStrategy.EXPONENTIAL:
            return float(base_delay * (2**retry_count))
        elif task.retry_strategy == RetryStrategy.FIXED_INTERVAL:
            return base_delay
        else:
            return base_delay

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a task"""
        if task_id not in self._tasks:
            return False

        try:
            task = self._tasks[task_id]
            task.update_status(TaskStatus.CANCELLED)

            # Remove from running tasks if present
            self._running_tasks.pop(task_id, None)

            safe_log(f"Task {task_id} cancelled")
            return True

        except Exception as e:
            safe_log(f"Error cancelling task {task_id}: {e}")
            return False

    def get_task(self, task_id: str) -> EnhancedTaskData | None:
        """Get task by ID"""
        return self._tasks.get(task_id)

    def get_queue_stats(self) -> QueueStats:
        """Get queue statistics"""
        self._update_stats()
        return self._stats

    def _update_stats(self) -> None:
        """Update queue statistics"""
        datetime.now(timezone.utc)

        # Basic counts
        self._stats.total_tasks = len(self._tasks)
        self._stats.pending_tasks = sum(
            1 for t in self._tasks.values() if t.status in [TaskStatus.PENDING, TaskStatus.QUEUED]
        )
        self._stats.running_tasks = len(self._running_tasks)
        self._stats.completed_tasks = len(self._completed_tasks)
        self._stats.failed_tasks = sum(
            1 for t in self._tasks.values() if t.status == TaskStatus.FAILED
        )

        # Calculate averages
        completed_tasks = [t for t in self._tasks.values() if t.status == TaskStatus.COMPLETED]
        if completed_tasks:
            self._stats.avg_queue_time = sum(t.metrics.queue_time for t in completed_tasks) / len(
                completed_tasks
            )
            self._stats.avg_execution_time = sum(
                t.metrics.execution_time for t in completed_tasks
            ) / len(completed_tasks)

        # Priority distribution
        self._stats.queue_by_priority = defaultdict(int)
        for task in self._tasks.values():
            if task.status in [TaskStatus.PENDING, TaskStatus.QUEUED]:
                self._stats.queue_by_priority[task.priority] += 1


class RetryManager:
    """Intelligent retry management for failed tasks"""

    def __init__(self) -> None:
        self.retry_policies: dict[str, Callable[..., Any]] = {}  # TODO(TYPE): replace Any with concrete type
        self.failure_patterns: dict[str, list[str]] = defaultdict(list)

    def register_retry_policy(self, error_type: str, policy: Callable[..., Any]) -> None:  # TODO(TYPE): replace Any with concrete type
        """Register custom retry policy for specific error types"""
        self.retry_policies[error_type] = policy

    async def should_retry(self, task: EnhancedTaskData, result: ExecutionResult) -> bool:
        """Determine if task should be retried based on failure analysis"""
        if task.metrics.retry_count >= task.max_retries:
            return False

        if not result.error_message:
            return False

        # Record failure pattern
        self.failure_patterns[task.task_id].append(result.error_message)

        # Check for repeating failures
        recent_failures = self.failure_patterns[task.task_id][-3:]
        if len(recent_failures) >= 3 and len(set(recent_failures)) == 1:
            safe_log(f"Task {task.task_id} has repeating failures, stopping retries")
            return False

        # Apply custom retry policies
        for error_type, policy in self.retry_policies.items():
            if error_type.lower() in result.error_message.lower():
                return bool(await policy(task, result))

        # Default retry logic
        transient_errors = [
            "timeout",
            "connection",
            "network",
            "temporary",
            "rate limit",
            "service unavailable",
        ]

        error_msg = result.error_message.lower()
        return any(err in error_msg for err in transient_errors)


class WorkflowEngine:
    """Multi-step workflow execution engine"""

    def __init__(self, task_queue: TaskQueue, agent_registry: AgentRegistryService) -> None:
        self.task_queue = task_queue
        self.agent_registry = agent_registry
        self.retry_manager = RetryManager()

        self.active_workflows: dict[str, Workflow] = {}
        self.workflow_monitors: dict[str, asyncio.Task[Any]] = {}  # TODO(TYPE): replace Any with concrete type

        safe_log("WorkflowEngine initialized")

    async def submit_workflow(self, workflow: Workflow) -> bool:
        """Submit workflow for execution"""
        try:
            workflow.status = WorkflowStatus.RUNNING
            workflow.started_at = datetime.now(timezone.utc)

            self.active_workflows[workflow.workflow_id] = workflow

            # Start workflow monitoring
            monitor_task = asyncio.create_task(self._monitor_workflow(workflow.workflow_id))
            self.workflow_monitors[workflow.workflow_id] = monitor_task

            safe_log(f"Workflow {workflow.workflow_id} submitted with {len(workflow.steps)} steps")
            return True

        except Exception as e:
            safe_log(f"Error submitting workflow {workflow.workflow_id}: {e}")
            return False

    async def _monitor_workflow(self, workflow_id: str) -> None:
        """Monitor workflow execution"""
        try:
            while workflow_id in self.active_workflows:
                workflow = self.active_workflows[workflow_id]

                if workflow.status != WorkflowStatus.RUNNING:
                    break

                # Check for ready steps
                ready_steps = workflow.get_ready_steps()

                for step_id in ready_steps:
                    step = workflow.steps[step_id]
                    await self._execute_workflow_step(workflow, step)

                # Check workflow completion
                if workflow.is_completed():
                    await self._complete_workflow(workflow)
                    break
                elif workflow.has_failed():
                    await self._fail_workflow(workflow)
                    break

                # Check timeout
                started_at = workflow.started_at
                if workflow.overall_timeout and started_at is not None:
                    elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
                    if elapsed > workflow.overall_timeout:
                        await self._timeout_workflow(workflow)
                        break

                await asyncio.sleep(1)  # Check every second

        except Exception as e:
            safe_log(f"Error monitoring workflow {workflow_id}: {e}")
            if workflow_id in self.active_workflows:
                await self._fail_workflow(self.active_workflows[workflow_id])

    async def _execute_workflow_step(self, workflow: Workflow, step: WorkflowStep) -> None:
        """Execute individual workflow step"""
        try:
            step.status = TaskStatus.RUNNING
            step.started_at = datetime.now(timezone.utc)

            # Enqueue step task (with None check)
            if step.task is None:
                raise ValueError(f"Step {step.step_id} has no associated task")
            await self.task_queue.enqueue(step.task)

            safe_log(f"Workflow step {step.step_id} started")

        except Exception as e:
            safe_log(f"Error executing workflow step {step.step_id}: {e}")
            step.status = TaskStatus.FAILED

    async def _complete_workflow(self, workflow: Workflow) -> None:
        """Complete workflow execution"""
        workflow.status = WorkflowStatus.COMPLETED
        workflow.completed_at = datetime.now(timezone.utc)

        # Collect final results
        workflow.final_result = {}
        for step_id, step in workflow.steps.items():
            if step.result and step.result.success:
                workflow.final_result[step_id] = step.result.result_data

        safe_log(f"Workflow {workflow.workflow_id} completed successfully")

        # Cleanup
        self.active_workflows.pop(workflow.workflow_id, None)
        self.workflow_monitors.pop(workflow.workflow_id, None)

    async def _fail_workflow(self, workflow: Workflow) -> None:
        """Handle workflow failure"""
        workflow.status = WorkflowStatus.FAILED
        workflow.completed_at = datetime.now(timezone.utc)

        # Find failure reason
        failed_steps = [
            step for step in workflow.steps.values() if step.status == TaskStatus.FAILED
        ]

        if failed_steps:
            workflow.error_message = f"Failed steps: {[s.step_id for s in failed_steps]}"

        safe_log(f"Workflow {workflow.workflow_id} failed: {workflow.error_message}")

        # Cleanup
        self.active_workflows.pop(workflow.workflow_id, None)
        self.workflow_monitors.pop(workflow.workflow_id, None)

    async def _timeout_workflow(self, workflow: Workflow) -> None:
        """Handle workflow timeout"""
        workflow.status = WorkflowStatus.FAILED
        workflow.completed_at = datetime.now(timezone.utc)
        workflow.error_message = f"Workflow timed out after {workflow.overall_timeout}s"

        safe_log(f"Workflow {workflow.workflow_id} timed out")

        # Cancel running steps
        for step in workflow.steps.values():
            if step.status == TaskStatus.RUNNING and step.task is not None:
                await self.task_queue.cancel_task(step.task.task_id)

        # Cleanup
        self.active_workflows.pop(workflow.workflow_id, None)
        self.workflow_monitors.pop(workflow.workflow_id, None)

    async def get_workflow_status(self, workflow_id: str) -> Workflow | None:
        """Get workflow status"""
        return self.active_workflows.get(workflow_id)

    async def cancel_workflow(self, workflow_id: str) -> bool:
        """Cancel running workflow"""
        if workflow_id not in self.active_workflows:
            return False

        try:
            workflow = self.active_workflows[workflow_id]
            workflow.status = WorkflowStatus.CANCELLED

            # Cancel all running steps
            for step in workflow.steps.values():
                if (
                    step.status in [TaskStatus.RUNNING, TaskStatus.ASSIGNED]
                    and step.task is not None
                ):
                    await self.task_queue.cancel_task(step.task.task_id)

            # Stop monitoring
            if workflow_id in self.workflow_monitors:
                self.workflow_monitors[workflow_id].cancel()

            safe_log(f"Workflow {workflow_id} cancelled")
            return True

        except Exception as e:
            safe_log(f"Error cancelling workflow {workflow_id}: {e}")
            return False


class TaskExecutionCoordinator:
    """Coordinates task execution across agents"""

    def __init__(
        self,
        task_queue: TaskQueue,
        agent_registry: AgentRegistryService,
        workflow_engine: WorkflowEngine,
    ) -> None:
        self.task_queue = task_queue
        self.agent_registry = agent_registry
        self.workflow_engine = workflow_engine
        self.retry_manager = RetryManager()

        self.execution_workers: list[asyncio.Task[Any]] = []  # TODO(TYPE): replace Any with concrete type
        self.max_workers = 5
        self.running = False

        safe_log("TaskExecutionCoordinator initialized")

    async def start(self) -> None:
        """Start task execution coordination"""
        if self.running:
            return

        self.running = True

        # Start execution workers
        for i in range(self.max_workers):
            worker = asyncio.create_task(self._execution_worker(f"worker_{i}"))
            self.execution_workers.append(worker)

        safe_log(f"TaskExecutionCoordinator started with {self.max_workers} workers")

    async def stop(self) -> None:
        """Stop task execution coordination"""
        self.running = False

        # Cancel all workers
        for worker in self.execution_workers:
            worker.cancel()

        # Wait for workers to finish
        if self.execution_workers:
            await asyncio.gather(*self.execution_workers, return_exceptions=True)

        self.execution_workers.clear()
        safe_log("TaskExecutionCoordinator stopped")

    async def _execution_worker(self, worker_id: str) -> None:
        """Individual execution worker"""
        safe_log(f"Execution worker {worker_id} started")

        try:
            while self.running:
                # Get next available task
                tasks = await self.task_queue.dequeue(max_tasks=1)

                if not tasks:
                    await asyncio.sleep(0.5)  # Brief pause when no tasks
                    continue

                task = tasks[0]

                # Find best agent for task
                agent_id = await self.agent_registry.find_best_agent_for_task(task.base_task)

                if not agent_id:
                    # No agent available, requeue task
                    safe_log(f"No agent available for task {task.task_id}, requeuing")
                    await self.task_queue.enqueue(task)
                    await asyncio.sleep(1)
                    continue

                # Execute task
                await self._execute_task(task, agent_id)  # type: ignore[arg-type]

        except asyncio.CancelledError:
            safe_log(f"Execution worker {worker_id} cancelled")
        except Exception as e:
            safe_log(f"Execution worker {worker_id} error: {e}")

    async def _execute_task(self, task: EnhancedTaskData, agent_id: str) -> None:
        """Execute single task on agent"""
        try:
            # Mark task as running
            await self.task_queue.mark_running(task.task_id, agent_id)

            # Get agent from registry
            agent_info = self.agent_registry._agents.get(agent_id)
            if not agent_info or not agent_info.agent_ref:  # type: ignore[attr-defined]
                raise Exception(f"Agent {agent_id} not available")

            # Execute task on agent
            result = await agent_info.agent_ref.process_task(task.base_task)  # type: ignore[attr-defined]

            # Mark task as completed
            await self.task_queue.mark_completed(task.task_id, result)

            # Handle retry if needed
            if not result.success and await self.retry_manager.should_retry(task, result):
                await self.task_queue.retry_task(task.task_id)

        except Exception as e:
            safe_log(f"Error executing task {task.task_id}: {e}")

            # Create failure result
            failure_result = ExecutionResult(
                task_id=task.task_id, success=False, error_message=str(e)
            )

            await self.task_queue.mark_completed(task.task_id, failure_result)
