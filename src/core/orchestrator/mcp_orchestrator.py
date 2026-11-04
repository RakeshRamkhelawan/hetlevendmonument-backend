"""
Multi-Agent MCP Orchestrator
Leverages existing MCP infrastructure for parallel agent execution
"""

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from src.core.shared.production_logging import SafeLogger
from src.core.tool_broker.mcp_client import MCPClientPool, MCPServerConfig, get_mcp_pool

logger = SafeLogger(__name__)


class TaskStatus(Enum):
    """Task execution status"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class AgentTask:
    """Single agent task definition"""

    task_id: str
    agent_name: str
    task_description: str
    priority: int = 0
    timeout: int = 120  # 2 minutes default
    dependencies: list[str] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type

    def __post_init__(self) -> None:
        """Validate task configuration"""
        if not self.task_id:
            raise ValueError("task_id cannot be empty")
        if not self.agent_name:
            raise ValueError("agent_name cannot be empty")
        if not self.task_description:
            raise ValueError("task_description cannot be empty")


@dataclass
class TaskResult:
    """Result from agent task execution"""

    task_id: str
    agent_name: str
    status: TaskStatus
    output: Any = None
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
            "agent_name": self.agent_name,
            "status": self.status.value,
            "output": self.output,
            "error": self.error,
            "execution_time": self.execution_time,
            "success": self.success,
        }


class MCPOrchestrator:
    """
    Orchestrator for parallel MCP agent execution
    Coordinates multiple specialized agents through MCP protocol
    """

    def __init__(self, mcp_pool: MCPClientPool) -> None:
        self.pool = mcp_pool
        self.active_tasks: dict[str, AgentTask] = {}
        self.results: dict[str, TaskResult] = {}
        self._lock = asyncio.Lock()

    async def register_agent(self, config: MCPServerConfig) -> None:
        """Register a specialized agent as MCP server"""
        self.pool.register(config)
        logger.info(f"[ORCHESTRATOR] Registered agent: {config.name}")

    async def execute_parallel(
        self, tasks: list[AgentTask], max_concurrent: int = 4, fail_fast: bool = False
    ) -> list[TaskResult]:
        """
        Execute multiple agent tasks in parallel

        Args:
            tasks: List[Any] of tasks to execute  # TODO(TYPE): replace Any with concrete type
            max_concurrent: Maximum number of concurrent executions
            fail_fast: Stop execution on first failure

        Returns: List[Any] of TaskResult objects  # TODO(TYPE): replace Any with concrete type
        """
        if not tasks:
            logger.warning("[ORCHESTRATOR] No tasks to execute")
            return []

        logger.info(f"[ORCHESTRATOR] Starting parallel execution of {len(tasks)} tasks")

        # Validate task IDs are unique
        task_ids = [task.task_id for task in tasks]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("Task IDs must be unique")

        # Topological sort based on dependencies
        sorted_tasks = self._sort_by_dependencies(tasks)

        # Execute in waves based on dependencies
        results: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        semaphore = asyncio.Semaphore(max_concurrent)

        for wave_num, wave in enumerate(self._group_by_dependency_level(sorted_tasks)):
            logger.info(f"[ORCHESTRATOR] Executing wave {wave_num + 1} with {len(wave)} tasks")

            wave_coroutines = [self._execute_task_with_semaphore(task, semaphore) for task in wave]

            wave_results = await asyncio.gather(*wave_coroutines, return_exceptions=True)

            # Convert exceptions to failed TaskResults
            processed_results: list[Any] = []  # TODO(TYPE): replace Any with concrete type
            for task, result in zip(wave, wave_results):
                if isinstance(result, Exception):
                    processed_results.append(
                        TaskResult(
                            task_id=task.task_id,
                            agent_name=task.agent_name,
                            status=TaskStatus.FAILED,
                            error=f"Unexpected error: {str(result)}",
                            execution_time=0.0,
                        )
                    )
                else:
                    processed_results.append(result)

            results.extend(processed_results)

            # Check for failures if fail_fast enabled
            if fail_fast:
                failed = [r for r in processed_results if not r.success]
                if failed:
                    logger.error(f"[ORCHESTRATOR] Fail-fast triggered. {len(failed)} tasks failed")
                    # Mark remaining tasks as failed
                    remaining_tasks = [t for t in sorted_tasks if t not in wave]
                    for task in remaining_tasks:
                        results.append(
                            TaskResult(
                                task_id=task.task_id,
                                agent_name=task.agent_name,
                                status=TaskStatus.FAILED,
                                error="Execution stopped due to fail-fast",
                                execution_time=0.0,
                            )
                        )
                    break

        # Log summary
        successful = len([r for r in results if r.success])
        failed_count = len([r for r in results if not r.success])
        total_time = sum(r.execution_time for r in results)

        logger.info(
            f"[ORCHESTRATOR] Execution complete: "
            f"{successful}/{len(tasks)} successful, "
            f"{failed_count} failed, "
            f"total time: {total_time:.2f}s"
        )

        return results

    async def execute_sequential(self, tasks: list[AgentTask]) -> list[TaskResult]:
        """
        Execute tasks sequentially (for comparison/debugging)

        Args:
            tasks: List[Any] of tasks to execute  # TODO(TYPE): replace Any with concrete type

        Returns: List[Any] of TaskResult objects  # TODO(TYPE): replace Any with concrete type
        """
        logger.info(f"[ORCHESTRATOR] Starting sequential execution of {len(tasks)} tasks")

        results: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for i, task in enumerate(tasks, 1):
            logger.info(f"[ORCHESTRATOR] Executing task {i}/{len(tasks)}: {task.task_id}")
            result = await self._execute_task(task)
            results.append(result)

            if not result.success:
                logger.warning(f"[ORCHESTRATOR] Task {task.task_id} failed: {result.error}")

        return results

    async def _execute_task_with_semaphore(
        self, task: AgentTask, semaphore: asyncio.Semaphore
    ) -> TaskResult:
        """Execute single task with concurrency control"""
        async with semaphore:
            return await self._execute_task(task)

    async def _execute_task(self, task: AgentTask) -> TaskResult:
        """Execute single agent task via MCP client

        CRITICAL: Creates dedicated MCP connection per task to avoid stdio_client concurrency issues.
        MCP's stdio_client uses anyio TaskGroups that cannot be shared across asyncio tasks.
        """
        start_time = time.time()

        logger.info(f"[AGENT:{task.agent_name}] Starting task: {task.task_id}")

        # Store as active
        async with self._lock:
            self.active_tasks[task.task_id] = task

        # Get server config for this agent
        if task.agent_name not in self.pool._configs:
            logger.error(f"[AGENT:{task.agent_name}] Not registered")
            return TaskResult(
                task_id=task.task_id,
                agent_name=task.agent_name,
                status=TaskStatus.FAILED,
                error=f"Agent '{task.agent_name}' not registered",
                execution_time=time.time() - start_time,
                started_at=start_time,
                completed_at=time.time(),
            )

        server_config = self.pool._configs[task.agent_name]

        # Create DEDICATED MCP client for this task (avoids stdio_client concurrency issues)
        from src.core.tool_broker.mcp_client import MCPClient

        client = MCPClient(server_config)

        try:
            # Connect client
            await client.connect()

            # Execute task with timeout
            try:
                result = await asyncio.wait_for(
                    client.call_tool(
                        "execute_task",
                        {
                            "description": task.task_description,
                            "context": task.context,
                            "task_id": task.task_id,
                        },
                    ),
                    timeout=task.timeout,
                )

                execution_time = time.time() - start_time

                logger.info(
                    f"[AGENT:{task.agent_name}] Task completed: {task.task_id} "
                    f"({execution_time:.2f}s)"
                )

                return TaskResult(
                    task_id=task.task_id,
                    agent_name=task.agent_name,
                    status=TaskStatus.COMPLETED,
                    output=result,
                    execution_time=execution_time,
                    started_at=start_time,
                    completed_at=time.time(),
                )

            except TimeoutError:
                execution_time = time.time() - start_time
                logger.error(
                    f"[AGENT:{task.agent_name}] Task timeout: {task.task_id} "
                    f"(after {task.timeout}s)"
                )
                return TaskResult(
                    task_id=task.task_id,
                    agent_name=task.agent_name,
                    status=TaskStatus.TIMEOUT,
                    error=f"Task timeout after {task.timeout}s",
                    execution_time=execution_time,
                    started_at=start_time,
                    completed_at=time.time(),
                )

        except Exception as e:
            execution_time = time.time() - start_time
            logger.error(
                f"[AGENT:{task.agent_name}] Task execution failed: {task.task_id} - {str(e)}"
            )
            return TaskResult(
                task_id=task.task_id,
                agent_name=task.agent_name,
                status=TaskStatus.FAILED,
                error=str(e),
                execution_time=execution_time,
                started_at=start_time,
                completed_at=time.time(),
            )

        finally:
            # CRITICAL: Cleanup dedicated MCP connection
            try:
                await client.disconnect()
            except Exception as cleanup_error:
                logger.warning(f"[AGENT:{task.agent_name}] Cleanup error: {cleanup_error}")

            # Remove from active
            async with self._lock:
                self.active_tasks.pop(task.task_id, None)

    def _sort_by_dependencies(self, tasks: list[AgentTask]) -> list[AgentTask]:
        """
        Topological sort based on task dependencies
        Falls back to priority-based sort if no dependencies
        """
        if not any(task.dependencies for task in tasks):
            # No dependencies, sort by priority
            return sorted(tasks, key=lambda t: t.priority, reverse=True)

        # Build dependency graph
        graph: dict[str, list[str]] = {}
        in_degree: dict[str, int] = {}
        task_map = {task.task_id: task for task in tasks}

        for task in tasks:
            graph[task.task_id] = task.dependencies.copy()
            in_degree[task.task_id] = len(task.dependencies)

        # Kahn's algorithm for topological sort
        queue = [tid for tid, degree in in_degree.items() if degree == 0]
        sorted_ids: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        while queue:
            # Sort by priority within same level
            queue.sort(key=lambda tid: task_map[tid].priority, reverse=True)
            current = queue.pop(0)
            sorted_ids.append(current)

            # Reduce in-degree for dependent tasks
            for task_id, dependencies in graph.items():
                if current in dependencies:
                    in_degree[task_id] -= 1
                    if in_degree[task_id] == 0:
                        queue.append(task_id)

        # Check for circular dependencies
        if len(sorted_ids) != len(tasks):
            logger.warning("[ORCHESTRATOR] Circular dependency detected, using priority sort")
            return sorted(tasks, key=lambda t: t.priority, reverse=True)

        return [task_map[tid] for tid in sorted_ids]

    def _group_by_dependency_level(self, tasks: list[AgentTask]) -> list[list[AgentTask]]:
        """
        Group tasks into waves that can execute in parallel
        Each wave contains tasks with all dependencies met
        """
        waves: list[list[AgentTask]] = []
        remaining = tasks.copy()
        completed: set[str] = set()

        while remaining:
            # Find tasks with all dependencies met
            current_wave = [
                task
                for task in remaining
                if not task.dependencies or all(dep in completed for dep in task.dependencies)
            ]

            if not current_wave:
                # Circular dependency detected
                logger.error("[ORCHESTRATOR] Circular dependency detected in task graph")
                # Execute all remaining tasks as final wave
                current_wave = remaining.copy()

            waves.append(current_wave)

            # Update tracking
            for task in current_wave:
                remaining.remove(task)
                completed.add(task.task_id)

        return waves

    async def get_active_tasks(self) -> list[AgentTask]:
        """Get currently executing tasks"""
        async with self._lock:
            return list(self.active_tasks.values())

    async def cancel_task(self, task_id: str) -> bool:
        """
        Attempt to cancel a running task
        Note: Actual cancellation depends on agent implementation
        """
        async with self._lock:
            if task_id in self.active_tasks:
                logger.warning(f"[ORCHESTRATOR] Cancellation requested for {task_id}")
                # TODO: Implement actual cancellation via MCP protocol
                return True
            return False


async def create_orchestrator(register_default_agents: bool = True) -> MCPOrchestrator:
    """
    Create and configure MCP orchestrator

    Args:
        register_default_agents: Whether to register GitHub Copilot agents

    Returns:
        Configured MCPOrchestrator instance
    """
    pool = get_mcp_pool()
    orchestrator = MCPOrchestrator(pool)

    if register_default_agents:
        # Register GitHub Copilot specialist agents
        # These can be implemented as MCP servers or CLI tools

        # Note: These are example configurations
        # Actual implementations need to be created

        logger.info("[ORCHESTRATOR] Registering default agents")

        # Serena agent (already configured in mcp_client.py)
        # pool.register is called by initialize_mcp_pool()

    logger.info("[ORCHESTRATOR] Orchestrator created and ready")
    return orchestrator
