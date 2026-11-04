"""Unit tests: AgenticOrchestrationService -- AUDIT-DB14a.

Rode tests voor aanvang implementatie. Alle tests falen zolang
src/core/api/v1/agentic/orchestration_service.py niet bestaat.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def test_agentic_orchestration_service_importable() -> None:
    """AUDIT-DB14a: AgenticOrchestrationService moet importeerbaar zijn."""
    from src.core.api.v1.agentic.orchestration_service import AgenticOrchestrationService  # noqa: F401


def test_agentic_orchestration_service_accepts_db_and_tenant_id() -> None:
    """AUDIT-DB14a: AgenticOrchestrationService(db=..., tenant_id=...) moet werken."""
    from src.core.api.v1.agentic.orchestration_service import AgenticOrchestrationService

    mock_db = MagicMock()
    svc = AgenticOrchestrationService(db=mock_db, tenant_id=42)
    assert svc.tenant_id == 42


@pytest.mark.asyncio
async def test_start_workflow_dispatches_with_tenant_id() -> None:
    """AUDIT-DB14a: start_workflow task-payload moet tenant_id bevatten (TI-004)."""
    from src.core.api.v1.agentic.orchestration_service import (
        AgenticOrchestrationService,
        AgenticWorkflowConfig,
    )

    mock_db = AsyncMock()
    mock_db.flush = AsyncMock()
    mock_db.commit = AsyncMock()

    captured: list[dict] = []

    def fake_send(payload: dict) -> None:
        captured.append(payload)

    with patch("src.core.api.v1.agentic.orchestration_service.execute_workflow_step") as mock_task:
        mock_task.send.side_effect = fake_send
        svc = AgenticOrchestrationService(db=mock_db, tenant_id=7)
        await svc.start_workflow(AgenticWorkflowConfig(name="test-workflow"))

    assert captured, "workflow_execute_task.send() werd nooit aangeroepen"
    assert captured[0]["tenant_id"] == 7, (
        f"tenant_id ontbreekt of verkeerd in task-payload: {captured[0]}"
    )


@pytest.mark.asyncio
async def test_start_workflow_raises_on_missing_tenant_id() -> None:
    """AUDIT-DB14a: tenant_id=0 of None moet ValueError geven (TI-004)."""
    from src.core.api.v1.agentic.orchestration_service import (
        AgenticOrchestrationService,
        AgenticWorkflowConfig,
    )

    mock_db = AsyncMock()
    svc = AgenticOrchestrationService(db=mock_db, tenant_id=0)

    with pytest.raises(ValueError):
        await svc.start_workflow(AgenticWorkflowConfig(name="test"))
