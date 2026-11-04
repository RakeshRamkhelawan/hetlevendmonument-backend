import pytest

from src.core.als.supervisors.cva_supervisor import CVASupervisor
from src.core.shared.interfaces import TaskData


@pytest.mark.asyncio
async def test_cva_meta_routing():
    supervisor = CVASupervisor(agent_id="ceo.sup", tenant_id=1)

    # Task that should go to Finance
    task_fin = TaskData(
        task_id="m1",
        title="Help",
        description="I need help with tax",
        metadata={"text": "tax help"},
    )
    agents_fin = await supervisor.select_agents([task_fin])
    assert "finance_supervisor" in agents_fin

    # Task that should go to HR
    task_hr = TaskData(
        task_id="m2", title="Help", description="I need to hire", metadata={"text": "hiring stuff"}
    )
    agents_hr = await supervisor.select_agents([task_hr])
    assert "hr_supervisor" in agents_hr
