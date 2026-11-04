from unittest.mock import AsyncMock, PropertyMock, patch

import pytest

from src.core.agents.base_agent import EnhancedBaseAgent
from src.core.shared.interfaces import ExecutionResult, TaskData
from src.core.types import AgentType


class _LearningAgent(EnhancedBaseAgent):
    async def _execute_task(self, task: TaskData) -> ExecutionResult:
        return ExecutionResult(task_id=task.id, success=True, result_data={"ok": True})


class _GeneratedLearningAgent(_LearningAgent):
    pass


class _AlsLearningAgent(_LearningAgent):
    pass


_GeneratedLearningAgent.__module__ = "src.core.agents.generated.test_agent"
_AlsLearningAgent.__module__ = "src.core.als.agents.test_agent"


def _make_task() -> TaskData:
    return TaskData(
        id="task-learning", title="Learn", description="desc", metadata={"type": "text"}
    )


def _make_agent(tenant_id: int = 1) -> _LearningAgent:
    with (
        patch("src.core.agents.base_agent.get_settings") as mock_settings,
        patch("src.core.agents.mixins.learning_mixin.get_feature_flag", return_value=True),
        patch("src.core.ai.router.AIRouter"),
        patch("src.core.ai.explainability.ReasoningTrace"),
    ):
        mock_settings.return_value.max_concurrent_tasks = 3
        return _LearningAgent(
            agent_id="learning-agent",
            agent_type=AgentType.SPECIALIST,
            tenant_id=tenant_id,
        )


def _make_custom_agent(agent_class, tenant_id: int = 1, feature_side_effect=None):
    with (
        patch("src.core.agents.base_agent.get_settings") as mock_settings,
        patch(
            "src.core.agents.mixins.learning_mixin.get_feature_flag",
            side_effect=feature_side_effect or (lambda _name: True),
        ),
        patch("src.core.ai.router.AIRouter"),
        patch("src.core.ai.explainability.ReasoningTrace"),
    ):
        mock_settings.return_value.max_concurrent_tasks = 3
        return agent_class(
            agent_id="learning-agent",
            agent_type=AgentType.SPECIALIST,
            tenant_id=tenant_id,
        )


def test_mixin_sets_learning_enabled_true() -> None:
    agent = _make_agent(tenant_id=7)
    assert agent._learning_enabled is True
    assert agent._learning_tenant_id == 7
    assert "learning_agent_learning_agent" in agent._learning_flag_names


def test_observation_service_created_lazily() -> None:
    agent = _make_agent()
    assert agent._observation_service_instance is None
    service = agent.observation_service
    assert service is agent._observation_service_instance


def test_observation_service_returns_none_when_learning_disabled() -> None:
    agent = _make_custom_agent(_LearningAgent, tenant_id=7, feature_side_effect=lambda _name: False)
    assert agent.observation_service is None


def test_generated_and_als_groups_are_included_in_flag_names() -> None:
    generated_agent = _make_custom_agent(_GeneratedLearningAgent, tenant_id=7)
    als_agent = _make_custom_agent(_AlsLearningAgent, tenant_id=7)

    assert "learning_group_generated" in generated_agent._learning_flag_names
    assert "learning_group_technical" in generated_agent._learning_flag_names
    assert "learning_group_als" in als_agent._learning_flag_names
    assert "learning_group_specialist" in als_agent._learning_flag_names


def test_flag_lookup_failures_disable_learning_safely() -> None:
    agent = _make_custom_agent(
        _LearningAgent,
        tenant_id=7,
        feature_side_effect=RuntimeError("flag backend offline"),
    )
    assert agent._learning_enabled is False


def test_build_learning_context_contains_agent_and_task_fields() -> None:
    agent = _make_agent(tenant_id=9)
    task = _make_task()
    result = ExecutionResult(task_id=task.id, success=True, execution_time=1.25)
    context = agent._build_learning_context(task, result)
    assert context["agent_id"] == "learning-agent"
    assert context["tenant_id"] == 9
    assert context["task_id"] == task.id
    assert context["result_success"] is True


def test_build_outcome_metrics_contains_numeric_values() -> None:
    agent = _make_agent()
    task = _make_task()
    result = ExecutionResult(task_id=task.id, success=False, execution_time=2.5)
    metrics = agent._build_outcome_metrics(task, result)
    assert metrics["execution_time"] == 2.5
    assert metrics["success"] == 0.0
    assert metrics["error_count"] == 1.0


@pytest.mark.asyncio
async def test_record_observation_returns_id() -> None:
    agent = _make_agent()
    task = _make_task()
    result = ExecutionResult(task_id=task.id, success=True, execution_time=1.0)
    with patch.object(type(agent), "observation_service", new_callable=property, create=True):
        pass


@pytest.mark.asyncio
async def test_record_observation_uses_service() -> None:
    agent = _make_agent()
    task = _make_task()
    result = ExecutionResult(task_id=task.id, success=True, execution_time=1.0)
    mock_service = AsyncMock()
    mock_service.record = AsyncMock(return_value="obs-1")
    agent._observation_service_instance = mock_service
    observation_id = await agent._record_task_observation(task, result)
    assert observation_id == "obs-1"
    mock_service.record.assert_awaited_once()


@pytest.mark.asyncio
async def test_record_observation_disabled_returns_none() -> None:
    agent = _make_agent()
    agent._learning_enabled = False
    task = _make_task()
    result = ExecutionResult(task_id=task.id, success=True)
    assert await agent._record_task_observation(task, result) is None


@pytest.mark.asyncio
async def test_record_observation_with_missing_service_returns_none() -> None:
    agent = _make_agent()
    task = _make_task()
    result = ExecutionResult(task_id=task.id, success=True)
    with patch.object(
        type(agent), "observation_service", new_callable=PropertyMock, return_value=None
    ):
        assert await agent._record_task_observation(task, result) is None


@pytest.mark.asyncio
async def test_record_observation_service_error_returns_none() -> None:
    agent = _make_agent()
    task = _make_task()
    result = ExecutionResult(task_id=task.id, success=True)
    mock_service = AsyncMock()
    mock_service.record = AsyncMock(side_effect=RuntimeError("boom"))
    agent._observation_service_instance = mock_service
    assert await agent._record_task_observation(task, result) is None


@pytest.mark.asyncio
async def test_record_method_observation_disabled_returns_none() -> None:
    agent = _make_agent()
    agent._learning_enabled = False

    observation_id = await agent._record_method_observation(
        method_name="custom",
        args_snapshot={"args": []},
        result_snapshot={"success": True},
        duration_seconds=0.1,
    )

    assert observation_id is None


@pytest.mark.asyncio
async def test_record_method_observation_handles_service_errors() -> None:
    agent = _make_agent()
    mock_service = AsyncMock()
    mock_service.record = AsyncMock(side_effect=RuntimeError("boom"))
    agent._observation_service_instance = mock_service

    observation_id = await agent._record_method_observation(
        method_name="custom",
        args_snapshot={"args": []},
        result_snapshot={"success": False},
        duration_seconds=0.1,
    )

    assert observation_id is None
