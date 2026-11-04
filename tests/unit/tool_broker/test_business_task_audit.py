"""Unit tests for ADR-019 audit-hash-chain wiring on business task actions.

Every successful create/update/delete must emit an AuditService.log_action entry
(audit_logs table, SHA-256 chain) inside best_effort so an audit failure never
blocks the primary action. The real hash-chain (previous_hash) is verified in the
integration suite against a real PostgreSQL instance.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Iterator
from contextlib import asynccontextmanager
from typing import Any, cast
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from src.core.tool_broker.business_registry import BusinessToolRegistry
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


def _make_service(task_service: AsyncMock) -> ToolBrokerService:
    @asynccontextmanager
    async def _mock_session() -> AsyncGenerator[AsyncMock, None]:
        yield AsyncMock()

    def _factory(session: AsyncMock, tenant_id: int) -> AsyncMock:
        return task_service

    registry = BusinessToolRegistry(
        session_factory=_mock_session,
        task_service_factory=cast(Any, _factory),
    )
    return ToolBrokerService(
        serena_client=MockSerenaClient(),
        seq_thinking_client=MockSeqThinkingClient(),
        business_registry=registry,
        enable_resilience=False,
    )


def _stub(**overrides: Any) -> MagicMock:
    base: dict[str, Any] = {"id": str(uuid4()), "tenant_id": 1, "title": "t", "status": "pending"}
    base.update(overrides)
    m = MagicMock()
    m.model_dump = lambda: base
    return m


class TestBusinessTaskAudit:
    @pytest.mark.asyncio
    async def test_create_emits_audit_log_action(self) -> None:
        """2.1 -- create_task schrijft een AuditService.log_action entry (ADR-019)."""
        task_service = AsyncMock()
        task_service.create = AsyncMock(return_value=_stub(title="Audited task"))
        service = _make_service(task_service)

        with patch(
            "src.core.governance.audit.AuditService.log_action",
            new_callable=AsyncMock,
        ) as mock_log:
            await service.execute_tool(
                tool_name="create_task",
                payload={"tenant_id": 7, "title": "Audited task"},
                agent_id="copilot",
                context={"tenant_id": 7},
            )

        mock_log.assert_awaited()
        kwargs = mock_log.await_args.kwargs
        assert kwargs.get("tenant_id") == 7
        assert "task" in str(kwargs.get("action", "")).lower()
        assert str(kwargs.get("resource", "")).startswith("task:")
        assert kwargs.get("session") is not None

    @pytest.mark.asyncio
    async def test_delete_emits_audit_log_action(self) -> None:
        """2.1 -- delete_task schrijft eveneens een audit entry."""
        task_service = AsyncMock()
        task_service.delete = AsyncMock(return_value=True)
        hitl_store = AsyncMock()
        hitl_store.get_approval_status = AsyncMock(return_value="approved")
        service = _make_service(task_service)
        service.hitl_store = hitl_store

        task_id = str(uuid4())
        with patch(
            "src.core.governance.audit.AuditService.log_action",
            new_callable=AsyncMock,
        ) as mock_log:
            await service.execute_tool(
                tool_name="delete_task",
                payload={
                    "tenant_id": 7,
                    "task_id": task_id,
                    "_hitl_ticket_ref": "TOOL-approved-002",
                },
                agent_id="copilot",
                context={"tenant_id": 7},
            )

        mock_log.assert_awaited()
        kwargs = mock_log.await_args.kwargs
        assert "delete" in str(kwargs.get("action", "")).lower()
        assert kwargs.get("resource") == f"task:{task_id}"

    @pytest.mark.asyncio
    async def test_audit_failure_does_not_block_primary_action(self) -> None:
        """2.2 -- audit-fout wordt door best_effort opgevangen; de actie slaagt nog steeds."""
        task_service = AsyncMock()
        task_service.create = AsyncMock(return_value=_stub(title="Still created"))
        service = _make_service(task_service)

        with patch(
            "src.core.governance.audit.AuditService.log_action",
            new_callable=AsyncMock,
            side_effect=RuntimeError("audit backend down"),
        ):
            result = await service.execute_tool(
                tool_name="create_task",
                payload={"tenant_id": 7, "title": "Still created"},
                agent_id="copilot",
                context={"tenant_id": 7},
            )

        assert result["success"] is True
        assert result["data"]["title"] == "Still created"
