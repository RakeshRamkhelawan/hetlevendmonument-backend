"""Tenant isolation tests -- SP-AGT-002 Dag 3 -- AgentRepository.

Verifies that every AgentRepository method includes tenant_id in the WHERE clause.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock

from src.core.agents.repositories.agent_repository import AgentRepository


@pytest.mark.asyncio
async def test_get_agents_by_tenant_filters_correctly() -> None:
    """AgentRepository.get_agents_by_tenant must filter by tenant_id in the WHERE clause."""
    mock_session = AsyncMock()

    mock_result_t1 = MagicMock()
    mock_result_t1.scalars.return_value.all.return_value = [MagicMock(tenant_id=1, id=10)]

    mock_result_t2 = MagicMock()
    mock_result_t2.scalars.return_value.all.return_value = []

    mock_session.execute = AsyncMock(side_effect=[mock_result_t1, mock_result_t2])

    repo = AgentRepository(mock_session)

    agents_t1 = await repo.get_agents_by_tenant(tenant_id=1)
    agents_t2 = await repo.get_agents_by_tenant(tenant_id=2)

    assert len(agents_t1) == 1, "Tenant 1 must see its own agents"
    assert len(agents_t2) == 0, "Tenant 2 must not see tenant 1 agents"

    assert mock_session.execute.call_count == 2
    stmt_t1 = mock_session.execute.call_args_list[0].args[0]
    stmt_t2 = mock_session.execute.call_args_list[1].args[0]
    where_t1 = str(stmt_t1.whereclause)
    where_t2 = str(stmt_t2.whereclause)
    assert "tenant_id" in where_t1.lower(), (
        f"WHERE clause for tenant 1 missing tenant_id: {where_t1}"
    )
    assert "tenant_id" in where_t2.lower(), (
        f"WHERE clause for tenant 2 missing tenant_id: {where_t2}"
    )


@pytest.mark.asyncio
async def test_get_agent_by_id_wrong_tenant_returns_none() -> None:
    """get_agent_by_id must return None if tenant_id does not match (FA-004).

    The WHERE clause must include tenant_id so that an agent owned by tenant A
    is invisible to tenant B even when the agent surrogate PK is known.
    """
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_session.execute = AsyncMock(return_value=mock_result)

    repo = AgentRepository(mock_session)
    result = await repo.get_agent_by_id(agent_id=42, tenant_id=999)

    assert result is None, "get_agent_by_id must return None for wrong tenant"

    stmt = mock_session.execute.call_args_list[0].args[0]
    where_str = str(stmt.whereclause)
    assert "tenant_id" in where_str.lower(), (
        f"WHERE clause missing tenant_id -- cross-tenant data leak possible: {where_str}"
    )
