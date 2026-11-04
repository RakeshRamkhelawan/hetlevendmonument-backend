"""Thin service layer for agentic task management."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.tasks.models import Task
from src.domains.tasks.repository import TaskRepository
from src.domains.tasks.schemas import TaskCreate, TaskRead, TaskUpdate


class TaskService:
    """
    Service for managing agentic tasks.

    The service is intentionally thin: it validates input schemas, delegates
    persistence to ``TaskRepository``, and never derives the tenant from user
    input. All reads are tenant-isolated by construction.
    """

    def __init__(self, db: AsyncSession, tenant_id: int) -> None:
        self.db = db
        self.tenant_id = tenant_id
        self.repository = TaskRepository(db, tenant_id)

    async def create(self, data: TaskCreate) -> TaskRead:
        """Create a new task for this tenant."""
        task = await self.repository.create(
            data.model_dump(exclude_unset=True, exclude={"tenant_id", "id"})
        )
        await self.db.commit()
        await self.db.refresh(task)
        return TaskRead.model_validate(task)

    async def get(self, task_id: UUID) -> TaskRead | None:
        """Fetch a single task by ID if it belongs to this tenant."""
        task = await self.repository.get(task_id)
        if task is None:
            return None
        return TaskRead.model_validate(task)

    async def list(
        self,
        status: str | None = None,
        assigned_agent_id: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[TaskRead]:
        """List tasks for this tenant."""
        tasks = await self.repository.list(
            status=status,
            assigned_agent_id=assigned_agent_id,
            skip=skip,
            limit=limit,
        )
        return [TaskRead.model_validate(task) for task in tasks]

    async def update(self, task_id: UUID, data: TaskUpdate) -> TaskRead | None:
        """Update an existing task."""
        task = await self.repository.update(
            task_id, data.model_dump(exclude_unset=True, exclude={"tenant_id", "id"})
        )
        if task is None:
            return None
        await self.db.commit()
        await self.db.refresh(task)
        return TaskRead.model_validate(task)

    async def delete(self, task_id: UUID) -> bool:
        """Delete a task if it belongs to this tenant."""
        deleted = await self.repository.delete(task_id)
        if deleted:
            await self.db.commit()
        return deleted
