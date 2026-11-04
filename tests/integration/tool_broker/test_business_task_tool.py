"""Integration tests for governed business task tools via ToolBroker.

Uses a real PostgreSQL session to verify that create_task/list_tasks tools
actually persist and read rows in the tenant-isolated `agentic_tasks` table.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator
from contextlib import asynccontextmanager
from typing import Any
from unittest.mock import patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

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


def _make_tool_broker(db_session: AsyncSession, tenant_id: int) -> ToolBrokerService:
    """Build a ToolBrokerService whose business tools reuse the test session."""

    @asynccontextmanager
    async def _session_factory() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    def _service_factory(session: AsyncSession, t_id: int) -> TaskService:
        return TaskService(db=session, tenant_id=t_id)

    registry = BusinessToolRegistry(
        session_factory=_session_factory,
        task_service_factory=_service_factory,
    )

    return ToolBrokerService(
        serena_client=MockSerenaClient(),
        seq_thinking_client=MockSeqThinkingClient(),
        business_registry=registry,
        enable_resilience=False,
    )


@pytest.mark.asyncio
async def test_create_task_tool_persists_in_database(db_session: AsyncSession) -> None:
    tenant_id = 1
    set_tenant_id(tenant_id)
    broker = _make_tool_broker(db_session, tenant_id)

    result: dict[str, Any] = await broker.execute_tool(
        tool_name="create_task",
        payload={"title": "Integration create task"},
        agent_id="copilot",
        context={"tenant_id": tenant_id},
    )

    assert result["success"] is True
    data: dict[str, Any] = result["data"]
    assert data["title"] == "Integration create task"
    assert data["tenant_id"] == tenant_id
    assert data["status"] == "pending"

    # Verify directly via TaskService
    direct_service = TaskService(db=db_session, tenant_id=tenant_id)
    found = await direct_service.get(data["id"])
    assert found is not None
    assert found.title == "Integration create task"


@pytest.mark.asyncio
async def test_list_tasks_tool_returns_tenant_tasks(db_session: AsyncSession) -> None:
    tenant_id = 1
    set_tenant_id(tenant_id)
    direct_service = TaskService(db=db_session, tenant_id=tenant_id)

    created = await direct_service.create(
        TaskCreate(title="Task A", status="pending", priority="medium")
    )

    broker = _make_tool_broker(db_session, tenant_id)
    result: dict[str, Any] = await broker.execute_tool(
        tool_name="list_tasks",
        payload={"status": "pending"},
        agent_id="copilot",
        context={"tenant_id": tenant_id},
    )

    assert result["success"] is True
    assert result["count"] >= 1
    data: list[dict[str, Any]] = result["data"]
    ids = {item["id"] for item in data}
    assert created.id in ids


@pytest.mark.asyncio
async def test_create_task_tool_rejects_missing_tenant(db_session: AsyncSession) -> None:
    broker = ToolBrokerService(
        serena_client=MockSerenaClient(),
        seq_thinking_client=MockSeqThinkingClient(),
        enable_resilience=False,
    )

    with pytest.raises(ToolExecutionException) as exc_info:
        await broker.execute_tool(
            tool_name="create_task",
            payload={"title": "no tenant"},
            agent_id="copilot",
        )

    # De formulering is veranderd toen de tenant uit de EXECUTIECONTEXT ging komen in plaats van
    # uit de payload (ADR-036 OP-27, ronde 2). De eigenschap die deze test bewaakt -- zonder tenant
    # geen uitvoering -- is ongewijzigd; alleen de melding is preciezer geworden over de HERKOMST.
    # Op "execution context" toetsen en niet op de hele zin: dan blijft de test overeind bij een
    # herformulering, maar valt hij om zodra de payload weer als bron wordt geaccepteerd.
    assert "execution context" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_list_tasks_tool_isolates_tenants(db_session: AsyncSession) -> None:
    """A task created for tenant 1 must not appear in tenant 2's list."""
    tenant_a = 1
    tenant_b = 2

    set_tenant_id(tenant_a)
    service_a = TaskService(db=db_session, tenant_id=tenant_a)
    created = await service_a.create(
        TaskCreate(title="Tenant A task", status="pending", priority="medium")
    )

    broker_b = _make_tool_broker(db_session, tenant_b)
    result: dict[str, Any] = await broker_b.execute_tool(
        tool_name="list_tasks",
        payload={"status": "pending"},
        agent_id="copilot",
        context={"tenant_id": tenant_b},
    )

    assert result["success"] is True
    data: list[dict[str, Any]] = result["data"]
    ids = {item["id"] for item in data}
    assert created.id not in ids
