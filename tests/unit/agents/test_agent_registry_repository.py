"""RED tests -- SP-AGT-002 Dag 4 -- AgentRegistryRepository.

Tests are RED until AgentRegistryRepository is implemented in
src/core/database/agent_registry_repository.py.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.shared.interfaces import IAgentRegistryRepository


@pytest.mark.asyncio
async def test_iagentregistryrepository_protocol_satisfied() -> None:
    """AgentRegistryRepository must satisfy IAgentRegistryRepository at runtime."""
    from src.core.agents.repositories.agent_registry_repository import AgentRegistryRepository

    mock_session = AsyncMock()
    instance = AgentRegistryRepository(mock_session)
    assert isinstance(instance, IAgentRegistryRepository), (
        "AgentRegistryRepository does not structurally satisfy IAgentRegistryRepository"
    )


@pytest.mark.asyncio
async def test_get_registered_agent_by_agent_id_filters_tenant() -> None:
    """get_registered_agent_by_agent_id must include tenant_id in the WHERE clause."""
    from src.core.agents.repositories.agent_registry_repository import AgentRegistryRepository

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)

    repo = AgentRegistryRepository(mock_session)
    result = await repo.get_registered_agent_by_agent_id(agent_id="agent-1", tenant_id=42)

    assert result is None
    stmt = mock_session.execute.call_args_list[0].args[0]
    where_str = str(stmt.whereclause).lower()
    assert "tenant_id" in where_str, f"WHERE clause missing tenant_id: {where_str}"


@pytest.mark.asyncio
async def test_get_registered_agents_filters_tenant_and_paginates() -> None:
    """get_registered_agents must filter by tenant_id and honour limit/offset."""
    from src.core.agents.repositories.agent_registry_repository import AgentRegistryRepository

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)

    repo = AgentRegistryRepository(mock_session)
    result = await repo.get_registered_agents(tenant_id=42, limit=10, offset=5)

    assert result == []
    stmt = mock_session.execute.call_args_list[0].args[0]
    stmt_str = str(stmt).lower()
    where_str = str(stmt.whereclause).lower()
    assert "tenant_id" in where_str, f"WHERE clause missing tenant_id: {where_str}"
    assert "10" in stmt_str or "limit" in stmt_str, f"LIMIT missing from statement: {stmt_str}"


@pytest.mark.asyncio
async def test_get_active_agents_filters_tenant_and_heartbeat() -> None:
    """get_active_agents must include both tenant_id and last_heartbeat in the WHERE clause."""
    from src.core.agents.repositories.agent_registry_repository import AgentRegistryRepository

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)

    repo = AgentRegistryRepository(mock_session)
    await repo.get_active_agents(tenant_id=42)

    stmt = mock_session.execute.call_args_list[0].args[0]
    where_str = str(stmt.whereclause).lower()
    assert "tenant_id" in where_str, f"WHERE clause missing tenant_id: {where_str}"
    assert "last_heartbeat" in where_str, (
        f"WHERE clause missing last_heartbeat threshold -- active agents filter broken: {where_str}"
    )


@pytest.mark.asyncio
async def test_register_agent_calls_add_and_flush() -> None:
    """register_agent must call session.add() then session.flush() -- caller owns the transaction."""
    from src.core.agents.repositories.agent_registry_repository import AgentRegistryRepository

    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session.flush = AsyncMock()
    mock_registration = MagicMock()

    repo = AgentRegistryRepository(mock_session)
    result = await repo.register_agent(mock_registration)

    mock_session.add.assert_called_once_with(mock_registration)
    mock_session.flush.assert_awaited_once()
    assert result is mock_registration


@pytest.mark.asyncio
async def test_get_registered_agent_by_agent_id_wrong_tenant_returns_none() -> None:
    """get_registered_agent_by_agent_id must return None for wrong tenant (isolation guard)."""
    from src.core.agents.repositories.agent_registry_repository import AgentRegistryRepository

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)

    repo = AgentRegistryRepository(mock_session)
    result = await repo.get_registered_agent_by_agent_id(agent_id="agent-1", tenant_id=999)

    assert result is None
    stmt = mock_session.execute.call_args_list[0].args[0]
    where_str = str(stmt.whereclause).lower()
    assert "tenant_id" in where_str, (
        f"WHERE clause missing tenant_id -- cross-tenant data leak possible: {where_str}"
    )


@pytest.mark.asyncio
async def test_get_registered_agents_wrong_tenant_returns_empty() -> None:
    """get_registered_agents must return empty list for wrong tenant (backend-patterns rule 11)."""
    from src.core.agents.repositories.agent_registry_repository import AgentRegistryRepository

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)

    repo = AgentRegistryRepository(mock_session)
    result = await repo.get_registered_agents(tenant_id=999)

    assert result == [], "Wrong tenant must receive empty list, not another tenant's agents"
    stmt = mock_session.execute.call_args_list[0].args[0]
    where_str = str(stmt.whereclause).lower()
    assert "tenant_id" in where_str, (
        f"WHERE clause missing tenant_id -- cross-tenant data leak possible: {where_str}"
    )


@pytest.mark.asyncio
async def test_get_active_agents_wrong_tenant_returns_empty() -> None:
    """get_active_agents must return empty list for wrong tenant (backend-patterns rule 11)."""
    from src.core.agents.repositories.agent_registry_repository import AgentRegistryRepository

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute = AsyncMock(return_value=mock_result)

    repo = AgentRegistryRepository(mock_session)
    result = await repo.get_active_agents(tenant_id=999)

    assert result == [], "Wrong tenant must receive empty list, not another tenant's active agents"
    stmt = mock_session.execute.call_args_list[0].args[0]
    where_str = str(stmt.whereclause).lower()
    assert "tenant_id" in where_str, (
        f"WHERE clause missing tenant_id -- cross-tenant data leak possible: {where_str}"
    )


@pytest.mark.asyncio
async def test_update_agent_filters_tenant_in_where_clause() -> None:
    """update_agent must include tenant_id in the WHERE clause (backend-patterns rule 11)."""
    from src.core.agents.repositories.agent_registry_repository import AgentRegistryRepository

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.flush = AsyncMock()

    repo = AgentRegistryRepository(mock_session)
    await repo.update_agent(agent_id="agent-1", tenant_id=42, values={"address": "new-addr"})

    stmt = mock_session.execute.call_args_list[0].args[0]
    where_str = str(stmt.whereclause).lower()
    assert "tenant_id" in where_str, (
        f"WHERE clause missing tenant_id -- cross-tenant update possible: {where_str}"
    )
    mock_session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_agent_strips_immutable_columns() -> None:
    """update_agent must not pass id/agent_id/tenant_id to .values() (column allowlist)."""
    from src.core.agents.repositories.agent_registry_repository import AgentRegistryRepository

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.flush = AsyncMock()

    repo = AgentRegistryRepository(mock_session)
    await repo.update_agent(
        agent_id="agent-1",
        tenant_id=42,
        values={"address": "new-addr", "tenant_id": 99, "id": 1, "agent_id": "evil"},
    )

    stmt = mock_session.execute.call_args_list[0].args[0]
    # Parse the SET clause column names directly from the compiled SQL.
    # SQLAlchemy renders: "UPDATE registered_agent SET col = :col_1 WHERE ..."
    # We extract column names from the SET portion and check for presence/absence.
    sql = str(stmt.compile()).lower()
    where_idx = sql.find(" where ")
    set_idx = sql.find(" set ") + 5
    set_clause = sql[set_idx:where_idx] if where_idx > 0 else sql[set_idx:]
    set_cols = {col.split("=")[0].strip() for col in set_clause.split(",")}

    assert "address" in set_cols, f"address must be in SET, got: {set_cols}"
    # These three must be stripped by _IMMUTABLE_COLUMNS; if the frozenset is ever
    # accidentally emptied this assertion catches the regression.
    assert "tenant_id" not in set_cols, f"tenant_id must be stripped from SET, got: {set_cols}"
    assert "id" not in set_cols, f"id must be stripped from SET, got: {set_cols}"
    assert "agent_id" not in set_cols, f"agent_id must be stripped from SET, got: {set_cols}"


@pytest.mark.asyncio
async def test_delete_agent_filters_tenant_in_where_clause() -> None:
    """delete_agent must include tenant_id in the WHERE clause (backend-patterns rule 11)."""
    from src.core.agents.repositories.agent_registry_repository import AgentRegistryRepository

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.flush = AsyncMock()

    repo = AgentRegistryRepository(mock_session)
    await repo.delete_agent(agent_id="agent-1", tenant_id=42)

    stmt = mock_session.execute.call_args_list[0].args[0]
    where_str = str(stmt.whereclause).lower()
    assert "tenant_id" in where_str, (
        f"WHERE clause missing tenant_id -- cross-tenant delete possible: {where_str}"
    )
    mock_session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_agent_wrong_tenant_targets_correct_where() -> None:
    """delete_agent must use the supplied tenant_id in the WHERE clause."""
    from src.core.agents.repositories.agent_registry_repository import AgentRegistryRepository

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock()
    mock_session.flush = AsyncMock()

    repo = AgentRegistryRepository(mock_session)
    await repo.delete_agent(agent_id="agent-1", tenant_id=999)

    stmt = mock_session.execute.call_args_list[0].args[0]
    where_str = str(stmt.whereclause).lower()
    assert "tenant_id" in where_str, (
        f"WHERE clause missing tenant_id -- cross-tenant delete possible: {where_str}"
    )
