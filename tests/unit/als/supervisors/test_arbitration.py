import pytest

from src.core.als.supervisors.base_supervisor import BaseSupervisor
from src.core.shared.interfaces import ExecutionResult, TaskData


class ArbiterSupervisor(BaseSupervisor):
    async def decompose_task(self, task: TaskData):
        return [task]

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
async def test_arbitration_logic_confidence_wins():
    supervisor = ArbiterSupervisor(agent_id="judge", tenant_id=1, department="finance")

    # Conflict: Agent A (Low confidence) vs Agent B (High confidence)
    res_a = ExecutionResult(
        task_id="t1",
        success=True,
        result_data={"advice": "sell"},
        confidence_score=0.4,
        reasoning_path=["Low data quality"],
    )
    res_b = ExecutionResult(
        task_id="t1",
        success=True,
        result_data={"advice": "hold"},
        confidence_score=0.9,
        reasoning_path=["Solid market indicators"],
    )

    winner = await supervisor.arbitrate([res_a, res_b])

    assert winner.result_data["advice"] == "hold"
    assert "Arbiter decided based on highest confidence score" in winner.reasoning_path[-1]


@pytest.mark.asyncio
async def test_arbitration_equal_confidence_triggers_escalation():
    supervisor = ArbiterSupervisor(agent_id="judge", tenant_id=1, department="finance")

    res_a = ExecutionResult(
        task_id="t1", success=True, result_data={"val": 10}, confidence_score=0.8
    )
    res_b = ExecutionResult(
        task_id="t1", success=True, result_data={"val": 20}, confidence_score=0.8
    )

    # Same confidence, different results -> should escalate (status='escalated')
    final = await supervisor.arbitrate([res_a, res_b])
    assert final.success is False
    assert "tie" in final.error_message.lower()
