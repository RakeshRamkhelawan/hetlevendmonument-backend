"""Unit tests for governed business task tools via ToolBroker.

Scope: create_task + list_tasks. These tests mock the database session and
TaskService to verify ToolBroker dispatch, tenant propagation, and fail-secure
behaviour without requiring a real PostgreSQL instance.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from collections.abc import Iterator
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

# Deze tests voeren echt een tool uit en hebben dus een tenant in de executiecontext
# nodig (ADR-036 OP-27: de pseudonimiseringsscope van de payload hangt eraan).
from tests.fixtures.tool_execution_tenant import tool_execution_tenant  # noqa: F401

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


def _make_registry(task_service: AsyncMock | None = None) -> BusinessToolRegistry:
    """Build a registry with an injected mock session and TaskService factory."""

    @asynccontextmanager
    async def _mock_session() -> AsyncGenerator[AsyncMock, None]:
        yield AsyncMock()

    def _mock_service_factory(session: AsyncMock, tenant_id: int) -> AsyncMock:
        svc = task_service or AsyncMock()
        if task_service is None:
            svc.create.return_value = MagicMock(
                model_dump=lambda: {
                    "id": "123e4567-e89b-12d3-a456-426614174000",
                    "tenant_id": tenant_id,
                    "title": "mock task",
                    "status": "pending",
                    "priority": "medium",
                    "description": None,
                    "created_by": None,
                    "assigned_agent_id": None,
                    "payload": None,
                    "result": None,
                    "parent_task_id": None,
                    "external_ref": None,
                    "due_at": None,
                    "created_at": "2026-07-06T00:00:00+00:00",
                    "updated_at": "2026-07-06T00:00:00+00:00",
                }
            )
            svc.list.return_value = [svc.create.return_value]
        return svc

    return BusinessToolRegistry(
        session_factory=_mock_session,
        task_service_factory=cast(Any, _mock_service_factory),
    )


def _make_service(registry: BusinessToolRegistry | None = None) -> ToolBrokerService:
    return ToolBrokerService(
        serena_client=MockSerenaClient(),
        seq_thinking_client=MockSeqThinkingClient(),
        business_registry=registry or _make_registry(),
        enable_resilience=False,
    )


class TestBusinessTaskToolCategory:
    """Verify the business-tool category is recognized and isolated."""

    @pytest.mark.asyncio
    async def test_unknown_business_tool_still_rejected(self) -> None:
        """A tool that is neither a known prefix nor a business tool must be rejected."""
        service = _make_service()

        with pytest.raises(ToolExecutionException) as exc_info:
            await service.execute_tool(
                tool_name="archive_task",  # not a registered business tool
                payload={"tenant_id": 1, "title": "x"},
                agent_id="copilot",
                context={"tenant_id": 1},
            )

        assert "Unknown tool category" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_create_task_is_recognized_after_fix(self) -> None:
        """create_task must be accepted and routed to the business registry."""
        service = _make_service()

        result: dict[str, Any] = await service.execute_tool(
            tool_name="create_task",
            payload={"tenant_id": 1, "title": "Review Q3 audit"},
            agent_id="copilot",
            context={"tenant_id": 1},
        )

        assert result["success"] is True
        assert result["data"]["title"] == "mock task"

    @pytest.mark.asyncio
    async def test_list_tasks_is_recognized_after_fix(self) -> None:
        """list_tasks must be accepted and return a list."""
        service = _make_service()

        result: dict[str, Any] = await service.execute_tool(
            tool_name="list_tasks",
            payload={"tenant_id": 1, "status": "pending"},
            agent_id="copilot",
            context={"tenant_id": 1},
        )

        assert result["success"] is True
        assert result["count"] == 1
        assert isinstance(result["data"], list)


class TestBusinessTaskToolTenantPropagation:
    """Tenant identity must come from context, never from user payload override."""

    @pytest.mark.asyncio
    async def test_create_task_uses_context_tenant_id(self) -> None:
        """Context tenant_id must always win over a tenant_id supplied in payload."""
        task_service = AsyncMock()
        task_service.create.return_value = MagicMock(model_dump=lambda: {"tenant_id": 42})
        registry = _make_registry(task_service=task_service)
        service = _make_service(registry=registry)

        result: dict[str, Any] = await service.execute_tool(
            tool_name="create_task",
            payload={"tenant_id": 99, "title": "x"},  # payload override attempt
            agent_id="copilot",
            context={"tenant_id": 42},
        )

        call_kwargs = task_service.create.call_args.kwargs
        assert "tenant_id" not in call_kwargs
        assert task_service.create.call_count == 1
        assert result["data"]["tenant_id"] == 42

    @pytest.mark.asyncio
    async def test_missing_tenant_id_is_rejected(self) -> None:
        service = _make_service()

        with pytest.raises(ToolExecutionException) as exc_info:
            await service.execute_tool(
                tool_name="create_task",
                payload={"title": "no tenant"},
                agent_id="copilot",
            )

        assert "tenant_id is required" in str(exc_info.value.detail)


class TestBusinessTaskToolRegression:
    """Existing ToolBroker categories must keep working."""

    @pytest.mark.asyncio
    async def test_serena_tool_still_works(self) -> None:
        service = _make_service()

        result = await service.execute_tool(
            tool_name="serena__search",
            payload={"query": "x"},
            agent_id="copilot",
        )

        assert result == {"result": "serena_ok"}

    @pytest.mark.asyncio
    async def test_local_tool_still_works(self) -> None:
        service = _make_service()
        local_registry = MagicMock()
        local_registry.execute_local_tool = AsyncMock(return_value={"result": "local_ok"})
        service.local_registry = local_registry

        result = await service.execute_tool(
            tool_name="local__read_file",
            payload={"path": "/tmp/x"},
            agent_id="copilot",
        )

        assert result == {"result": "local_ok"}


class TestBusinessTaskToolPermission:
    """Default-deny must still apply to business tools."""

    @pytest.mark.asyncio
    async def test_create_task_denied_for_unknown_agent(self) -> None:
        with patch(
            "src.core.tool_broker.service.ToolPermissionManager.is_tool_allowed",
            return_value=False,
        ):
            service = _make_service()

            with pytest.raises(ToolExecutionException) as exc_info:
                await service.execute_tool(
                    tool_name="create_task",
                    payload={"tenant_id": 1, "title": "x"},
                    agent_id="unknown_agent",
                    context={"tenant_id": 1},
                )

            assert "Permission denied" in str(exc_info.value.detail)


class TestBusinessTaskToolValidation:
    """list_tasks parameter validation."""

    @pytest.mark.asyncio
    async def test_list_tasks_rejects_negative_skip(self) -> None:
        service = _make_service()

        with pytest.raises(ToolExecutionException) as exc_info:
            await service.execute_tool(
                tool_name="list_tasks",
                payload={"skip": -1},
                agent_id="copilot",
                context={"tenant_id": 1},
            )

        assert "skip must be >= 0" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_list_tasks_rejects_non_numeric_limit(self) -> None:
        service = _make_service()

        with pytest.raises(ToolExecutionException) as exc_info:
            await service.execute_tool(
                tool_name="list_tasks",
                payload={"limit": "abc"},
                agent_id="copilot",
                context={"tenant_id": 1},
            )

        assert "limit must be an integer" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_list_tasks_rejects_limit_above_max(self) -> None:
        service = _make_service()

        with pytest.raises(ToolExecutionException) as exc_info:
            await service.execute_tool(
                tool_name="list_tasks",
                payload={"limit": 1001},
                agent_id="copilot",
                context={"tenant_id": 1},
            )

        assert "limit must be <= 1000" in str(exc_info.value.detail)
