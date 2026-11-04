import pytest

from src.core.als.supervisors.finance_supervisor import FinanceSupervisor
from src.core.als.supervisors.hr_supervisor import HRSupervisor
from src.core.shared.interfaces import TaskData


@pytest.mark.asyncio
async def test_finance_supervisor_selects_finance_agents():
    supervisor = FinanceSupervisor(agent_id="fin.sup", tenant_id=1)
    task = {
        "task_id": "t1",
        "title": "Tax",
        "description": "Review tax",
        "tenant_id": "tenant_1",
        "metadata": {"type": "tax"},
    }

    # Simulate a sub-task that requires tax compliance
    sub_tasks = await supervisor.decompose_task(task)

    # Registry matching should only return finance agents
    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(
            "src.core.als.supervisors.base_supervisor.AGENT_REGISTRY",
            {
                "tax_compliance": ("finance_treasury", "TaxComplianceAgent", "LLM"),
                "talent_acquisition": ("hr_culture", "TalentAcquisitionAgent", "ML"),
            },
        )
        agents = await supervisor.select_agents(sub_tasks)

        assert "tax_compliance" in agents
        assert "talent_acquisition" not in agents


@pytest.mark.asyncio
async def test_hr_supervisor_selects_hr_agents():
    supervisor = HRSupervisor(agent_id="hr.sup", tenant_id=1)
    task = TaskData(id="t2", title="Hiring", description="Hire dev", metadata={"type": "hire"})

    sub_tasks = await supervisor.decompose_task(task)

    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(
            "src.core.als.supervisors.base_supervisor.AGENT_REGISTRY",
            {
                "tax_compliance": ("finance_treasury", "TaxComplianceAgent", "LLM"),
                "talent_acquisition": ("hr_culture", "TalentAcquisitionAgent", "ML"),
            },
        )
        agents = await supervisor.select_agents(sub_tasks)

        assert "talent_acquisition" in agents
        assert "tax_compliance" not in agents
