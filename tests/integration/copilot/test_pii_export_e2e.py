"""E2E test: DSAR export event -> DSARExportMonitor signal -> Council -> dispatch.
Behavioral: admin receives a signal when a user initiates a PII export.
Unhappy: exports without PII flag are silently ignored.
Respond: user can acknowledge a proactive signal via CopilotService.
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from src.core.copilot.council.types import CouncilDecision, DecisionVerdict
from src.core.copilot.proactive.monitors import DSARExportMonitor
from src.core.copilot.service import CopilotService
from tests.integration.copilot.conftest import seed_tenants

logger = logging.getLogger(__name__)


class _MockTenantRepo:
    def __init__(self, tenant_id: int, admin_user_id: int) -> None:
        self._tenant_id = tenant_id
        self._admin_user_id = admin_user_id

    async def get_primary_admin_user_id(self, tenant_id: int) -> int:  # noqa: ARG002
        return self._admin_user_id

    async def get_platform_admin_tenant_id(self) -> int:
        return self._tenant_id

    async def list_active_ids(self) -> list[int]:
        return [self._tenant_id]

    async def get_tenant_id_for_user(self, user_id: int) -> int | None:  # noqa: ARG002
        return self._tenant_id

    async def get_tenant_id_for_workflow(self, workflow_id: str | int) -> int | None:  # noqa: ARG002
        return self._tenant_id


@pytest.mark.integration
@pytest.mark.als
@pytest.mark.e2e
async def test_dsar_export_event_triggers_signal_and_council_dispatch(
    real_council: Any,
    db_session: Any,
    real_redis_client: Any,
) -> None:
    """PII export event -> DSARExportMonitor handler -> Council -> dispatcher called."""
    tenant_id = 401
    initiating_user_id = 4001
    admin_user_id = 4099

    await seed_tenants(db_session, [tenant_id])

    logger.info(
        "e2e_start",
        extra={
            "test_name": "test_dsar_export_event_triggers_signal_and_council_dispatch",
            "tenant_id": tenant_id,
        },
    )

    # Dedup key cleanup so the handler is not silently skipped
    dedup_key = f"monitor_dedup:dsar_export:{tenant_id}:{initiating_user_id}:customer_data"
    await real_redis_client.delete(dedup_key)

    dispatched: list[Any] = []

    async def _capture_dispatch(signal: Any, decision: Any) -> None:
        dispatched.append((signal, decision))

    mock_dispatcher = AsyncMock()
    mock_dispatcher.dispatch = _capture_dispatch

    mock_event_bus = MagicMock()
    mock_event_bus.subscribe = MagicMock()

    tenant_repo = _MockTenantRepo(tenant_id, admin_user_id)
    copilot_service = CopilotService(
        council=real_council,
        llm_handler=AsyncMock(),
        proposal_builder=MagicMock(),
    )

    monitor = DSARExportMonitor(
        copilot_service=copilot_service,
        dispatcher=mock_dispatcher,
        tenant_repo=tenant_repo,
        redis=real_redis_client,
        event_bus=mock_event_bus,
    )

    try:
        # Simulate event bus publishing "dsar.export_initiated"
        await monitor._on_export_initiated(
            {
                "tenant_id": tenant_id,
                "user_id": initiating_user_id,
                "export_type": "customer_data",
                "contains_pii": True,
            }
        )

        # Council must have approved before dispatcher was called
        assert len(dispatched) >= 1, f"Expected 1 dispatch call, got {len(dispatched)}"
        signal, decision = dispatched[0]

        # Council APPROVED (signal is internal, no user PII access) -- check verdict first
        assert isinstance(decision, CouncilDecision)
        assert decision.verdict == DecisionVerdict.APPROVED

        # Signal fields
        assert signal.tenant_id == tenant_id
        assert signal.affected_user_id == admin_user_id
        assert signal.monitor_name == "dsar_export"
        assert signal.severity.value == "high"
        assert len(dispatched) == 1, f"Expected exactly 1 dispatch call, got {len(dispatched)}"

        logger.info(
            "e2e_complete",
            extra={
                "test_name": "test_dsar_export_event_triggers_signal_and_council_dispatch",
                "tenant_id": tenant_id,
                "verdict": decision.verdict.value,
            },
        )
    finally:
        await real_redis_client.delete(dedup_key)


@pytest.mark.integration
@pytest.mark.als
@pytest.mark.e2e
async def test_dsar_export_event_without_pii_ignored(
    real_redis_client: Any,
) -> None:
    """Export event with contains_pii=False produces no signal (unhappy path)."""
    tenant_id = 402
    mock_event_bus = MagicMock()
    mock_event_bus.subscribe = MagicMock()

    mock_dispatcher = AsyncMock()
    tenant_repo = _MockTenantRepo(tenant_id, 9999)

    monitor = DSARExportMonitor(
        copilot_service=AsyncMock(),
        dispatcher=mock_dispatcher,
        tenant_repo=tenant_repo,
        redis=real_redis_client,
        event_bus=mock_event_bus,
    )

    await monitor._on_export_initiated(
        {
            "tenant_id": tenant_id,
            "user_id": 4002,
            "export_type": "metadata_only",
            "contains_pii": False,  # no PII -> must be ignored
        }
    )

    mock_dispatcher.dispatch.assert_not_called()


@pytest.mark.integration
@pytest.mark.als
@pytest.mark.e2e
async def test_user_can_acknowledge_proactive_signal(
    real_council: Any,
    db_session: Any,
) -> None:
    """User responds to a proactive signal via CopilotService.handle_proactive_response."""
    tenant_id = 403
    user_id = 4003
    signal_id = uuid4()

    await seed_tenants(db_session, [tenant_id])

    audit_writer = AsyncMock()
    service = CopilotService(
        council=real_council,
        llm_handler=AsyncMock(),
        proposal_builder=MagicMock(),
        audit_writer=audit_writer,
    )

    result = await service.handle_proactive_response(
        signal_id=signal_id,
        tenant_id=tenant_id,
        user_id=user_id,
        action_type="confirm",
        params={"export_id": str(uuid4())},
    )

    # Behavioral assertion: service acknowledges the response
    assert result.signal_id == signal_id
    assert result.accepted is True
    assert result.message is not None
