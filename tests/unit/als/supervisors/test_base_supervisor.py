from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.als.supervisors.base_supervisor import BaseSupervisor
from src.core.shared.interfaces import ExecutionResult, TaskData


class ConcreteSupervisor(BaseSupervisor):
    """Temporary concrete class for testing BaseSupervisor."""

    async def decompose_task(self, task: TaskData) -> list[TaskData]:
        # Simple split for testing: returns the same task in a list
        return [task]

    # Implement abstract OODA methods from SymbioticAgent
    async def observe(self, task: TaskData):
        pass

    async def orient(self, task: TaskData):
        pass

    async def decide(self, task: TaskData):
        pass

    async def act(self, task: TaskData):
        pass

    async def _execute_task(self, task: TaskData):
        pass


@pytest.mark.asyncio
async def test_supervisor_initialization():
    supervisor = ConcreteSupervisor(
        agent_id="test.supervisor", tenant_id=1, department="finance_treasury"
    )
    assert supervisor.agent_id == "test.supervisor"
    assert supervisor.tenant_id == 1
    assert supervisor.department == "finance_treasury"


@pytest.mark.asyncio
async def test_select_agents_happy_path():
    supervisor = ConcreteSupervisor(agent_id="test", tenant_id=1, department="finance")
    sub_tasks = [
        TaskData(
            task_id="1", title="Tax Review", description="Review Q3 tax", metadata={"type": "tax"}
        )
    ]

    with pytest.MonkeyPatch().context() as mp:
        mp.setattr(
            "src.core.als.supervisors.base_supervisor.AGENT_REGISTRY",
            {"tax_compliance": ("finance", "TaxComplianceAgent", "LLM")},
        )
        agents = await supervisor.select_agents(sub_tasks)
        assert "tax_compliance" in agents


@pytest.mark.asyncio
async def test_supervisor_execution_without_tenant_fails():
    # Note: validation happens in __init__
    with pytest.raises(ValueError, match="tenant_id is required"):
        ConcreteSupervisor(agent_id="test", tenant_id=None, department="finance")
