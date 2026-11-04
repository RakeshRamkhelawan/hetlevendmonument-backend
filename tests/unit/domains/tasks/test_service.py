"""Unit tests for src.domains.tasks.service.TaskService."""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.tasks.schemas import TaskCreate, TaskUpdate
from src.domains.tasks.service import TaskService


@pytest.fixture
def tenant_id() -> int:
    return 7


@pytest.fixture
def other_tenant_id() -> int:
    return 8


@pytest.fixture
def service(db_session: AsyncSession, tenant_id: int) -> TaskService:
    return TaskService(db=db_session, tenant_id=tenant_id)


@pytest.fixture
def other_service(db_session: AsyncSession, other_tenant_id: int) -> TaskService:
    return TaskService(db=db_session, tenant_id=other_tenant_id)


@pytest.mark.unit
class TestTaskServiceCrud:
    """Happy path CRUD through the service layer."""

    @pytest.mark.asyncio
    async def test_create_task_sets_tenant_and_defaults(
        self, service: TaskService, tenant_id: int
    ) -> None:
        created = await service.create(TaskCreate(title="review audit"))

        assert created.tenant_id == tenant_id
        assert created.title == "review audit"
        assert created.status == "pending"
        assert created.priority == "medium"

    @pytest.mark.asyncio
    async def test_get_returns_own_task(self, service: TaskService) -> None:
        created = await service.create(TaskCreate(title="find me"))

        found = await service.get(created.id)
        assert found is not None
        assert found.title == "find me"

    @pytest.mark.asyncio
    async def test_get_returns_none_for_other_tenant(
        self, service: TaskService, other_service: TaskService
    ) -> None:
        created = await service.create(TaskCreate(title="private"))

        assert await other_service.get(created.id) is None

    @pytest.mark.asyncio
    async def test_list_filters_by_tenant(
        self, service: TaskService, other_service: TaskService
    ) -> None:
        await service.create(TaskCreate(title="one"))
        await service.create(TaskCreate(title="two"))
        await other_service.create(TaskCreate(title="three"))

        items = await service.list()
        assert len(items) == 2
        assert all(i.tenant_id == service.tenant_id for i in items)

    @pytest.mark.asyncio
    async def test_update_task(self, service: TaskService) -> None:
        created = await service.create(TaskCreate(title="old"))

        updated = await service.update(created.id, TaskUpdate(title="new", status="in_progress"))
        assert updated is not None
        assert updated.title == "new"
        assert updated.status == "in_progress"

    @pytest.mark.asyncio
    async def test_delete_task(self, service: TaskService) -> None:
        created = await service.create(TaskCreate(title="remove"))

        assert await service.delete(created.id) is True
        assert await service.get(created.id) is None


@pytest.mark.unit
class TestTaskServiceStatusFilter:
    """Optional filters are applied without leaking across tenants."""

    @pytest.mark.asyncio
    async def test_list_status_filter(self, service: TaskService) -> None:
        await service.create(TaskCreate(title="pending task"))
        await service.create(TaskCreate(title="in-progress task", status="in_progress"))

        pending = await service.list(status="pending")
        assert len(pending) == 1
        assert pending[0].status == "pending"
