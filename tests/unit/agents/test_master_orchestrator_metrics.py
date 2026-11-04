"""Rode tests -- SP-ADR023-002 Dag 3 -- Prometheus-metrics op MasterOrchestratorAgent.process_task().

Tests zijn ROOD totdat master_orchestrator_workflow_duration_seconds bestaat in
src/core/observability/metrics.py EN daadwerkelijk wordt aangeroepen in zowel het
succes- als het foutpad van process_task(). Volgt hetzelfde testpatroon als
tests/unit/agents/test_critique_metrics.py (SP-AGT-007).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.agents.master_orchestrator_agent import MasterOrchestratorAgent, WorkflowStatus
from src.core.shared.interfaces import ExecutionResult, TaskData


@pytest.fixture(autouse=True)
def suppress_registry_mutation():  # type: ignore[return]
    with patch.object(MasterOrchestratorAgent, "_register_agent_profile", return_value=None):
        yield


def _make_task() -> TaskData:
    return TaskData(id="wf-metrics-1", title="metrics workflow", description="d", metadata={})


@pytest.mark.unit
@pytest.mark.asyncio
async def test_process_task_observes_duration_on_success() -> None:
    orchestrator = MasterOrchestratorAgent(agent_id="test_orch_metrics", tenant_id=99)

    async def fake_plan_workflow(workflow_id: str, task: TaskData):
        from src.core.agents.master_orchestrator_agent import WorkflowPlan

        return WorkflowPlan(workflow_id=workflow_id, goal=task.title, sub_tasks=[])

    orchestrator._plan_workflow = fake_plan_workflow  # type: ignore[method-assign]
    orchestrator._execute_plan = AsyncMock(return_value=[])  # type: ignore[method-assign]

    with patch(
        "src.core.agents.master_orchestrator_agent.master_orchestrator_workflow_duration_seconds"
    ) as mock_hist:
        mock_obs = MagicMock()
        mock_hist.labels.return_value = mock_obs
        result = await orchestrator.process_task(_make_task())

    assert result.success is True
    mock_hist.labels.assert_called_once_with(tenant_id="99", status=WorkflowStatus.SUCCEEDED.value)
    mock_obs.observe.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_process_task_observes_duration_on_failure() -> None:
    orchestrator = MasterOrchestratorAgent(agent_id="test_orch_metrics_fail", tenant_id=99)

    async def failing_plan_workflow(workflow_id: str, task: TaskData):
        raise RuntimeError("planning failed")

    orchestrator._plan_workflow = failing_plan_workflow  # type: ignore[method-assign]

    with patch(
        "src.core.agents.master_orchestrator_agent.master_orchestrator_workflow_duration_seconds"
    ) as mock_hist:
        mock_obs = MagicMock()
        mock_hist.labels.return_value = mock_obs
        result = await orchestrator.process_task(_make_task())

    assert result.success is False
    mock_hist.labels.assert_called_once_with(tenant_id="99", status="failed")
    mock_obs.observe.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_process_task_observes_duration_on_partial_success() -> None:
    """WorkflowStatus.PARTIAL is a separate branch of the success return path
    (plan.status.value differs from SUCCEEDED) -- must not be silently
    uninstrumented, per code-review Gate 2 note on this sprint day."""
    orchestrator = MasterOrchestratorAgent(agent_id="test_orch_metrics_partial", tenant_id=99)

    async def fake_plan_workflow(workflow_id: str, task: TaskData):
        from src.core.agents.master_orchestrator_agent import WorkflowPlan

        return WorkflowPlan(workflow_id=workflow_id, goal=task.title, sub_tasks=[])

    orchestrator._plan_workflow = fake_plan_workflow  # type: ignore[method-assign]
    orchestrator._execute_plan = AsyncMock(  # type: ignore[method-assign]
        return_value=[
            ExecutionResult(task_id="sub-1", success=True, result_data={}, execution_time=0.0),
            ExecutionResult(task_id="sub-2", success=False, result_data={}, execution_time=0.0),
        ]
    )

    with patch(
        "src.core.agents.master_orchestrator_agent.master_orchestrator_workflow_duration_seconds"
    ) as mock_hist:
        mock_obs = MagicMock()
        mock_hist.labels.return_value = mock_obs
        result = await orchestrator.process_task(_make_task())

    assert result.success is True
    assert result.result_data is not None
    assert result.result_data["status"] == WorkflowStatus.PARTIAL.value
    mock_hist.labels.assert_called_once_with(tenant_id="99", status=WorkflowStatus.PARTIAL.value)
    mock_obs.observe.assert_called_once()
