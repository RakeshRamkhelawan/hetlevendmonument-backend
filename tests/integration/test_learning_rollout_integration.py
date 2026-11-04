"""Integration tests for Phase 4 learning rollout and rollback via environment flags."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.core.agents.base_agent import EnhancedBaseAgent
from src.core.shared.config import get_feature_flag, reload_settings
from src.core.shared.interfaces import ExecutionResult, TaskData
from src.core.types import AgentType


class _IntegrationLearningAgent(EnhancedBaseAgent):
    async def _execute_task(self, task: TaskData) -> ExecutionResult:
        return ExecutionResult(task_id=task.id, success=True, result_data={"task": task.title})


class _GeneratedIntegrationLearningAgent(_IntegrationLearningAgent):
    pass


_GeneratedIntegrationLearningAgent.__module__ = "src.core.agents.generated.phase4_rollout_agent"


def _make_task(task_id: str = "phase4-integration-task") -> TaskData:
    return TaskData(
        id=task_id,
        title="Phase 4 rollout",
        description="Validate learning feature rollout",
        metadata={"type": "text"},
    )


def _build_agent(
    agent_class: type[EnhancedBaseAgent] = _IntegrationLearningAgent,
    *,
    agent_id: str = "integration-agent",
    agent_type: AgentType = AgentType.SPECIALIST,
    tenant_id: int = 17,
) -> EnhancedBaseAgent:
    with (
        patch("src.core.agents.base_agent.get_settings") as mock_settings,
        patch("src.core.ai.router.AIRouter"),
        patch("src.core.ai.explainability.ReasoningTrace"),
    ):
        mock_settings.return_value.max_concurrent_tasks = 3
        return agent_class(
            agent_id=agent_id,
            agent_type=agent_type,
            tenant_id=tenant_id,
        )


@pytest.fixture
def learning_env(monkeypatch: pytest.MonkeyPatch):
    tracked_keys = [
        "FEATURE_LEARNING_ENABLED",
        "FEATURE_LEARNING_GROUP_CORE",
        "FEATURE_LEARNING_GROUP_GENERATED",
        "FEATURE_LEARNING_GROUP_SPECIALIST",
        "FEATURE_LEARNING_GROUP_TECHNICAL",
        "FEATURE_LEARNING_AGENT_INTEGRATION_AGENT",
        "FEATURE_LEARNING_AGENT_TYPE_SPECIALIST",
    ]
    for key in tracked_keys:
        monkeypatch.delenv(key, raising=False)
    reload_settings()
    yield monkeypatch
    for key in tracked_keys:
        monkeypatch.delenv(key, raising=False)
    reload_settings()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_learning_global_env_rollout_and_rollback(learning_env: pytest.MonkeyPatch) -> None:
    learning_env.setenv("FEATURE_LEARNING_ENABLED", "true")
    reload_settings()

    enabled_agent = _build_agent()
    assert get_feature_flag("learning_enabled") is True
    assert enabled_agent._learning_enabled is True
    assert enabled_agent.observation_service is not None

    learning_env.setenv("FEATURE_LEARNING_ENABLED", "false")
    reload_settings()

    disabled_agent = _build_agent()
    result = await disabled_agent.process_task(_make_task("rollback-global"))

    assert result.success is True
    assert get_feature_flag("learning_enabled") is False
    assert disabled_agent._learning_enabled is False
    assert disabled_agent._observation_service_instance is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_generated_group_env_toggle_rolls_back_cleanly(
    learning_env: pytest.MonkeyPatch,
) -> None:
    learning_env.setenv("FEATURE_LEARNING_GROUP_GENERATED", "1")
    reload_settings()

    enabled_agent = _build_agent(_GeneratedIntegrationLearningAgent, agent_id="generated-agent")
    assert enabled_agent._learning_enabled is True
    assert "learning_group_generated" in enabled_agent._learning_flag_names

    learning_env.delenv("FEATURE_LEARNING_GROUP_GENERATED", raising=False)
    reload_settings()

    disabled_agent = _build_agent(_GeneratedIntegrationLearningAgent, agent_id="generated-agent")
    result = await disabled_agent.process_task(_make_task("rollback-generated"))

    assert result.success is True
    assert disabled_agent._learning_enabled is False
    assert disabled_agent._observation_service_instance is None


@pytest.mark.asyncio
@pytest.mark.integration
async def test_agent_specific_env_toggle_does_not_enable_other_agents(
    learning_env: pytest.MonkeyPatch,
) -> None:
    learning_env.setenv("FEATURE_LEARNING_AGENT_INTEGRATION_AGENT", "yes")
    reload_settings()

    targeted_agent = _build_agent(agent_id="integration-agent")
    other_agent = _build_agent(agent_id="other-agent")

    assert targeted_agent._learning_enabled is True
    assert other_agent._learning_enabled is False


@pytest.mark.asyncio
@pytest.mark.integration
async def test_group_env_rollback_stops_new_observation_service_initialization(
    learning_env: pytest.MonkeyPatch,
) -> None:
    learning_env.setenv("FEATURE_LEARNING_GROUP_SPECIALIST", "on")
    reload_settings()

    enabled_agent = _build_agent(agent_id="specialist-agent")
    assert enabled_agent._learning_enabled is True
    assert enabled_agent.observation_service is not None

    learning_env.setenv("FEATURE_LEARNING_GROUP_SPECIALIST", "off")
    reload_settings()

    disabled_agent = _build_agent(agent_id="specialist-agent")
    observation_id = await disabled_agent._record_task_observation(
        _make_task("rollback-observation"),
        ExecutionResult(task_id="rollback-observation", success=True),
    )

    assert observation_id is None
    assert disabled_agent._learning_enabled is False
    assert disabled_agent._observation_service_instance is None
