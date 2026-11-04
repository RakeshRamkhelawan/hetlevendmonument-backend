from __future__ import annotations

import pytest
from sqlalchemy import select

from src.core.agents.base_agent import EnhancedBaseAgent
from src.core.learning.auto_learning import auto_learn
from src.core.learning.learning_repository import LearningRepository
from src.core.learning.models import LearningExperience
from src.core.learning.services.observation_service import ObservationService
from src.core.shared.interfaces import ExecutionResult, TaskData
from src.core.types import AgentType


class MandatoryPhase3Agent(EnhancedBaseAgent):
    async def _execute_task(self, task: TaskData) -> ExecutionResult:
        return ExecutionResult(task_id=task.id, success=True, result_data={"task": task.id})

    @auto_learn()
    async def summarize(self, text: str) -> dict:
        return {"success": True, "summary": text.upper()}


def _make_task(task_id: str) -> TaskData:
    return TaskData(
        id=task_id,
        title="Phase 3 task",
        description="Verify decorator-driven learning",
        metadata={"type": "text"},
    )


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.no_mocks
async def test_full_chain_decorator_to_observation_service(
    phase3_learning_env,
    phase3_session_factory,
) -> None:
    repo = LearningRepository(phase3_session_factory)
    agent = MandatoryPhase3Agent("phase3-agent", AgentType.SPECIALIST, 19)
    agent._observation_service_instance = ObservationService(
        tenant_id=19,
        repository=repo,
        observation_threshold=999,
    )

    result = await agent.process_task(_make_task("phase3-process-task"))

    async with phase3_session_factory() as session:
        rows = (await session.execute(select(LearningExperience))).scalars().all()

    assert result.success is True
    assert len(rows) == 1
    assert rows[0].task_type == "text"
    assert rows[0].context["task_title"] == "Phase 3 task"


@pytest.mark.asyncio
@pytest.mark.integration
@pytest.mark.no_mocks
async def test_decorator_records_on_real_agent_subclass(
    phase3_learning_env,
    phase3_session_factory,
) -> None:
    repo = LearningRepository(phase3_session_factory)
    agent = MandatoryPhase3Agent("phase3-method-agent", AgentType.SPECIALIST, 19)
    agent._observation_service_instance = ObservationService(
        tenant_id=19,
        repository=repo,
        observation_threshold=999,
    )

    result = await agent.summarize("phase three")

    async with phase3_session_factory() as session:
        rows = (await session.execute(select(LearningExperience))).scalars().all()

    assert result["summary"] == "PHASE THREE"
    assert len(rows) == 1
    assert rows[0].task_type == "summarize"
    assert rows[0].context["method_name"] == "summarize"
