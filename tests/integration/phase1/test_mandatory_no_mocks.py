from __future__ import annotations

from unittest.mock import patch

import pytest
from sqlalchemy import select

from src.core.agents.base_agent import EnhancedBaseAgent


@pytest.fixture(autouse=True)
def _allow_all_tools():
    """Bypass ToolPermissionManager for integration tests -- permission logic tested separately."""
    with patch(
        "src.core.tool_broker.service.ToolPermissionManager.is_tool_allowed",
        return_value=True,
    ):
        yield


from src.core.learning.learning_repository import LearningRepository
from src.core.learning.models import LearningExperience
from src.core.learning.services.observation_service import ObservationService
from src.core.shared.interfaces import ExecutionResult, TaskData
from src.core.types import AgentType


class MandatoryPhase1Agent(EnhancedBaseAgent):
    async def _execute_task(self, task: TaskData) -> ExecutionResult:
        return ExecutionResult(task_id=task.id, success=True, result_data={"task": task.title})


def _make_task(task_id: str) -> TaskData:
    return TaskData(
        id=task_id,
        title="Phase 1 task",
        description="Verify mandatory phase 1 flow",
        metadata={"type": "text"},
    )


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.no_mocks
async def test_learning_mixin_records_to_real_observation_service(
    phase1_learning_env,
    phase1_session_factory,
) -> None:
    repo = LearningRepository(phase1_session_factory)
    agent = MandatoryPhase1Agent("phase1-agent", AgentType.SPECIALIST, 11)
    agent._observation_service_instance = ObservationService(
        tenant_id=11,
        repository=repo,
        observation_threshold=999,
    )

    task = _make_task("phase1-observation")
    result = ExecutionResult(task_id=task.id, success=True, execution_time=0.25)
    observation_id = await agent._record_task_observation(task, result)

    async with phase1_session_factory() as session:
        rows = (await session.execute(select(LearningExperience))).scalars().all()

    assert observation_id is not None
    assert len(rows) == 1
    assert rows[0].tenant_id == 11
    assert rows[0].agent_id == "phase1-agent"


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.no_mocks
async def test_execute_tool_with_test_tools(phase1_learning_env) -> None:
    agent = MandatoryPhase1Agent("phase1-tool-agent", AgentType.SPECIALIST, 11)

    result = await agent.execute_tool("test__echo", {"tenant_id": 11, "payload": "ok"})

    assert result["tool"] == "test__echo"
    assert result["echo"]["payload"] == "ok"
