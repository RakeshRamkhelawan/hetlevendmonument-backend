"""Unit tests for governed muterende business task tools via ToolBroker.

Scope: update_task (medium) + delete_task (high -> HITL-gated). These tests mock
the database session, TaskService and HITL store to verify ToolBroker dispatch,
the HIGH-risk HITL gate, tenant propagation from context, and dag-3 regression
without requiring a real PostgreSQL instance.

Kern-rode test: 1.1 (delete zonder goedgekeurd ticket wordt geblokkeerd).
Cross-tenant isolatie (1.4) staat in de integratie-suite (echte RLS).
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator
from contextlib import asynccontextmanager
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.tool_broker.business_registry import BusinessToolRegistry
from src.core.tool_broker.exceptions import ToolExecutionException
from src.core.tool_broker.service import ToolBrokerService


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


def _make_registry(task_service: AsyncMock) -> BusinessToolRegistry:
    """Build a registry with an injected mock session and TaskService factory."""

    @asynccontextmanager
    async def _mock_session() -> AsyncGenerator[AsyncMock, None]:
        yield AsyncMock()

    def _mock_service_factory(session: AsyncMock, tenant_id: int) -> AsyncMock:
        return task_service

    return BusinessToolRegistry(
        session_factory=_mock_session,
        task_service_factory=cast(Any, _mock_service_factory),
    )


def _make_service(
    task_service: AsyncMock,
    hitl_approved: bool | None = None,
) -> ToolBrokerService:
    """ToolBrokerService with a mocked HITL store.

    hitl_approved=None  -> no hitl_store status mocking needed (medium-risk path)
    hitl_approved=True  -> get_approval_status returns "approved"
    hitl_approved=False -> get_approval_status returns "pending" (not approved)
    """
    hitl_store = AsyncMock()
    if hitl_approved is True:
        hitl_store.get_approval_status = AsyncMock(return_value="approved")
    elif hitl_approved is False:
        hitl_store.get_approval_status = AsyncMock(return_value="pending")

    return ToolBrokerService(
        serena_client=MockSerenaClient(),
        seq_thinking_client=MockSeqThinkingClient(),
        business_registry=_make_registry(task_service),
        enable_resilience=False,
        hitl_store=hitl_store,
    )


def _task_read_stub(**overrides: Any) -> MagicMock:
    base = {
        "id": str(uuid4()),
        "tenant_id": 1,
        "title": "mock task",
        "status": "pending",
        "priority": "medium",
    }
    base.update(overrides)
    stub = MagicMock()
    stub.model_dump = lambda: base
    return stub


class TestDeleteTaskHITLGate:
    """delete_task is HIGH risk and must pass the existing ToolBroker HITL gate."""

    @pytest.mark.asyncio
    async def test_delete_without_approved_ticket_is_blocked(self) -> None:
        """1.1 -- delete_task zonder goedgekeurd HITL-ticket wordt geblokkeerd (ROOD voor fix)."""
        task_service = AsyncMock()
        task_service.delete = AsyncMock(return_value=True)
        service = _make_service(task_service, hitl_approved=False)

        with pytest.raises(ToolExecutionException) as exc_info:
            await service.execute_tool(
                tool_name="delete_task",
                payload={"tenant_id": 1, "task_id": str(uuid4())},
                agent_id="copilot",
                context={"tenant_id": 1},
            )

        assert "human approval" in str(exc_info.value.detail)
        task_service.delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_with_approved_ticket_deletes_task(self) -> None:
        """1.2 -- delete_task MET goedgekeurd ticket verwijdert de taak via TaskService.delete."""
        task_service = AsyncMock()
        task_service.delete = AsyncMock(return_value=True)
        service = _make_service(task_service, hitl_approved=True)

        result = await service.execute_tool(
            tool_name="delete_task",
            payload={
                "tenant_id": 1,
                "task_id": str(uuid4()),
                "_hitl_ticket_ref": "TOOL-approved-001",
            },
            agent_id="copilot",
            context={"tenant_id": 1},
        )

        assert result["success"] is True
        assert result["data"]["deleted"] is True
        task_service.delete.assert_awaited_once()


class TestUpdateTaskStatus:
    """update_task is medium risk (no HITL) and dispatches to TaskService.update."""

    @pytest.mark.asyncio
    async def test_update_task_happy_path(self) -> None:
        """1.3 -- update_task werkt de status bij via TaskService.update."""
        task_service = AsyncMock()
        task_service.update = AsyncMock(return_value=_task_read_stub(status="completed"))
        service = _make_service(task_service)

        result = await service.execute_tool(
            tool_name="update_task",
            payload={"tenant_id": 1, "task_id": str(uuid4()), "status": "completed"},
            agent_id="copilot",
            context={"tenant_id": 1},
        )

        assert result["success"] is True
        assert result["data"]["status"] == "completed"
        task_service.update.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_update_missing_task_returns_structured_error(self) -> None:
        """update op onbestaande/andere-tenant taak -> gestructureerde fout, geen lek."""
        task_service = AsyncMock()
        task_service.update = AsyncMock(return_value=None)
        service = _make_service(task_service)

        with pytest.raises(ToolExecutionException):
            await service.execute_tool(
                tool_name="update_task",
                payload={"tenant_id": 1, "task_id": str(uuid4()), "status": "completed"},
                agent_id="copilot",
                context={"tenant_id": 1},
            )


class TestMutationTenantPropagation:
    """Tenant identity must come from context, never from user payload override."""

    @pytest.mark.asyncio
    async def test_update_payload_tenant_id_is_ignored(self) -> None:
        """1.5 -- payload tenant_id/id wordt genegeerd; context wint (SOUL-1)."""
        task_service = AsyncMock()
        task_service.update = AsyncMock(return_value=_task_read_stub(tenant_id=42))

        # Capture the tenant_id the registry passes to the TaskService factory so
        # we can assert context (42) beats the payload override (99) -- not tautological.
        seen_tenant_ids: list[int] = []

        @asynccontextmanager
        async def _mock_session() -> AsyncGenerator[AsyncMock, None]:
            yield AsyncMock()

        def _capturing_factory(session: AsyncMock, tenant_id: int) -> AsyncMock:
            seen_tenant_ids.append(tenant_id)
            return task_service

        registry = BusinessToolRegistry(
            session_factory=_mock_session,
            task_service_factory=cast(Any, _capturing_factory),
        )
        service = ToolBrokerService(
            serena_client=MockSerenaClient(),
            seq_thinking_client=MockSeqThinkingClient(),
            business_registry=registry,
            enable_resilience=False,
        )

        await service.execute_tool(
            tool_name="update_task",
            payload={
                "tenant_id": 99,  # override attempt
                "id": "999",  # injected id attempt
                "task_id": str(uuid4()),
                "status": "in_progress",
            },
            agent_id="copilot",
            context={"tenant_id": 42},
        )

        # Context tenant_id must win over the payload override.
        assert seen_tenant_ids == [42]
        # The TaskUpdate passed to service.update must not carry tenant_id or id.
        call = task_service.update.call_args
        data = call.args[1] if len(call.args) > 1 else call.kwargs.get("data")
        dumped = data.model_dump(exclude_unset=True)
        assert "tenant_id" not in dumped
        assert "id" not in dumped


class TestMutationRegressionDag3:
    """create_task/list_tasks (dag 3) must keep working unchanged."""

    @pytest.mark.asyncio
    async def test_create_task_still_works(self) -> None:
        """1.6 -- create_task blijft ongewijzigd werken."""
        task_service = AsyncMock()
        task_service.create = AsyncMock(return_value=_task_read_stub(title="Review Q3"))
        service = _make_service(task_service)

        result = await service.execute_tool(
            tool_name="create_task",
            payload={"tenant_id": 1, "title": "Review Q3"},
            agent_id="copilot",
            context={"tenant_id": 1},
        )

        assert result["success"] is True
        assert result["data"]["title"] == "Review Q3"

    @pytest.mark.asyncio
    async def test_list_tasks_still_works(self) -> None:
        """1.6 -- list_tasks blijft ongewijzigd werken."""
        task_service = AsyncMock()
        task_service.list = AsyncMock(return_value=[_task_read_stub()])
        service = _make_service(task_service)

        result = await service.execute_tool(
            tool_name="list_tasks",
            payload={"tenant_id": 1, "status": "pending"},
            agent_id="copilot",
            context={"tenant_id": 1},
        )

        assert result["success"] is True
        assert result["count"] == 1
