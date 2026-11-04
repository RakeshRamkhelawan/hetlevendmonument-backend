"""Unit tests for src.domains.tasks.repository.TaskRepository.

Covers:
- Transaction behavior (flush, no commit)
- Mandatory tenant_id injection on writes
- Tenant isolation on reads
- Rejection of conflicting or immutable tenant_id updates
"""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.tasks.models import Task
from src.domains.tasks.repository import TaskRepository


@pytest.fixture
def tenant_id() -> int:
    return 7


@pytest.fixture
def other_tenant_id() -> int:
    return 8


@pytest.fixture
def repository(db_session: AsyncSession, tenant_id: int) -> TaskRepository:
    return TaskRepository(db=db_session, tenant_id=tenant_id)


@pytest.fixture
def other_repository(db_session: AsyncSession, other_tenant_id: int) -> TaskRepository:
    return TaskRepository(db=db_session, tenant_id=other_tenant_id)


@pytest.mark.unit
class TestRepositoryTransactionBehavior:
    """Writes must flush, not commit."""

    @pytest.mark.asyncio
    async def test_create_uses_flush_not_commit(self, tenant_id: int) -> None:
        mock_db = MagicMock(spec=AsyncSession)
        flush_mock = AsyncMock()
        commit_mock = AsyncMock()
        refresh_mock = AsyncMock()
        object.__setattr__(mock_db, "flush", flush_mock)
        object.__setattr__(mock_db, "commit", commit_mock)
        object.__setattr__(mock_db, "refresh", refresh_mock)

        repo = TaskRepository(db=mock_db, tenant_id=tenant_id)
        await repo.create({"id": uuid4(), "title": "task"})

        flush_mock.assert_called_once()
        commit_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_uses_flush_not_commit(self, tenant_id: int) -> None:
        task = MagicMock(spec=Task)
        task.id = uuid4()
        task.tenant_id = tenant_id

        async def mock_execute(stmt: Any) -> MagicMock:
            result = MagicMock()
            result.scalars.return_value.first.return_value = task
            return result

        mock_db = MagicMock(spec=AsyncSession)
        execute_mock = AsyncMock(side_effect=mock_execute)
        flush_mock = AsyncMock()
        commit_mock = AsyncMock()
        refresh_mock = AsyncMock()
        object.__setattr__(mock_db, "execute", execute_mock)
        object.__setattr__(mock_db, "flush", flush_mock)
        object.__setattr__(mock_db, "commit", commit_mock)
        object.__setattr__(mock_db, "refresh", refresh_mock)

        repo = TaskRepository(db=mock_db, tenant_id=tenant_id)
        await repo.update(task.id, {"title": "updated"})

        flush_mock.assert_called_once()
        commit_mock.assert_not_called()


@pytest.mark.unit
class TestRepositoryTenantIsolation:
    """ADR-005: every read filters by tenant_id."""

    @pytest.mark.asyncio
    async def test_create_injects_tenant_id(self, repository: TaskRepository) -> None:
        task = await repository.create({"id": uuid4(), "title": "injected"})

        assert task.tenant_id == repository.tenant_id

    @pytest.mark.asyncio
    async def test_create_rejects_conflicting_tenant_id(
        self, repository: TaskRepository, other_tenant_id: int
    ) -> None:
        with pytest.raises(ValueError):
            await repository.create(
                {
                    "id": uuid4(),
                    "title": "conflict",
                    "tenant_id": other_tenant_id,
                }
            )

    @pytest.mark.asyncio
    async def test_get_filters_by_tenant_id(
        self,
        repository: TaskRepository,
        other_repository: TaskRepository,
        tenant_id: int,
        other_tenant_id: int,
    ) -> None:
        task_id = uuid4()
        await repository.create({"id": task_id, "title": "mine"})
        await other_repository.create({"id": uuid4(), "title": "theirs"})

        found = await repository.get(task_id)
        assert found is not None
        assert found.title == "mine"

        not_found = await other_repository.get(task_id)
        assert not_found is None

    @pytest.mark.asyncio
    async def test_list_returns_only_own_tenant_tasks(
        self,
        repository: TaskRepository,
        other_repository: TaskRepository,
    ) -> None:
        await repository.create({"id": uuid4(), "title": "a"})
        await repository.create({"id": uuid4(), "title": "b"})
        await other_repository.create({"id": uuid4(), "title": "c"})

        own = await repository.list()
        assert len(own) == 2
        assert all(t.tenant_id == repository.tenant_id for t in own)

    @pytest.mark.asyncio
    async def test_update_rejects_tenant_id_change(
        self, repository: TaskRepository, other_tenant_id: int
    ) -> None:
        task = await repository.create({"id": uuid4(), "title": "stable"})

        with pytest.raises(ValueError):
            await repository.update(task.id, {"tenant_id": other_tenant_id})

    @pytest.mark.asyncio
    async def test_delete_only_affects_own_tenant(
        self,
        repository: TaskRepository,
        other_repository: TaskRepository,
    ) -> None:
        task_id = uuid4()
        await repository.create({"id": task_id, "title": "delete-me"})

        assert await other_repository.delete(task_id) is False
        assert await repository.delete(task_id) is True


@pytest.mark.unit
class TestRepositoryQueryRendering:
    """Compiled SQL must contain the tenant filter."""

    @pytest.mark.asyncio
    async def test_get_query_includes_tenant_filter(self, tenant_id: int) -> None:
        captured: dict[str, Any] = {}

        async def mock_execute(stmt: Any) -> MagicMock:
            captured["stmt"] = stmt
            result = MagicMock()
            result.scalars.return_value.first.return_value = None
            return result

        mock_db = MagicMock(spec=AsyncSession)
        execute_mock = AsyncMock(side_effect=mock_execute)
        object.__setattr__(mock_db, "execute", execute_mock)

        repo = TaskRepository(db=mock_db, tenant_id=tenant_id)
        await repo.get(uuid4())

        compiled = captured["stmt"].compile(compile_kwargs={"literal_binds": True})
        rendered = str(compiled)
        assert "agentic_tasks.tenant_id" in rendered
        assert str(tenant_id) in rendered
