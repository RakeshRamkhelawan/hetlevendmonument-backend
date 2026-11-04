from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
import uuid

import pytest

from src.core.company.external_agent_service import ExternalAgentService


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_pending_tasks_captures_query_with_tenant_isolation() -> None:
    """Verify that ExternalAgentService._get_pending_tasks builds a query with tenant_id isolation."""
    agent_id = uuid.uuid4()
    tenant_id = 42

    service = ExternalAgentService(
        db_manager=MagicMock(),
        tenant_context=None,
        policy_engine=None,
        budget_manager=None,
    )

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_session.execute.return_value = mock_result

    await service._get_pending_tasks(mock_session, agent_id=agent_id, tenant_id=tenant_id, limit=5)

    assert mock_session.execute.called
    stmt = mock_session.execute.call_args[0][0]
    compiled = str(stmt.compile())

    assert "tasks.tenant_id =" in compiled
    assert "tasks.assigned_agent_id =" in compiled


@pytest.mark.unit
@pytest.mark.asyncio
async def test_reschedule_orphaned_tasks_captures_update_with_tenant_isolation() -> None:
    """Verify that ExternalAgentService._reschedule_orphaned_tasks builds an update with tenant_id isolation."""
    agent_id = uuid.uuid4()
    tenant_id = 42

    service = ExternalAgentService(
        db_manager=MagicMock(),
        tenant_context=None,
        policy_engine=None,
        budget_manager=None,
    )

    mock_session = AsyncMock()

    await service._reschedule_orphaned_tasks(mock_session, agent_id=agent_id, tenant_id=tenant_id)

    assert mock_session.execute.called
    stmt = mock_session.execute.call_args[0][0]
    compiled = str(stmt.compile())

    assert "tasks.tenant_id =" in compiled
    assert "tasks.assigned_agent_id =" in compiled


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cancel_pending_tasks_captures_update_with_tenant_isolation() -> None:
    """Verify that ExternalAgentService._cancel_pending_tasks builds an update with tenant_id isolation."""
    agent_id = uuid.uuid4()
    tenant_id = 42

    service = ExternalAgentService(
        db_manager=MagicMock(),
        tenant_context=None,
        policy_engine=None,
        budget_manager=None,
    )

    mock_session = AsyncMock()

    await service._cancel_pending_tasks(mock_session, agent_id=agent_id, tenant_id=tenant_id)

    assert mock_session.execute.called
    stmt = mock_session.execute.call_args[0][0]
    compiled = str(stmt.compile())

    assert "tasks.tenant_id =" in compiled
    assert "tasks.assigned_agent_id =" in compiled
