"""Integration tests for muterende business task tools against real PostgreSQL.

Verifies that update_task/delete_task actually mutate the tenant-isolated
`agentic_tasks` table (RLS), that cross-tenant mutations are impossible, and that
each action writes an ADR-019 audit-hash-chain entry to `audit_logs`.

The HITL gate itself is unit-tested; here the approved-ticket state is mocked so
the focus stays on real DB behaviour and the audit chain.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.governance.models import AuditLog
from src.core.middleware.tenant_context import set_tenant_id
from src.core.tool_broker.business_registry import BusinessToolRegistry
from src.core.tool_broker.exceptions import ToolExecutionException
from src.core.tool_broker.service import ToolBrokerService
from src.domains.tasks.schemas import TaskCreate
from src.domains.tasks.service import TaskService


class MockSerenaClient:
    async def call(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {"result": "serena_ok"}


class MockSeqThinkingClient:
    async def call(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {"result": "thinking_ok"}


@pytest.fixture(autouse=True)
def _allow_all_tools() -> Iterator[None]:
    with patch(
        "src.core.tool_broker.service.ToolPermissionManager.is_tool_allowed",
        return_value=True,
    ):
        yield


def _make_tool_broker(db_session: AsyncSession) -> ToolBrokerService:
    @asynccontextmanager
    async def _session_factory() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    def _service_factory(session: AsyncSession, t_id: int) -> TaskService:
        return TaskService(db=session, tenant_id=t_id)

    registry = BusinessToolRegistry(
        session_factory=_session_factory,
        task_service_factory=_service_factory,
    )
    hitl_store = AsyncMock()
    hitl_store.get_approval_status = AsyncMock(return_value="approved")
    return ToolBrokerService(
        serena_client=MockSerenaClient(),
        seq_thinking_client=MockSeqThinkingClient(),
        business_registry=registry,
        enable_resilience=False,
        hitl_store=hitl_store,
    )


@pytest.mark.asyncio
async def test_update_task_tool_persists_status(db_session: AsyncSession) -> None:
    tenant_id = 1
    set_tenant_id(tenant_id)
    direct = TaskService(db=db_session, tenant_id=tenant_id)
    created = await direct.create(TaskCreate(title="Update me", status="pending"))

    broker = _make_tool_broker(db_session)
    result: dict[str, Any] = await broker.execute_tool(
        tool_name="update_task",
        payload={"task_id": str(created.id), "status": "completed"},
        agent_id="copilot",
        context={"tenant_id": tenant_id},
    )

    assert result["success"] is True
    assert result["data"]["status"] == "completed"
    reloaded = await direct.get(created.id)
    assert reloaded is not None
    assert reloaded.status == "completed"


@pytest.mark.asyncio
async def test_delete_task_tool_removes_row(db_session: AsyncSession) -> None:
    tenant_id = 1
    set_tenant_id(tenant_id)
    direct = TaskService(db=db_session, tenant_id=tenant_id)
    created = await direct.create(TaskCreate(title="Delete me", status="pending"))

    broker = _make_tool_broker(db_session)
    result: dict[str, Any] = await broker.execute_tool(
        tool_name="delete_task",
        payload={"task_id": str(created.id), "_hitl_ticket_ref": "TOOL-approved-int"},
        agent_id="copilot",
        context={"tenant_id": tenant_id},
    )

    assert result["success"] is True
    assert result["data"]["deleted"] is True
    assert await direct.get(created.id) is None


@pytest.mark.asyncio
async def test_cross_tenant_delete_does_not_leak(db_session: AsyncSession) -> None:
    """1.4 -- tenant B kan een taak van tenant A niet verwijderen (RLS)."""
    tenant_a, tenant_b = 1, 2
    set_tenant_id(tenant_a)
    service_a = TaskService(db=db_session, tenant_id=tenant_a)
    created = await service_a.create(TaskCreate(title="Tenant A only", status="pending"))

    broker_b = _make_tool_broker(db_session)
    result: dict[str, Any] = await broker_b.execute_tool(
        tool_name="delete_task",
        payload={"task_id": str(created.id), "_hitl_ticket_ref": "TOOL-approved-int"},
        agent_id="copilot",
        context={"tenant_id": tenant_b},
    )

    assert result["data"]["deleted"] is False
    set_tenant_id(tenant_a)
    assert await service_a.get(created.id) is not None


@pytest.mark.asyncio
async def test_cross_tenant_update_raises(db_session: AsyncSession) -> None:
    """1.4 -- tenant B kan een taak van tenant A niet bijwerken."""
    tenant_a, tenant_b = 1, 2
    set_tenant_id(tenant_a)
    service_a = TaskService(db=db_session, tenant_id=tenant_a)
    created = await service_a.create(TaskCreate(title="A owned", status="pending"))

    broker_b = _make_tool_broker(db_session)
    with pytest.raises(ToolExecutionException):
        await broker_b.execute_tool(
            tool_name="update_task",
            payload={"task_id": str(created.id), "status": "completed"},
            agent_id="copilot",
            context={"tenant_id": tenant_b},
        )


@pytest.mark.asyncio
async def test_create_writes_audit_hash_chain_entry(db_session: AsyncSession) -> None:
    """2.1 -- create_task schrijft een audit_logs entry met gezette audit_hash (ADR-019)."""
    tenant_id = 1
    set_tenant_id(tenant_id)
    broker = _make_tool_broker(db_session)

    await broker.execute_tool(
        tool_name="create_task",
        payload={"title": "Audited integration task"},
        agent_id="copilot",
        context={"tenant_id": tenant_id},
    )

    rows = (
        (
            await db_session.execute(
                select(AuditLog)
                .where(AuditLog.tenant_id == tenant_id)
                .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
                .limit(5)
            )
        )
        .scalars()
        .all()
    )
    task_entries = [r for r in rows if "task" in (r.action or "").lower()]
    assert task_entries, "verwacht minstens een task-audit entry"
    assert task_entries[0].audit_hash is not None
