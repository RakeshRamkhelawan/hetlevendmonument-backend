"""
Task Coordinator - Collaborative Task Management
Manages task distribution and coordination across the agent mesh network
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """Task execution status"""

    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(Enum):
    """Task priority levels"""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass
class TaskRequirement:
    """Requirement specification for collaborative tasks"""

    skill_type: str
    minimum_capability_level: float
    estimated_duration: float
    resource_requirements: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    dependencies: list[str] = field(default_factory=list)


@dataclass
class CollaborativeTask:
    """Collaborative task definition"""

    task_id: str
    title: str
    description: str
    requirements: list[TaskRequirement]
    priority: TaskPriority
    status: TaskStatus
    created_at: datetime
    assigned_agents: list[str] = field(default_factory=list)
    progress_percentage: float = 0.0
    result: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type


class TaskCoordinator:
    """Task coordination and management system"""

    def __init__(self) -> None:
        self.active_tasks: dict[str, CollaborativeTask] = {}
        self.completed_tasks: dict[str, CollaborativeTask] = {}
        self.task_queue: list[str] = []
        self.agent_workloads: dict[str, int] = {}
        self.task_history: list[str] = []

        logger.info("Task Coordinator initialized")

    async def submit_collaborative_task(
        self,
        title: str,
        description: str,
        requirements: list[TaskRequirement],
        priority: TaskPriority = TaskPriority.MEDIUM,
    ) -> str:
        """Submit a new collaborative task"""
        task_id = str(uuid.uuid4())

        task = CollaborativeTask(
            task_id=task_id,
            title=title,
            description=description,
            requirements=requirements,
            priority=priority,
            status=TaskStatus.PENDING,
            created_at=datetime.now(timezone.utc),
        )

        self.active_tasks[task_id] = task
        self.task_queue.append(task_id)

        logger.info(f"Submitted collaborative task: {title} (ID: {task_id})")
        return task_id

    async def get_task_status(self, task_id: str) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
        """Get current status of a task"""
        if task_id in self.active_tasks:
            task = self.active_tasks[task_id]
            return {
                "task_id": task.task_id,
                "title": task.title,
                "status": task.status.value,
                "progress": task.progress_percentage,
                "assigned_agents": task.assigned_agents,
                "created_at": task.created_at.isoformat(),
            }
        elif task_id in self.completed_tasks:
            task = self.completed_tasks[task_id]
            return {
                "task_id": task.task_id,
                "title": task.title,
                "status": task.status.value,
                "progress": 100.0,
                "result": task.result,
                "created_at": task.created_at.isoformat(),
            }
        return None

    async def assign_task_to_agents(self, task_id: str, agent_ids: list[str]) -> bool:
        """Assign task to specific agents"""
        if task_id not in self.active_tasks:
            return False

        task = self.active_tasks[task_id]
        task.assigned_agents = agent_ids
        task.status = TaskStatus.ASSIGNED

        # Update agent workloads
        for agent_id in agent_ids:
            self.agent_workloads[agent_id] = self.agent_workloads.get(agent_id, 0) + 1

        logger.info(f"Assigned task {task_id} to agents: {agent_ids}")
        return True

    async def update_task_progress(
        self, task_id: str, progress: float, status: TaskStatus | None = None
    ) -> bool:
        """Update task progress"""
        if task_id not in self.active_tasks:
            return False

        task = self.active_tasks[task_id]
        task.progress_percentage = max(0, min(100, progress))

        if status:
            task.status = status

        logger.debug(f"Updated task {task_id} progress: {progress}%")
        return True

    async def complete_task(self, task_id: str, result: dict[str, Any]) -> bool:  # TODO(TYPE): replace Any with concrete type
        """Mark task as completed with result"""
        if task_id not in self.active_tasks:
            return False

        task = self.active_tasks[task_id]
        task.status = TaskStatus.COMPLETED
        task.progress_percentage = 100.0
        task.result = result

        # Move to completed tasks
        self.completed_tasks[task_id] = task
        del self.active_tasks[task_id]

        # Update agent workloads
        for agent_id in task.assigned_agents:
            if agent_id in self.agent_workloads:
                self.agent_workloads[agent_id] = max(0, self.agent_workloads[agent_id] - 1)

        # Add to history
        self.task_history.append(task_id)

        logger.info(f"Completed task: {task.title} (ID: {task_id})")
        return True

    async def fail_task(self, task_id: str, error_message: str) -> bool:
        """Mark task as failed"""
        if task_id not in self.active_tasks:
            return False

        task = self.active_tasks[task_id]
        task.status = TaskStatus.FAILED
        task.error_message = error_message

        # Move to completed tasks
        self.completed_tasks[task_id] = task
        del self.active_tasks[task_id]

        # Update agent workloads
        for agent_id in task.assigned_agents:
            if agent_id in self.agent_workloads:
                self.agent_workloads[agent_id] = max(0, self.agent_workloads[agent_id] - 1)

        logger.warning(f"Failed task: {task.title} (ID: {task_id}) - {error_message}")
        return True

    async def get_coordination_metrics(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get task coordination metrics"""
        total_tasks = len(self.active_tasks) + len(self.completed_tasks)
        completed_count = len(
            [t for t in self.completed_tasks.values() if t.status == TaskStatus.COMPLETED]
        )
        failed_count = len(
            [t for t in self.completed_tasks.values() if t.status == TaskStatus.FAILED]
        )

        return {
            "total_tasks": total_tasks,
            "active_tasks": len(self.active_tasks),
            "completed_tasks": completed_count,
            "failed_tasks": failed_count,
            "success_rate": (completed_count / total_tasks * 100) if total_tasks > 0 else 0,
            "agent_workloads": dict(self.agent_workloads),
            "queue_length": len(self.task_queue),
        }

    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a pending or assigned task"""
        if task_id not in self.active_tasks:
            return False

        task = self.active_tasks[task_id]
        if task.status in [TaskStatus.PENDING, TaskStatus.ASSIGNED]:
            task.status = TaskStatus.CANCELLED

            # Move to completed tasks
            self.completed_tasks[task_id] = task
            del self.active_tasks[task_id]

            # Remove from queue if present
            if task_id in self.task_queue:
                self.task_queue.remove(task_id)

            logger.info(f"Cancelled task: {task.title} (ID: {task_id})")
            return True

        return False

    def get_active_tasks(self) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get list of all active tasks"""
        return [
            {
                "task_id": task.task_id,
                "title": task.title,
                "status": task.status.value,
                "priority": task.priority.value,
                "progress": task.progress_percentage,
                "assigned_agents": task.assigned_agents,
                "created_at": task.created_at.isoformat(),
            }
            for task in self.active_tasks.values()
        ]


# Global coordinator instance
_global_coordinator: TaskCoordinator | None = None


def get_task_coordinator() -> TaskCoordinator:
    """Get global task coordinator instance"""
    global _global_coordinator
    if _global_coordinator is None:
        _global_coordinator = TaskCoordinator()
    return _global_coordinator


def create_task_coordinator() -> TaskCoordinator:
    """Create or reset global task coordinator"""
    global _global_coordinator
    _global_coordinator = TaskCoordinator()
    return _global_coordinator
