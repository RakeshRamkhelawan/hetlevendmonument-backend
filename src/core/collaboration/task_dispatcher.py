"""
Task Dispatcher - Production Implementation
Task distribution and coordination zoals gespecificeerd in PHOENIX TAAK 1.3
"""

import asyncio
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from .agent_mesh import AgentRegistry, AgentStatus, RegisteredAgent
from .message_protocol import MessagePriority, TaskAssignmentMessage, TaskStatus

logger = logging.getLogger(__name__)


class TaskPriority(str, Enum):
    """Task priority levels for coordination"""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class TaskType(str, Enum):
    """Supported task types for agent mesh coordination"""

    KNOWLEDGE_QUERY = "knowledge_query"
    SENTIMENT_ANALYSIS = "sentiment_analysis"
    TRANSLATION = "translation"
    DIAGNOSTICS = "diagnostics"
    CONTENT_GENERATION = "content_generation"
    SYSTEM_MANAGEMENT = "system_management"


class PendingTask:
    """Task awaiting assignment and execution"""

    def __init__(
        self,
        task_id: str,
        task_type: TaskType,
        task_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        priority: TaskPriority = TaskPriority.NORMAL,
        timeout: int = 300,
        retry_count: int = 3,
    ) -> None:
        self.task_id = task_id
        self.task_type = task_type
        self.task_data = task_data
        self.priority = priority
        self.timeout = timeout
        self.retry_count = retry_count
        self.created_at = datetime.now(timezone.utc)
        self.status = TaskStatus.PENDING
        self.assigned_agent: str | None = None
        self.started_at: datetime | None = None
        self.completed_at: datetime | None = None
        self.result: Any | None = None  # TODO(TYPE): replace Any with concrete type
        self.error: str | None = None


