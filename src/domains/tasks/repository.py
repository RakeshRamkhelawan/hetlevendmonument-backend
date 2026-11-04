"""Tenant-isolated repository for agentic tasks."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.tasks.models import Task


class TaskRepository:
    """
    Repository for accessing agentic task data with mandatory tenant isolation.

    Every read method filters on the ``tenant_id`` supplied at construction
    time. The repository never falls back to a default or ``None`` tenant.
    """

    def __init__(self, db: AsyncSession, tenant_id: int) -> None:
        self.db = db
        self.tenant_id = tenant_id

    async def get(self, task_id: UUID) -> Task | None:
        """Get a task by ID, scoped to the repository tenant."""
        result = await self.db.execute(
            select(Task).filter(
                Task.id == task_id,
                Task.tenant_id == self.tenant_id,
            )
        )
        return result.scalars().first()

    async def list(
        self,
        status: str | None = None,
        assigned_agent_id: str | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[Task]:
        """List tasks for this tenant, optionally filtered."""
        query = select(Task).filter(Task.tenant_id == self.tenant_id)

        if status is not None:
            query = query.filter(Task.status == status)
        if assigned_agent_id is not None:
            query = query.filter(Task.assigned_agent_id == assigned_agent_id)

        query = query.order_by(desc(Task.updated_at)).offset(skip).limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def create(
        self,
        data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> Task:
        """Create a new task. The supplied ``tenant_id`` is always overwritten."""
        if "tenant_id" in data and data["tenant_id"] != self.tenant_id:
            raise ValueError("tenant_id in data conflicts with repository tenant")

        data["tenant_id"] = self.tenant_id
        task = Task(**data)
        self.db.add(task)
        await self.db.flush()
        await self.db.refresh(task)
        return task

    async def update(
        self,
        task_id: UUID,
        data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> Task | None:
        """Update an existing task, but never its tenant."""
        task = await self.get(task_id)
        if task is None:
            return None

        if "tenant_id" in data:
            raise ValueError("tenant_id cannot be changed")

        for key, value in data.items():
            if hasattr(task, key):
                setattr(task, key, value)

        await self.db.flush()
        await self.db.refresh(task)
        return task

    async def delete(self, task_id: UUID) -> bool:
        """Delete a task if it belongs to this tenant."""
        task = await self.get(task_id)
        if task is None:
            return False

        await self.db.delete(task)
        await self.db.flush()
        return True
