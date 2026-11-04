from __future__ import annotations

import importlib.util
from pathlib import Path
from unittest.mock import patch

import pytest

from src.core.agents.base_agent import EnhancedBaseAgent
from src.core.shared.interfaces import ExecutionResult, TaskData
from src.core.types import AgentType


class _Phase4Agent(EnhancedBaseAgent):
    async def _execute_task(self, task: TaskData) -> ExecutionResult:
        return ExecutionResult(task_id=task.id, success=True)


class _GeneratedPhase4Agent(_Phase4Agent):
    pass


_GeneratedPhase4Agent.__module__ = "src.core.agents.generated.phase4_agent"


def _make_agent(
    *,
    agent_class: type[EnhancedBaseAgent] = _Phase4Agent,
    agent_id: str = "phase4-agent",
    agent_type: AgentType = AgentType.SPECIALIST,
    feature_side_effect=None,
) -> EnhancedBaseAgent:
    with (
        patch("src.core.agents.base_agent.get_settings") as mock_settings,
        patch(
            "src.core.agents.mixins.learning_mixin.get_feature_flag",
            side_effect=feature_side_effect or (lambda _name: False),
        ),
        patch("src.core.ai.router.AIRouter"),
        patch("src.core.ai.explainability.ReasoningTrace"),
    ):
        mock_settings.return_value.max_concurrent_tasks = 3
        return agent_class(
            agent_id=agent_id,
            agent_type=agent_type,
            tenant_id=7,
        )


def _load_constructor_verifier_module():
    module_path = (
        Path(__file__).resolve().parents[3]
        / "scripts"
        / "verification"
        / "verify_agent_constructors.py"
    )
    spec = importlib.util.spec_from_file_location("verify_agent_constructors", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_learning_disabled_by_default() -> None:
    agent = _make_agent()
    assert agent._learning_enabled is False
    assert agent._learning_tenant_id == 0


def test_global_learning_flag_enables_learning() -> None:
    agent = _make_agent(feature_side_effect=lambda name: name == "learning_enabled")
    assert agent._learning_enabled is True


def test_generated_group_flag_enables_generated_agents() -> None:
    agent = _make_agent(
        agent_class=_GeneratedPhase4Agent,
        feature_side_effect=lambda name: name == "learning_group_generated",
    )
    assert agent._learning_enabled is True
    assert "learning_group_generated" in agent._learning_flag_names
    assert "learning_group_technical" in agent._learning_flag_names


def test_agent_specific_flag_enables_named_agent() -> None:
    agent = _make_agent(
        agent_id="SEO Meta Optimizer",
        feature_side_effect=lambda name: name == "learning_agent_seo_meta_optimizer",
    )
    assert agent._learning_enabled is True
    assert "learning_agent_seo_meta_optimizer" in agent._learning_flag_names


def test_constructor_verifier_finds_no_generated_agent_issues() -> None:
    """The 73 fake-stub EnhancedBaseAgent-based files in src/core/agents/generated/
    were removed as confirmed-dead code (0 production/test callers, see ADR-036
    audit-to-fix AUDIT-006) -- checked_count == 0 is therefore the correct,
    current state, not a regression. The remaining 6 files in that directory
    (5 agency_*_agent.py compatibility stubs + tenant_service.py) do not
    subclass EnhancedBaseAgent, so the verifier legitimately finds nothing to
    check. If a real EnhancedBaseAgent-based generated agent is ever added
    back, this test still enforces that its constructor has zero issues."""
    verifier = _load_constructor_verifier_module()
    result = verifier.verify_generated_agent_constructors(Path.cwd())
    assert result["issue_count"] == 0
    assert result["checked_count"] == 0


@pytest.mark.asyncio
async def test_disabled_learning_skips_observation_recording() -> None:
    agent = _make_agent()
    task = TaskData(id="phase4-task", title="Task", description="Desc", metadata={"type": "text"})
    assert (
        await agent._record_task_observation(task, ExecutionResult(task_id=task.id, success=True))
        is None
    )