class TaskDispatcher:
    """
    Production task dispatcher for agent mesh coordination
    Implements intelligent task routing and load balancing
    """

    def __init__(self, agent_registry: AgentRegistry) -> None:
        self.agent_registry = agent_registry
        self.pending_tasks: dict[str, PendingTask] = {}
        self.active_tasks: dict[str, PendingTask] = {}
        self.completed_tasks: dict[str, PendingTask] = {}
        self.task_history: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type

        # Task assignment tracking
        self.agent_workload: dict[str, int] = {}
        self.agent_capabilities: dict[str, set[TaskType]] = {}

        # Performance metrics
        self.total_tasks_processed = 0
        self.successful_tasks = 0
        self.failed_tasks = 0

        logger.info("Task dispatcher initialized")

    async def submit_task(
        self,
        task_type: TaskType,
        task_data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        priority: TaskPriority = TaskPriority.NORMAL,
        timeout: int = 300,
        retry_count: int = 3,
    ) -> str:
        """
        Submit new task for processing

        Returns:
            task_id: Unique task identifier
        """
        task_id = f"task_{uuid4().hex[:8]}"

        task = PendingTask(
            task_id=task_id,
            task_type=task_type,
            task_data=task_data,
            priority=priority,
            timeout=timeout,
            retry_count=retry_count,
        )

        self.pending_tasks[task_id] = task

        logger.info(f"Task submitted: {task_id} ({task_type})")

        # Attempt immediate assignment
        await self._try_assign_task(task)

        return task_id

    async def _try_assign_task(self, task: PendingTask) -> bool:
        """
        Attempt to assign task to available agent

        Returns:
            bool: True if task was assigned
        """
        # Find suitable agents
        suitable_agents = await self._find_suitable_agents(task.task_type)

        if not suitable_agents:
            logger.warning(f"No suitable agents found for task {task.task_id} ({task.task_type})")
            return False

        # Select best agent based on workload and capability
        selected_agent = self._select_best_agent(suitable_agents, task)

        if not selected_agent:
            logger.warning(f"No available agents for task {task.task_id}")
            return False

        # Assign task
        await self._assign_task_to_agent(task, selected_agent)
        return True

    async def _find_suitable_agents(self, task_type: TaskType) -> list[RegisteredAgent]:
        """Find agents capable of handling task type"""
        all_agents = self.agent_registry.get_all_agents()
        suitable_agents: list[RegisteredAgent] = []

        for agent in all_agents.values():
            if agent.status == AgentStatus.ONLINE:
                # Check if agent can handle this task type
                if self._agent_supports_task_type(agent, task_type):
                    suitable_agents.append(agent)

        return suitable_agents

    def _agent_supports_task_type(self, agent: RegisteredAgent, task_type: TaskType) -> bool:
        """Check if agent supports specific task type"""
        # Map task types to agent types/capabilities
        task_agent_mapping = {
            TaskType.KNOWLEDGE_QUERY: ["knowledge_processor", "knowledge_agent"],
            TaskType.SENTIMENT_ANALYSIS: ["sentiment_processor", "sentiment_agent"],
            TaskType.TRANSLATION: ["translation_processor", "translation_agent"],
            TaskType.DIAGNOSTICS: ["diagnostics_processor", "diagnostics_agent"],
            TaskType.CONTENT_GENERATION: ["content_generator", "generation_agent"],
            TaskType.SYSTEM_MANAGEMENT: ["system_manager", "admin_agent"],
        }

        supported_agents = task_agent_mapping.get(task_type, [])

        # Check agent type
        if agent.agent_type in supported_agents:
            return True

        # Check agent capabilities
        if hasattr(agent, "capabilities") and agent.capabilities:
            for capability in agent.capabilities:
                if task_type.value in capability or capability in task_type.value:
                    return True

        # Check supported task types
        if hasattr(agent, "supported_task_types") and agent.supported_task_types:
            return task_type.value in agent.supported_task_types

        return False

    def _select_best_agent(
        self, suitable_agents: list[RegisteredAgent], task: PendingTask
    ) -> RegisteredAgent | None:
        """Select best agent based on workload and capability"""
        if not suitable_agents:
            return None

        # Score agents based on multiple factors
        agent_scores: list[tuple[RegisteredAgent, float]] = []
        for agent in suitable_agents:
            score: float = 0.0

            # Factor 1: Current workload (lower is better)
            current_workload = self.agent_workload.get(agent.agent_id, 0)
            max_concurrent = getattr(agent, "max_concurrent_tasks", 5)

            if current_workload >= max_concurrent:
                continue  # Agent at capacity

            workload_score = (max_concurrent - current_workload) / max_concurrent
            score += workload_score * 40  # 40% weight

            # Factor 2: Agent specialization (higher is better)
            if hasattr(agent, "supported_task_types") and agent.supported_task_types:
                if task.task_type.value in agent.supported_task_types:
                    score += 30  # 30% weight for exact match

            # Factor 3: Agent reliability (based on history)
            # TODO: Implement based on task success rate
            score += 20  # 20% baseline reliability

            # Factor 4: Task priority matching
            if task.priority == TaskPriority.CRITICAL:
                score += 10  # Boost for critical tasks

            agent_scores.append((agent, score))

        # Select agent with highest score
        if agent_scores:
            agent_scores.sort(key=lambda x: x[1], reverse=True)
            return agent_scores[0][0]

        return None

    async def _assign_task_to_agent(self, task: PendingTask, agent: RegisteredAgent) -> None:
        """Assign task to specific agent"""
        try:
            # Create task assignment message
            TaskAssignmentMessage(
                sender_id="task_dispatcher",
                recipient_id=agent.agent_id,
                task_name=task.task_id,
                task_type=task.task_type.value,
                task_parameters=task.task_data,
                priority=MessagePriority(task.priority.value),
                estimated_duration=task.timeout,
            )

            # Update task status
            task.status = TaskStatus.ASSIGNED
            task.assigned_agent = agent.agent_id
            task.started_at = datetime.now(timezone.utc)

            # Move task to active
            self.active_tasks[task.task_id] = task
            if task.task_id in self.pending_tasks:
                del self.pending_tasks[task.task_id]

            # Update agent workload
            self.agent_workload[agent.agent_id] = self.agent_workload.get(agent.agent_id, 0) + 1

            # TODO: Send message to agent (implement message delivery)
            logger.info(f"Task {task.task_id} assigned to agent {agent.agent_id}")

            # Start task timeout monitoring
            asyncio.create_task(self._monitor_task_timeout(task))

        except Exception as e:
            logger.error(f"Failed to assign task {task.task_id} to agent {agent.agent_id}: {e}")
            task.status = TaskStatus.FAILED
            task.error = str(e)

    async def _monitor_task_timeout(self, task: PendingTask) -> None:
        """Monitor task execution timeout"""
        await asyncio.sleep(task.timeout)

        # Check if task is still active
        if task.task_id in self.active_tasks and task.status in [
            TaskStatus.ASSIGNED,
            TaskStatus.IN_PROGRESS,
        ]:
            logger.warning(f"Task {task.task_id} timed out")
            await self.handle_task_failure(task.task_id, "Task timeout")

    async def handle_task_update(
        self,
        task_id: str,
        status: TaskStatus,
        result: Any | None = None,  # TODO(TYPE): replace Any with concrete type
        error: str | None = None,
    ) -> None:
        """Handle task status updates from agents"""
        if task_id not in self.active_tasks:
            logger.warning(f"Received update for unknown task: {task_id}")
            return

        task = self.active_tasks[task_id]
        task.status = status

        if result:
            task.result = result
        if error:
            task.error = error

        if status == TaskStatus.COMPLETED:
            await self._complete_task(task)
        elif status == TaskStatus.FAILED:
            await self._handle_task_failure(task)
        elif status == TaskStatus.IN_PROGRESS:
            logger.info(f"Task {task_id} in progress")

    async def _complete_task(self, task: PendingTask) -> None:
        """Mark task as completed and update metrics"""
        task.completed_at = datetime.now(timezone.utc)

        # Move to completed tasks
        self.completed_tasks[task.task_id] = task
        if task.task_id in self.active_tasks:
            del self.active_tasks[task.task_id]

        # Update agent workload
        if task.assigned_agent:
            self.agent_workload[task.assigned_agent] = max(
                0, self.agent_workload.get(task.assigned_agent, 1) - 1
            )

        # Update metrics
        self.total_tasks_processed += 1
        self.successful_tasks += 1

        # Record in history
        self.task_history.append(
            {
                "task_id": task.task_id,
                "task_type": task.task_type.value,
                "status": "completed",
                "agent_id": task.assigned_agent,
                "duration": (
                    (task.completed_at - task.started_at).total_seconds() if task.started_at else 0
                ),
                "completed_at": task.completed_at.isoformat(),
            }
        )

        logger.info(f"Task {task.task_id} completed successfully")

    async def _handle_task_failure(self, task: PendingTask) -> None:
        """Handle task failure with retry logic"""
        self.failed_tasks += 1

        # Update agent workload
        if task.assigned_agent:
            self.agent_workload[task.assigned_agent] = max(
                0, self.agent_workload.get(task.assigned_agent, 1) - 1
            )

        # Check if retries are available
        if task.retry_count > 0:
            logger.info(f"Retrying task {task.task_id} ({task.retry_count} retries left)")

            # Reset task for retry
            task.retry_count -= 1
            task.status = TaskStatus.PENDING
            task.assigned_agent = None
            task.started_at = None
            task.error = None

            # Move back to pending
            self.pending_tasks[task.task_id] = task
            if task.task_id in self.active_tasks:
                del self.active_tasks[task.task_id]

            # Try to assign again
            await self._try_assign_task(task)
        else:
            logger.error(f"Task {task.task_id} failed permanently: {task.error}")

            # Move to completed (failed)
            task.completed_at = datetime.now(timezone.utc)
            self.completed_tasks[task.task_id] = task
            if task.task_id in self.active_tasks:
                del self.active_tasks[task.task_id]

            # Record in history
            self.task_history.append(
                {
                    "task_id": task.task_id,
                    "task_type": task.task_type.value,
                    "status": "failed",
                    "agent_id": task.assigned_agent,
                    "error": task.error,
                    "completed_at": task.completed_at.isoformat(),
                }
            )

    async def handle_task_failure(self, task_id: str, error: str) -> None:
        """Public method to handle task failure"""
        if task_id in self.active_tasks:
            task = self.active_tasks[task_id]
            task.status = TaskStatus.FAILED
            task.error = error
            await self._handle_task_failure(task)

    def get_task_status(self, task_id: str) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Get current status of task"""
        # Check all task collections
        for collection_name, collection in [
            ("pending", self.pending_tasks),
            ("active", self.active_tasks),
            ("completed", self.completed_tasks),
        ]:
            if task_id in collection:
                task = collection[task_id]
                return {
                    "task_id": task.task_id,
                    "task_type": task.task_type.value,
                    "status": task.status.value,
                    "priority": task.priority.value,
                    "assigned_agent": task.assigned_agent,
                    "created_at": task.created_at.isoformat(),
                    "started_at": task.started_at.isoformat() if task.started_at else None,
                    "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                    "result": task.result,
                    "error": task.error,
                    "collection": collection_name,
                }

        return None

    def get_performance_metrics(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get dispatcher performance metrics"""
        return {
            "total_tasks_processed": self.total_tasks_processed,
            "successful_tasks": self.successful_tasks,
            "failed_tasks": self.failed_tasks,
            "success_rate": (self.successful_tasks / max(self.total_tasks_processed, 1)) * 100,
            "pending_tasks_count": len(self.pending_tasks),
            "active_tasks_count": len(self.active_tasks),
            "completed_tasks_count": len(self.completed_tasks),
            "agent_workload": dict(self.agent_workload),
        }

    async def process_pending_tasks(self) -> None:
        """Process pending tasks (called periodically)"""
        if not self.pending_tasks:
            return

        logger.info(f"Processing {len(self.pending_tasks)} pending tasks")

        # Sort by priority and creation time
        sorted_tasks = sorted(
            self.pending_tasks.values(),
            key=lambda t: (
                {"critical": 0, "high": 1, "normal": 2, "low": 3}[t.priority.value],
                t.created_at,
            ),
        )

        for task in sorted_tasks:
            await self._try_assign_task(task)


# Global task dispatcher instance
_task_dispatcher: TaskDispatcher | None = None


async def get_task_dispatcher() -> TaskDispatcher:
    """Get global task dispatcher instance"""
    global _task_dispatcher
    if _task_dispatcher is None:
        from .agent_mesh import get_agent_registry

        agent_registry = get_agent_registry()
        _task_dispatcher = TaskDispatcher(agent_registry)
    return _task_dispatcher
