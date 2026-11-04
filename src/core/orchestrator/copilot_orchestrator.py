"""
GitHub Copilot Orchestrator
True multi-agent orchestration using runSubagent()
"""

import asyncio
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional
from collections.abc import Callable

from src.core.shared.production_logging import SafeLogger

logger = SafeLogger(__name__)


class TaskStatus(Enum):
    """Task execution status"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class OrchestratorTask:
    """
    Single orchestrator task that will be executed by a subagent
    """

    task_id: str
    description: str  # Detailed prompt for subagent
    dependencies: list[str] = field(default_factory=list)
    timeout: int = 600  # 10 minutes default
    priority: int = 0  # Higher = execute first
    expected_outcome: str = ""  # What success looks like
    context: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type

    def __post_init__(self) -> None:
        """Validate task configuration"""
        if not self.task_id:
            raise ValueError("task_id cannot be empty")
        if not self.description:
            raise ValueError("description cannot be empty")
        if self.timeout <= 0:
            raise ValueError("timeout must be positive")


@dataclass
class TaskResult:
    """Result from subagent execution"""

    task_id: str
    status: TaskStatus
    output: str = ""
    error: str | None = None
    execution_time: float = 0.0
    started_at: float | None = None
    completed_at: float | None = None

    @property
    def success(self) -> bool:
        """Check if task completed successfully"""
        return self.status == TaskStatus.COMPLETED

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert to dictionary for serialization"""
        return {
            "task_id": self.task_id,
            "status": self.status.value,
            "output": self.output[:500] if self.output else "",  # Truncate for JSON
            "error": self.error,
            "execution_time": self.execution_time,
            "success": self.success,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
        }


