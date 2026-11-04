"""
RED tests for WorkflowService._execute_step() wiring -- ADR-023 P0-4.

These tests FAIL before the fix (stub returns "not_implemented") and PASS after.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.core.agents.router_agent_service import RouterAgentService
from src.domains.workflows.models import Workflow, WorkflowStep, WorkflowStatus
from src.domains.workflows.services import WorkflowService


def _make_step(
    step_id: str = "step-001",
    name: str = "Test Step",
    step_type: str = "agent",
    order: int = 0,
    config: dict | None = None,
) -> WorkflowStep:
    return WorkflowStep(
        id=step_id,
        name=name,
        step_type=step_type,
        order=order,
        config=config or {},
    )


@pytest.mark.asyncio
async def test_execute_step_with_router_returns_completed() -> None:
    """With router configured: _execute_step calls execute_request and returns completed."""
    mock_router = AsyncMock(spec=RouterAgentService)
    mock_router.execute_request.return_value = {
        "query": "Test Step",
        "decision": {},
        "result": "ok",
        "executed_by": "ollama_local",
        "tenant_id": None,
    }
    svc = WorkflowService(router=mock_router)
    step = _make_step()

    result = await svc._execute_step(step)

    mock_router.execute_request.assert_awaited_once()
    assert result["status"] == "completed"
    assert result["step_id"] == "step-001"
    assert result["step_name"] == "Test Step"
    assert "output" in result


@pytest.mark.asyncio
async def test_execute_step_uses_config_description_as_query() -> None:
    """When config has a 'description' key, that is used as the query (not just step.name)."""
    mock_router = AsyncMock(spec=RouterAgentService)
    mock_router.execute_request.return_value = {
        "result": "ok",
        "decision": {},
        "executed_by": "x",
        "tenant_id": None,
    }
    svc = WorkflowService(router=mock_router)
    step = _make_step(config={"description": "Approve the invoice via finance team"})

    await svc._execute_step(step)

    call_args = mock_router.execute_request.call_args
    assert call_args[0][0] == "Approve the invoice via finance team"


@pytest.mark.asyncio
async def test_execute_step_without_router_returns_skipped() -> None:
    """Without router: _execute_step returns skipped status without raising."""
    svc = WorkflowService()
    step = _make_step()

    result = await svc._execute_step(step)

    assert result["status"] == "skipped"
    assert result["step_id"] == "step-001"
    assert result["step_name"] == "Test Step"


@pytest.mark.asyncio
async def test_execute_step_router_failure_returns_failed() -> None:
    """Router raises exception: _execute_step returns failed status without re-raising."""
    mock_router = AsyncMock(spec=RouterAgentService)
    mock_router.execute_request.side_effect = RuntimeError("LLM timeout")
    svc = WorkflowService(router=mock_router)
    step = _make_step()

    result = await svc._execute_step(step)

    assert result["status"] == "failed"
    assert "error_code" in result
    assert result["step_id"] == "step-001"


@pytest.mark.asyncio
async def test_execute_step_passes_tenant_id_to_router() -> None:
    """tenant_id is forwarded as kwarg to router.execute_request()."""
    mock_router = AsyncMock(spec=RouterAgentService)
    mock_router.execute_request.return_value = {
        "result": "ok",
        "decision": {},
        "executed_by": "x",
        "tenant_id": "tenant-abc",
    }
    svc = WorkflowService(router=mock_router)

    await svc._execute_step(_make_step(), tenant_id="tenant-abc")

    call_kwargs = mock_router.execute_request.call_args
    assert call_kwargs.kwargs.get("tenant_id") == "tenant-abc"


@pytest.mark.asyncio
async def test_execute_workflow_threads_tenant_id_to_steps() -> None:
    """execute_workflow passes workflow.tenant_id into each _execute_step call."""
    mock_router = AsyncMock(spec=RouterAgentService)
    mock_router.execute_request.return_value = {
        "result": "ok",
        "decision": {},
        "executed_by": "x",
        "tenant_id": "tenant-xyz",
    }
    svc = WorkflowService(router=mock_router)
    workflow = Workflow(
        id="wf-2",
        name="Tenant Workflow",
        tenant_id="tenant-xyz",
        steps=[_make_step()],
    )

    await svc.execute_workflow(workflow)

    call_kwargs = mock_router.execute_request.call_args
    assert call_kwargs.kwargs.get("tenant_id") == "tenant-xyz"


@pytest.mark.asyncio
async def test_execute_step_forwards_none_tenant_id_when_not_provided() -> None:
    """FA-003: default path forwards tenant_id=None explicitly to execute_request."""
    mock_router = AsyncMock(spec=RouterAgentService)
    mock_router.execute_request.return_value = {
        "result": "ok",
        "decision": {},
        "executed_by": "x",
        "tenant_id": None,
    }
    svc = WorkflowService(router=mock_router)

    await svc._execute_step(_make_step())

    mock_router.execute_request.assert_awaited_once_with("Test Step", tenant_id=None)


@pytest.mark.asyncio
async def test_execute_step_without_router_logs_warning_with_context() -> None:
    """FA-003: logger.bind() called with step context when router is None."""
    with patch("src.domains.workflows.services.logger") as mock_logger:
        mock_bound: MagicMock = mock_logger.bind.return_value
        svc = WorkflowService()

        await svc._execute_step(_make_step())

        mock_logger.bind.assert_called_once_with(step_id="step-001", step_name="Test Step")
        mock_bound.warning.assert_called_once()


@pytest.mark.asyncio
async def test_execute_workflow_without_router_returns_failed() -> None:
    """execute_workflow with no router: workflow.status=FAILED, returned dict status=failed.

    A workflow where all steps are skipped must not silently report completion.
    """
    svc = WorkflowService()
    workflow = Workflow(
        id="wf-001",
        name="Test Workflow",
        tenant_id="tenant-1",
        steps=[_make_step(step_id="s1"), _make_step(step_id="s2", name="Step 2", order=1)],
    )

    result = await svc.execute_workflow(workflow)

    assert result["status"] == "failed"
    assert workflow.status == WorkflowStatus.FAILED


# ---------------------------------------------------------------------------
# BE-WFL-005: AuditService integratie (RED tests -- VOOR implementatie)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_execute_workflow_calls_audit_on_success() -> None:
    """AuditService.log_action wordt aangeroepen met WORKFLOW_EXECUTED na succesvolle uitvoering."""
    mock_router = AsyncMock(spec=RouterAgentService)
    mock_router.execute_request.return_value = {
        "result": "ok",
        "decision": {},
        "executed_by": "ollama_local",
        "tenant_id": "t1",
    }
    mock_audit = MagicMock()
    mock_audit.log_action = AsyncMock(return_value=None)
    svc = WorkflowService(router=mock_router, audit_service=mock_audit)
    workflow = Workflow(
        id="wf-audit-1",
        name="Audit Success Test",
        tenant_id="t1",
        steps=[_make_step()],
    )

    result = await svc.execute_workflow(workflow)

    assert result["status"] == "completed"
    mock_audit.log_action.assert_awaited_once()
    call_kwargs = mock_audit.log_action.call_args.kwargs
    assert call_kwargs["action"] == "WORKFLOW_EXECUTED"
    assert call_kwargs["resource"] == "workflow:wf-audit-1"
    assert call_kwargs["tenant_id"] == "t1"


@pytest.mark.asyncio
async def test_execute_workflow_calls_audit_on_exception() -> None:
    """AuditService.log_action wordt aangeroepen met WORKFLOW_FAILED als router een exception gooit."""
    mock_router = AsyncMock(spec=RouterAgentService)
    mock_router.execute_request.side_effect = RuntimeError("LLM timeout")
    mock_audit = MagicMock()
    mock_audit.log_action = AsyncMock(return_value=None)
    svc = WorkflowService(router=mock_router, audit_service=mock_audit)
    workflow = Workflow(
        id="wf-audit-2",
        name="Audit Fail Test",
        tenant_id="t1",
        steps=[_make_step()],
    )

    result = await svc.execute_workflow(workflow)

    assert result["status"] == "failed"
    mock_audit.log_action.assert_awaited_once()
    call_kwargs = mock_audit.log_action.call_args.kwargs
    assert call_kwargs["action"] == "WORKFLOW_FAILED"
    assert call_kwargs["resource"] == "workflow:wf-audit-2"


@pytest.mark.asyncio
async def test_execute_workflow_without_audit_service_does_not_crash() -> None:
    """audit_service=None mag execute_workflow nooit laten crashen."""
    mock_router = AsyncMock(spec=RouterAgentService)
    mock_router.execute_request.return_value = {
        "result": "ok",
        "decision": {},
        "executed_by": "ollama_local",
        "tenant_id": "t1",
    }
    svc = WorkflowService(router=mock_router)
    workflow = Workflow(
        id="wf-audit-3",
        name="No Audit Service",
        tenant_id="t1",
        steps=[_make_step()],
    )

    result = await svc.execute_workflow(workflow)

    assert result["status"] == "completed"
