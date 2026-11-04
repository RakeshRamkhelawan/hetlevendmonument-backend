from unittest.mock import AsyncMock, patch

import pytest

from src.core.als.supervisors.finance_supervisor import FinanceSupervisor
from src.core.monitoring.ooda_metrics import OODAMonitor
from src.core.shared.interfaces import TaskData


@pytest.mark.asyncio
async def test_supervisor_execution_logs_metrics():
    tenant_id = 1
    agent_id = "fin.sup.test"
    supervisor = FinanceSupervisor(agent_id=agent_id, tenant_id=tenant_id)
    task = TaskData(title="Audit", description="Audit me", metadata={"type": "audit"})

    # Mock decompose_task to bypass tenant_id validation (not what this test is for)
    # This test verifies OODA monitor phase tracking
    mock_subtask = TaskData(title="Sub-audit", description="Sub", metadata={})
    with patch.object(supervisor, "decompose_task", AsyncMock(return_value=[mock_subtask])):
        with patch.object(supervisor, "select_agents", AsyncMock(return_value=[])):
            # Execute
            await supervisor.execute(task)

    # Verify monitor has the data
    monitor = OODAMonitor()
    metrics = monitor.get_agent_metrics(agent_id, tenant_id)

    assert "orient" in metrics
    assert "decide" in metrics
    assert metrics["orient"] > 0