class CopilotOrchestrator:
    """
    Main orchestrator class that coordinates subagent execution

    This orchestrator delegates tasks to independent GitHub Copilot agent
    instances via runSubagent(). It handles:
    - Task dependency resolution
    - Wave-based parallel execution
    - Progress monitoring
    - Result aggregation
    - Error handling and retries
    """

    def __init__(
        self,
        subagent_executor: Callable[..., Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        working_dir: Path | None = None,
    ) -> None:
        """
        Initialize orchestrator

        Args:
            subagent_executor: Function to execute subagent (for testing)
            working_dir: Working directory for tasks
        """
        self.tasks: dict[str, OrchestratorTask] = {}
        self.results: dict[str, TaskResult] = {}
        self.working_dir = working_dir or Path.cwd()
        self._subagent_executor = subagent_executor
        self._active_tasks: set[str] = set()

        logger.info(f"[ORCHESTRATOR] Initialized with working_dir: {self.working_dir}")

    def add_task(self, task: OrchestratorTask) -> None:
        """Add task to execution queue"""
        if task.task_id in self.tasks:
            raise ValueError(f"Task {task.task_id} already exists")

        # Validate dependencies exist
        for dep_id in task.dependencies:
            if dep_id not in self.tasks:
                raise ValueError(f"Dependency {dep_id} not found for task {task.task_id}")

        self.tasks[task.task_id] = task
        logger.info(f"[ORCHESTRATOR] Added task: {task.task_id}")

    def add_tasks(self, tasks: list[OrchestratorTask]) -> None:
        """Add multiple tasks"""
        for task in tasks:
            self.add_task(task)

    async def execute_parallel(
        self, max_concurrent: int = 4, fail_fast: bool = False
    ) -> list[TaskResult]:
        """
        Execute tasks in parallel with dependency resolution

        Args:
            max_concurrent: Maximum concurrent subagents
            fail_fast: Stop on first failure

        Returns: list[Any] of task results  # TODO(TYPE): replace Any with concrete type
        """
        if not self.tasks:
            logger.warning("[ORCHESTRATOR] No tasks to execute")
            return []

        logger.info(f"[ORCHESTRATOR] Starting execution of {len(self.tasks)} tasks")
        start_time = time.time()

        # Create execution waves based on dependencies
        waves = self._create_execution_waves()
        logger.info(f"[ORCHESTRATOR] Created {len(waves)} execution waves")

        all_results: list[TaskResult] = []

        # Execute waves sequentially, tasks within wave in parallel
        for wave_num, wave_tasks in enumerate(waves, 1):
            logger.info(
                f"[ORCHESTRATOR] Executing wave {wave_num}/{len(waves)} with {len(wave_tasks)} tasks"
            )

            # Limit concurrency
            semaphore = asyncio.Semaphore(max_concurrent)

            # Execute wave tasks in parallel
            wave_coroutines = [
                self._execute_task_with_semaphore(task, semaphore) for task in wave_tasks
            ]

            wave_results = await asyncio.gather(*wave_coroutines, return_exceptions=True)

            # Process results
            for result in wave_results:
                if isinstance(result, BaseException):
                    logger.error(f"[ORCHESTRATOR] Task raised exception: {result}")
                    continue

                # Type narrowing: result is now TaskResult (not BaseException)
                task_result: TaskResult = result
                all_results.append(task_result)
                self.results[task_result.task_id] = task_result

                # Fail-fast check
                if fail_fast and not result.success:
                    logger.warning(f"[ORCHESTRATOR] Fail-fast triggered by task: {result.task_id}")
                    total_time = time.time() - start_time
                    self._log_summary(all_results, total_time)
                    return all_results

            # Check if wave had failures
            wave_failures = [
                r for r in wave_results if not isinstance(r, BaseException) and not r.success
            ]
            if wave_failures:
                logger.warning(f"[ORCHESTRATOR] Wave {wave_num} had {len(wave_failures)} failures")

        # Final summary
        total_time = time.time() - start_time
        self._log_summary(all_results, total_time)

        return all_results

    async def execute_sequential(self) -> list[TaskResult]:
        """Execute tasks sequentially (for debugging)"""
        logger.info(f"[ORCHESTRATOR] Starting sequential execution of {len(self.tasks)} tasks")

        # Sort by priority and dependencies
        sorted_tasks = self._topological_sort()

        results: list[TaskResult] = []
        for task in sorted_tasks:
            result = await self._execute_task(task)
            results.append(result)
            self.results[task.task_id] = result

            if not result.success:
                logger.warning(f"[ORCHESTRATOR] Task {task.task_id} failed, continuing...")

        return results

    async def _execute_task_with_semaphore(
        self, task: OrchestratorTask, semaphore: asyncio.Semaphore
    ) -> TaskResult:
        """Execute task with concurrency limit"""
        async with semaphore:
            return await self._execute_task(task)

    async def _execute_task(self, task: OrchestratorTask) -> TaskResult:
        """
        Execute a single task via subagent

        IMPORTANT: This function MUST be called from within a GitHub Copilot Chat session
        where runSubagent() is available. It will NOT work in CLI/standalone mode.

        The orchestrator is designed to be used by the MAIN CHAT AGENT only, not via CLI.
        """
        logger.info(f"[ORCHESTRATOR] Starting task: {task.task_id}")
        start_time = time.time()

        self._active_tasks.add(task.task_id)

        try:
            # Use custom executor if provided (for testing/CLI mode)
            if self._subagent_executor:
                output = await self._subagent_executor(task.description, task.task_id)
            else:
                # PRODUCTION MODE: This code ONLY runs inside GitHub Copilot Chat
                # The main chat agent will import this module and provide runSubagent
                # via dependency injection during create_orchestrator()
                raise RuntimeError(
                    "Orchestrator is running in standalone mode without runSubagent() executor.\n"
                    "This orchestrator MUST be used from within a GitHub Copilot Chat session.\n"
                    "The main chat agent should call:\n"
                    "  orchestrator = create_orchestrator(subagent_executor=runSubagent)\n"
                    "  results = await orchestrator.execute_parallel()\n"
                    "\n"
                    "For CLI usage, the chat agent must manually call runSubagent() for each task."
                )

            execution_time = time.time() - start_time

            result = TaskResult(
                task_id=task.task_id,
                status=TaskStatus.COMPLETED,
                output=output,
                execution_time=execution_time,
                started_at=start_time,
                completed_at=time.time(),
            )

            logger.info(f"[ORCHESTRATOR] Task completed: {task.task_id} ({execution_time:.2f}s)")
            return result

        except TimeoutError:
            execution_time = time.time() - start_time
            logger.error(f"[ORCHESTRATOR] Task timeout: {task.task_id}")

            return TaskResult(
                task_id=task.task_id,
                status=TaskStatus.TIMEOUT,
                error=f"Task exceeded timeout of {task.timeout}s",
                execution_time=execution_time,
                started_at=start_time,
                completed_at=time.time(),
            )

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(f"[ORCHESTRATOR] Task failed: {task.task_id} - {e}")

            return TaskResult(
                task_id=task.task_id,
                status=TaskStatus.FAILED,
                error=str(e),
                execution_time=execution_time,
                started_at=start_time,
                completed_at=time.time(),
            )

        finally:
            self._active_tasks.discard(task.task_id)

    def _create_execution_waves(self) -> list[list[OrchestratorTask]]:
        """
        Group tasks into waves based on dependencies
        Tasks in the same wave can execute in parallel
        """
        sorted_tasks = self._topological_sort()

        waves: list[list[OrchestratorTask]] = []
        task_wave: dict[str, int] = {}

        for task in sorted_tasks:
            # Find maximum wave number of dependencies
            max_dep_wave = -1
            for dep_id in task.dependencies:
                if dep_id in task_wave:
                    max_dep_wave = max(max_dep_wave, task_wave[dep_id])

            # This task goes in the wave after all its dependencies
            wave_num = max_dep_wave + 1
            task_wave[task.task_id] = wave_num

            # Ensure wave list is long enough
            while len(waves) <= wave_num:
                waves.append([])

            waves[wave_num].append(task)

        return waves

    def _topological_sort(self) -> list[OrchestratorTask]:
        """
        Sort tasks by dependencies using topological sort
        Also considers priority as secondary sort key
        """
        # Build dependency graph
        in_degree: dict[str, int] = {task_id: 0 for task_id in self.tasks}
        graph: dict[str, list[str]] = {task_id: [] for task_id in self.tasks}

        for task_id, task in self.tasks.items():
            for dep_id in task.dependencies:
                graph[dep_id].append(task_id)
                in_degree[task_id] += 1

        # Find tasks with no dependencies
        queue = [
            (task.priority, task_id)
            for task_id, task in self.tasks.items()
            if in_degree[task_id] == 0
        ]
        queue.sort(reverse=True)  # Higher priority first

        sorted_tasks: list[OrchestratorTask] = []

        while queue:
            _, task_id = queue.pop(0)
            sorted_tasks.append(self.tasks[task_id])

            # Reduce in-degree for dependent tasks
            for dependent_id in graph[task_id]:
                in_degree[dependent_id] -= 1
                if in_degree[dependent_id] == 0:
                    queue.append((self.tasks[dependent_id].priority, dependent_id))
                    queue.sort(reverse=True)

        # Check for cycles
        if len(sorted_tasks) != len(self.tasks):
            raise ValueError("Cyclic dependencies detected")

        return sorted_tasks

    def _log_summary(self, results: list[TaskResult], total_time: float) -> None:
        """Log execution summary"""
        successful = len([r for r in results if r.success])
        failed = len([r for r in results if not r.success])

        logger.info(
            f"[ORCHESTRATOR] Execution complete: "
            f"{successful}/{len(results)} successful, "
            f"{failed} failed, "
            f"total time: {total_time:.2f}s"
        )

    def get_status(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get current orchestrator status"""
        return {
            "total_tasks": len(self.tasks),
            "completed": len([r for r in self.results.values() if r.success]),
            "failed": len([r for r in self.results.values() if not r.success]),
            "active": len(self._active_tasks),
            "pending": len(self.tasks) - len(self.results),
        }

    def export_results(self, output_file: Path) -> None:
        """Export results to JSON file"""
        output_data = {
            "summary": self.get_status(),
            "results": [r.to_dict() for r in self.results.values()],
        }

        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2)

        logger.info(f"[ORCHESTRATOR] Results exported to {output_file}")


# Helper functions for easy usage


def create_orchestrator(
    subagent_executor: Callable[..., Any] | None = None,  # TODO(TYPE): replace Any with concrete type
) -> CopilotOrchestrator:
    """Create a new orchestrator instance"""
    return CopilotOrchestrator(subagent_executor=subagent_executor)


async def execute_tasks(
    tasks: list[OrchestratorTask], max_concurrent: int = 4, fail_fast: bool = False
) -> list[TaskResult]:
    """
    Convenience function to create orchestrator and execute tasks

    NOTE: This function is designed for use by the main GitHub Copilot Chat agent.
    It will NOT work in CLI/standalone mode unless a custom subagent_executor is provided.

    Args:
        tasks: list[Any] of tasks to execute  # TODO(TYPE): replace Any with concrete type
        max_concurrent: Maximum concurrent subagents
        fail_fast: Stop on first failure

    Returns: list[Any] of task results  # TODO(TYPE): replace Any with concrete type
    """
    orchestrator = create_orchestrator()
    orchestrator.add_tasks(tasks)
    return await orchestrator.execute_parallel(max_concurrent, fail_fast)


def create_quick_tasks(descriptions: list[str], timeout: int = 600) -> list[OrchestratorTask]:
    """
    Quick helper to create tasks from simple string descriptions

    Usage:
        tasks = create_quick_tasks([
            "Fix test failures in test_auth.py",
            "Fix test failures in test_user.py"
        ])
        results = await execute_tasks(tasks)

    Args:
        descriptions: list[Any] of task descriptions (will be used as prompts)  # TODO(TYPE): replace Any with concrete type
        timeout: Timeout per task in seconds

    Returns: list[Any] of OrchestratorTask objects  # TODO(TYPE): replace Any with concrete type
    """
    return [
        OrchestratorTask(task_id=f"task_{i + 1}", description=desc, timeout=timeout, priority=0)
        for i, desc in enumerate(descriptions)
    ]


def create_dependency_chain(descriptions: list[str], timeout: int = 600) -> list[OrchestratorTask]:
    """
    Create tasks with sequential dependencies (task N depends on task N-1)

    Usage:
        tasks = create_dependency_chain([
            "Step 1: set[Any]up database",
            "Step 2: Run migrations",
            "Step 3: Seed data"
        ])
        results = await execute_tasks(tasks)

    Args:
        descriptions: list[Any] of task descriptions in execution order  # TODO(TYPE): replace Any with concrete type
        timeout: Timeout per task in seconds

    Returns: list[Any] of OrchestratorTask objects with dependencies  # TODO(TYPE): replace Any with concrete type
    """
    tasks: list[Any] = []  # TODO(TYPE): replace Any with concrete type
    for i, desc in enumerate(descriptions):
        dependencies = [f"task_{i}"] if i > 0 else []
        tasks.append(
            OrchestratorTask(
                task_id=f"task_{i + 1}",
                description=desc,
                dependencies=dependencies,
                timeout=timeout,
                priority=len(descriptions) - i,  # Earlier tasks have higher priority
            )
        )
    return tasks


def format_results_summary(results: list[TaskResult]) -> str:
    """
    Format task results into a user-friendly summary

    Args:
        results: list[Any] of task results from execute_tasks()  # TODO(TYPE): replace Any with concrete type

    Returns:
        Formatted summary string
    """
    successful = [r for r in results if r.success]
    failed = [r for r in results if not r.success]
    total_time = sum(r.execution_time for r in results)

    lines = [
        "[OK] ORCHESTRATOR RESULTS",
        "=" * 60,
        f"Total: {len(results)} tasks",
        f"Successful: {len(successful)}",
        f"Failed: {len(failed)}",
        f"Total time: {total_time:.2f}s",
        "",
    ]

    if successful:
        lines.append("[OK] Successful Tasks:")
        for r in successful:
            output_preview = r.output[:100] + "..." if len(r.output) > 100 else r.output
            lines.append(f"  - {r.task_id} ({r.execution_time:.2f}s): {output_preview}")
        lines.append("")

    if failed:
        lines.append("[FAIL] Failed Tasks:")
        for r in failed:
            lines.append(f"  - {r.task_id}: {r.error}")
        lines.append("")

    lines.append("=" * 60)
    return "\n".join(lines)
