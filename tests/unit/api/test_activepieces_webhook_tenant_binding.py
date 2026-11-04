from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.api.webhooks.activepieces_handler import (
    ExecutionEvent,
    activepieces_webhook,
    execution_completed_webhook,
)


def _mock_request(payload: dict[str, object]) -> MagicMock:
    request = MagicMock()
    request.json = AsyncMock(return_value=payload)
    return request


@pytest.mark.asyncio
async def test_activepieces_webhook_binds_execution_tenant_from_stored_flow() -> None:
    payload = {
        "type": "execution.completed",
        "flowId": "flow-123",
        "runId": "run-123",
        "projectId": "project-123",
        "status": "SUCCESS",
        "tenant_id": 999,
    }
    request = _mock_request(payload)
    db = MagicMock()
    flow_repo = MagicMock()
    flow_repo.get_by_ap_flow_reference = AsyncMock(return_value=SimpleNamespace(tenant_id=42))
    handler = AsyncMock()

    with patch(
        "src.core.api.webhooks.activepieces_handler.ActivePiecesFlowRepository",
        return_value=flow_repo,
    ), patch(
        "src.core.api.webhooks.activepieces_handler.handle_execution_completed",
        handler,
    ):
        response = await activepieces_webhook(request=request, db=db)

    assert response == {"status": "success", "message": "Webhook processed"}
    flow_repo.get_by_ap_flow_reference.assert_awaited_once_with("flow-123", "project-123")
    handler.assert_awaited_once()
    # Tot 2026-09-18 droeg `ExecutionEvent` zelf een `tenant_id`-veld, dat na de
    # opzoeking werd overschreven met de opgeloste waarde; deze assertie toetste die
    # overschrijving. Het veld is nu WEG (ADR-036 OP-259): een request body hoort geen
    # tenant te dragen, ook niet eentje die je daarna negeert. De payload-waarde 999
    # hierboven landt dus nergens meer, en dat is wat hier nu getoetst wordt -- strenger
    # dan de oude assertie, want die liet het veld bestaan.
    assert not hasattr(handler.await_args.args[0], "tenant_id"), (
        "ExecutionEvent draagt weer een tenant_id-veld uit de payload."
    )
    assert handler.await_args.args[2] == 42


@pytest.mark.asyncio
async def test_activepieces_webhook_binds_connection_tenant_from_stored_connection() -> None:
    payload = {
        "type": "connection.status_changed",
        "connectionId": "conn-123",
        "appName": "gmail",
        "projectId": "project-123",
        "status": "connected",
        "tenant_id": 999,
    }
    request = _mock_request(payload)
    db = MagicMock()
    connection_repo = MagicMock()
    connection_repo.get_by_ap_connection_reference = AsyncMock(
        return_value=SimpleNamespace(tenant_id=7)
    )
    handler = AsyncMock()

    with patch(
        "src.core.api.webhooks.activepieces_handler.ActivePiecesConnectionRepository",
        return_value=connection_repo,
    ), patch(
        "src.core.api.webhooks.activepieces_handler.handle_connection_status_changed",
        handler,
    ):
        response = await activepieces_webhook(request=request, db=db)

    assert response == {"status": "success", "message": "Webhook processed"}
    connection_repo.get_by_ap_connection_reference.assert_awaited_once_with(
        "conn-123", "project-123"
    )
    handler.assert_awaited_once()
    assert handler.await_args.args[2] == 7


@pytest.mark.asyncio
async def test_execution_completed_webhook_ignores_payload_tenant_id() -> None:
    event = ExecutionEvent(
        type="execution.completed",
        flowId="flow-123",
        runId="run-123",
        projectId="project-123",
        status="SUCCESS",
        tenant_id=999,
    )
    db = MagicMock()
    flow_repo = MagicMock()
    flow_repo.get_by_ap_flow_reference = AsyncMock(return_value=SimpleNamespace(tenant_id=42))
    handler = AsyncMock()

    with patch(
        "src.core.api.webhooks.activepieces_handler.ActivePiecesFlowRepository",
        return_value=flow_repo,
    ), patch(
        "src.core.api.webhooks.activepieces_handler.handle_execution_completed",
        handler,
    ):
        response = await execution_completed_webhook(event=event, db=db)

    assert response == {"status": "success"}
    flow_repo.get_by_ap_flow_reference.assert_awaited_once_with("flow-123", "project-123")
    handler.assert_awaited_once()
    # Zie de toelichting hierboven: het veld bestaat niet meer, dus `tenant_id=999` in de
    # constructie wordt stil genegeerd door Pydantic en er valt niets te overschrijven.
    assert not hasattr(event, "tenant_id"), (
        "ExecutionEvent draagt weer een tenant_id-veld uit de payload (ADR-036 OP-259)."
    )
    assert handler.await_args.args[2] == 42