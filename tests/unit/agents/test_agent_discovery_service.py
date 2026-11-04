"""RED tests -- SP-AGT-002 Dag 5 -- AgentDiscoveryService AsyncSessionFactory migratie.

Tests are RED until:
1. get_async_session import is removed from src/core/agents/agent_discovery.py
2. async_session_factory parameter is added to AgentDiscoveryService.__init__
3. _session_scope raises RuntimeError when neither db_session nor factory is available
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_session_scope_raises_when_no_session_or_factory() -> None:
    """_session_scope must raise RuntimeError when neither db_session nor factory is provided.

    Before the fix: tries to call get_async_session() which requires DB connectivity.
    After the fix: raises RuntimeError immediately (fail-fast, no implicit DB import).
    """
    from src.core.agents.agent_discovery import AgentDiscoveryService

    svc = AgentDiscoveryService(tenant_id=42)

    with pytest.raises(RuntimeError, match="requires either db_session or async_session_factory"):
        async with svc._session_scope():
            pass


@pytest.mark.asyncio
async def test_session_scope_uses_injected_db_session() -> None:
    """_session_scope must yield the injected db_session when provided."""
    from src.core.agents.agent_discovery import AgentDiscoveryService

    mock_session = AsyncMock(spec=AsyncSession)
    svc = AgentDiscoveryService(tenant_id=42, db_session=mock_session)

    yielded: list[object] = []
    async with svc._session_scope() as session:
        yielded.append(session)

    assert len(yielded) == 1
    assert yielded[0] is mock_session


@pytest.mark.asyncio
async def test_session_scope_uses_factory_when_no_db_session() -> None:
    """_session_scope must call async_session_factory() when no db_session is provided."""
    from src.core.agents.agent_discovery import AgentDiscoveryService

    mock_session = AsyncMock(spec=AsyncSession)

    @asynccontextmanager
    async def mock_factory():
        yield mock_session

    svc = AgentDiscoveryService(tenant_id=42, async_session_factory=mock_factory)

    yielded: list[object] = []
    async with svc._session_scope() as session:
        yielded.append(session)

    assert len(yielded) == 1
    assert yielded[0] is mock_session


@pytest.mark.asyncio
async def test_find_agent_by_id_filters_on_tenant_id() -> None:
    """find_agent_by_id must include tenant_id in the WHERE clause (ADR-005 isolation)."""
    from src.core.agents.agent_discovery import AgentDiscoveryService

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.execute = AsyncMock(return_value=mock_result)

    svc = AgentDiscoveryService(tenant_id=42, db_session=mock_session)
    result = await svc.find_agent_by_id("agent-test")

    assert result is None
    stmt = mock_session.execute.call_args_list[0].args[0]
    where_str = str(stmt.whereclause).lower()
    assert "tenant_id" in where_str, (
        f"WHERE clause missing tenant_id -- cross-tenant data leak possible: {where_str}"
    )


@pytest.mark.asyncio
async def test_get_agents_by_department_filters_on_tenant_id() -> None:
    """get_agents_by_department must include tenant_id in the WHERE clause (ADR-005)."""
    from src.core.agents.agent_discovery import AgentDiscoveryService, DepartmentFilter

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.execute = AsyncMock(return_value=mock_result)

    svc = AgentDiscoveryService(tenant_id=42, db_session=mock_session)
    result = await svc.get_agents_by_department(DepartmentFilter.ALL)

    assert result == []
    stmt = mock_session.execute.call_args_list[0].args[0]
    where_str = str(stmt.whereclause).lower()
    assert "tenant_id" in where_str, (
        f"WHERE clause missing tenant_id -- cross-tenant data leak possible: {where_str}"
    )


@pytest.mark.asyncio
async def test_discover_all_agents_filters_on_tenant_id() -> None:
    """discover_all_agents must include tenant_id in the WHERE clause (ADR-005 isolation)."""
    from src.core.agents.agent_discovery import AgentDiscoveryService

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []

    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.execute = AsyncMock(return_value=mock_result)

    svc = AgentDiscoveryService(tenant_id=99, db_session=mock_session)
    result = await svc.discover_all_agents()

    assert isinstance(result, list)
    stmt = mock_session.execute.call_args_list[0].args[0]
    where_str = str(stmt.whereclause).lower()
    assert "tenant_id" in where_str, (
        f"WHERE clause missing tenant_id -- cross-tenant data leak possible: {where_str}"
    )


def test_agent_discovery_does_not_import_database_module() -> None:
    """agent_discovery.py must not directly import from src.core.database.database (ADR-034).

    This test reads the module source and asserts the forbidden import is absent.
    After the fix, get_async_session is injected via async_session_factory, never imported directly.
    """
    import src.core.agents.agent_discovery as discovery_module

    source_path = discovery_module.__file__
    assert source_path is not None, "Could not determine module source path"

    with open(source_path, encoding="utf-8") as fh:
        source = fh.read()

    forbidden = "from src.core.database.database import"
    assert forbidden not in source, (
        f"ADR-034 violation: agent_discovery.py contains forbidden import:\n"
        f"  '{forbidden}'\n"
        f"Fix: inject async_session_factory instead of importing get_async_session directly."
    )
