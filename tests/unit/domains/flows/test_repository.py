"""
Unit tests for src.domains.flows.repository.FlowRepository.

TDD: tests were RED before implementation and GREEN after.
Covers the critical fixes from FocusBuilder audit 2026-06-18:
- H-2: repository must flush, not commit
- H-4: repository must not expunge instances
"""

from __future__ import annotations

from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.domains.flows.models import Flow
from src.domains.flows.repository import FlowRepository


@pytest.fixture
def mock_db() -> Any:
    return MagicMock()


@pytest.fixture
def tenant_id() -> int:
    return 42


@pytest.fixture
def repository(mock_db: AsyncSession, tenant_id: int) -> FlowRepository:
    return FlowRepository(db=mock_db, tenant_id=tenant_id)


@pytest.mark.unit
class TestRepositoryTransactionBehavior:
    """H-2: writes must flush, not commit."""

    @pytest.mark.asyncio
    async def test_create_uses_flush_not_commit(
        self, repository: FlowRepository, mock_db: AsyncSession
    ) -> None:
        flush_mock = AsyncMock()
        commit_mock = AsyncMock()
        refresh_mock = AsyncMock()
        object.__setattr__(mock_db, "flush", flush_mock)
        object.__setattr__(mock_db, "commit", commit_mock)
        object.__setattr__(mock_db, "refresh", refresh_mock)

        await repository.create(
            {
                "name": "test-flow",
                "react_flow_graph": {"nodes": [], "edges": []},
            }
        )

        flush_mock.assert_called_once()
        commit_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_update_uses_flush_not_commit(
        self, repository: FlowRepository, mock_db: AsyncSession
    ) -> None:
        flow = MagicMock(spec=Flow)
        flow.id = 1
        flow.tenant_id = repository.tenant_id

        async def mock_execute(stmt: Any) -> MagicMock:
            result = MagicMock()
            result.scalars.return_value.first.return_value = flow
            return result

        execute_mock = AsyncMock(side_effect=mock_execute)
        flush_mock = AsyncMock()
        commit_mock = AsyncMock()
        refresh_mock = AsyncMock()
        object.__setattr__(mock_db, "execute", execute_mock)
        object.__setattr__(mock_db, "flush", flush_mock)
        object.__setattr__(mock_db, "commit", commit_mock)
        object.__setattr__(mock_db, "refresh", refresh_mock)

        await repository.update(1, {"name": "updated"})

        flush_mock.assert_called_once()
        commit_mock.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_uses_flush_not_commit(
        self, repository: FlowRepository, mock_db: AsyncSession
    ) -> None:
        flow = MagicMock(spec=Flow)
        flow.id = 1
        flow.tenant_id = repository.tenant_id

        async def mock_execute(stmt: Any) -> MagicMock:
            result = MagicMock()
            result.scalars.return_value.first.return_value = flow
            return result

        execute_mock = AsyncMock(side_effect=mock_execute)
        flush_mock = AsyncMock()
        commit_mock = AsyncMock()
        delete_mock = AsyncMock()
        object.__setattr__(mock_db, "execute", execute_mock)
        object.__setattr__(mock_db, "flush", flush_mock)
        object.__setattr__(mock_db, "commit", commit_mock)
        object.__setattr__(mock_db, "delete", delete_mock)

        await repository.delete(1)

        flush_mock.assert_called_once()
        commit_mock.assert_not_called()


@pytest.mark.unit
class TestRepositoryExpungeBehavior:
    """H-4: reads must not expunge instances."""

    @pytest.mark.asyncio
    async def test_get_does_not_expunge(
        self, repository: FlowRepository, mock_db: AsyncSession
    ) -> None:
        flow = MagicMock(spec=Flow)

        async def mock_execute(stmt: Any) -> MagicMock:
            result = MagicMock()
            result.scalars.return_value.first.return_value = flow
            return result

        execute_mock = AsyncMock(side_effect=mock_execute)
        object.__setattr__(mock_db, "execute", execute_mock)

        await repository.get(1)

        cast(AsyncMock, mock_db.expunge).assert_not_called()

    @pytest.mark.asyncio
    async def test_list_does_not_expunge(
        self, repository: FlowRepository, mock_db: AsyncSession
    ) -> None:
        flow = MagicMock(spec=Flow)

        async def mock_execute(stmt: Any) -> MagicMock:
            result = MagicMock()
            result.scalars.return_value.all.return_value = [flow]
            return result

        execute_mock = AsyncMock(side_effect=mock_execute)
        object.__setattr__(mock_db, "execute", execute_mock)

        await repository.list()

        cast(AsyncMock, mock_db.expunge).assert_not_called()


@pytest.mark.unit
class TestRepositoryTenantIsolation:
    """ADR-005: Flow queries must always filter by tenant_id."""

    @pytest.mark.asyncio
    async def test_create_injects_tenant_id(
        self, repository: FlowRepository, mock_db: AsyncSession
    ) -> None:
        flush_mock = AsyncMock()
        refresh_mock = AsyncMock()
        object.__setattr__(mock_db, "flush", flush_mock)
        object.__setattr__(mock_db, "refresh", refresh_mock)

        await repository.create(
            {
                "name": "test-flow",
                "react_flow_graph": {"nodes": [], "edges": []},
            }
        )

        call_args = cast(AsyncMock, mock_db.add).call_args[0][0]
        assert call_args.tenant_id == repository.tenant_id

    @pytest.mark.asyncio
    async def test_get_filters_by_tenant_id(
        self, repository: FlowRepository, mock_db: AsyncSession
    ) -> None:
        captured: dict[str, Any] = {}

        async def mock_execute(stmt: Any) -> MagicMock:
            captured["stmt"] = stmt
            result = MagicMock()
            result.scalars.return_value.first.return_value = None
            return result

        execute_mock = AsyncMock(side_effect=mock_execute)
        object.__setattr__(mock_db, "execute", execute_mock)

        await repository.get(1)

        compiled = captured["stmt"].compile(compile_kwargs={"literal_binds": True})
        rendered = str(compiled)
        assert "flows.tenant_id" in rendered
        assert str(repository.tenant_id) in rendered
