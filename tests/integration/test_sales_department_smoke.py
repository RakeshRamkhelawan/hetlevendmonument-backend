"""E2E smoke test: Sales department activation -> webhook -> signal flow."""

import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.core.events.department_activation_handler import (
    DepartmentActivatedEvent,
    on_department_activated,
)
from src.core.api.webhook_endpoints import inbound_webhook
from src.core.tool_broker.ap_mcp_registry import ap_mcp_registry


@pytest.mark.asyncio
async def test_sales_department_activation_registers_tools() -> None:
    """Sales department activation registers gmail and slack tools."""
    session = MagicMock()
    with pytest.MonkeyPatch().context() as m:
        repo_mock = MagicMock()
        repo_mock.get_by_agent_id = AsyncMock(return_value=None)
        repo_mock.create = AsyncMock(return_value=MagicMock())
        m.setattr(
            "src.core.events.department_activation_handler.AgentConfigRepository",
            lambda db: repo_mock,
        )
        event = DepartmentActivatedEvent(tenant_id=1, department="sales")
        await on_department_activated(event, session)
        tools = ap_mcp_registry.get_default_tools_for_department("sales")
        assert "gmail.send_email" in tools
        assert "slack.send_message" in tools


@pytest.mark.asyncio
async def test_webhook_to_signalbus_flow() -> None:
    """Webhook receives event and would publish to SignalBus."""
    from fastapi import Request

    mock_request = MagicMock(spec=Request)
    mock_request.headers = {"X-Tenant-ID": "1"}
    mock_request.json = AsyncMock(
        return_value={"event_type": "email.received", "data": {"subject": "Lead"}}
    )
    mock_app = MagicMock()
    mock_app.state.signal_bus = None
    mock_request.app = mock_app
    with (
        patch.dict(os.environ, {"WEBHOOK_SECRET_GMAIL": "test-secret"}),
        patch(
            "src.core.api.webhook_endpoints._verify_webhook_signature",
            new=AsyncMock(return_value=True),
        ),
    ):
        result = await inbound_webhook("gmail", mock_request)
    assert result["received"] is True
