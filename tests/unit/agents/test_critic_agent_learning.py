"""Unit tests: CriticAgent LearningMixin integration.

SP-AGT-007 Dag 1 -- Item C
Tests are RED before implementation:
- CriticAgent does not yet inherit LearningMixin
- _record_method_observation is not yet called from critique_task()
"""

import pytest
from unittest.mock import AsyncMock, call, patch

from src.core.agents.critic_agent import CriticAgent
from src.core.agents.mixins.learning_mixin import LearningMixin
from src.core.shared.interfaces import ExecutionResult


@pytest.fixture(autouse=True)
def reset_critic_singleton():
    CriticAgent._instances.clear()
    yield
    CriticAgent._instances.clear()


@pytest.fixture
def mock_store():
    from unittest.mock import MagicMock

    store = MagicMock()
    store.store = AsyncMock(return_value=True)
    return store


@pytest.mark.unit
def test_critic_agent_inherits_learning_mixin():
    """CriticAgent must inherit LearningMixin (RED: not yet in class definition)."""
    assert issubclass(CriticAgent, LearningMixin), (
        "CriticAgent must inherit from LearningMixin (SP-AGT-007 Item C)"
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_record_method_observation_called_after_critique_task(mock_store):
    """_record_method_observation() is called once after a successful critique_task()."""
    agent = CriticAgent(tenant_id=1)
    agent._store = mock_store
    result = ExecutionResult(
        task_id="obs-task-001",
        success=True,
        output="Valid output for observation test purposes.",
        execution_time=1.0,
    )

    with patch.object(
        agent, "_record_method_observation", new=AsyncMock(return_value=None)
    ) as mock_record:
        await agent.critique_task(
            agent_name="TestAgent",
            task_id="obs-task-001",
            result=result,
        )

    mock_record.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_observation_result_snapshot_contains_score_and_schema_valid(mock_store):
    """result_snapshot passed to _record_method_observation contains 'score' and 'schema_valid'."""
    agent = CriticAgent(tenant_id=1)
    agent._store = mock_store
    result = ExecutionResult(
        task_id="obs-task-002",
        success=True,
        output="Output for feature key test.",
        execution_time=1.0,
    )

    with patch.object(
        agent, "_record_method_observation", new=AsyncMock(return_value=None)
    ) as mock_record:
        await agent.critique_task(
            agent_name="TestAgent",
            task_id="obs-task-002",
            result=result,
        )

    _, kwargs = mock_record.call_args
    result_snapshot = kwargs.get("result_snapshot") or mock_record.call_args[0][2]
    assert "score" in result_snapshot, "result_snapshot must contain 'score'"
    assert "schema_valid" in result_snapshot, "result_snapshot must contain 'schema_valid'"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_observation_uses_panel_score_when_panel_activated(mock_store):
    """When judge panel activates, _record_method_observation receives the panel consensus score."""
    from src.core.agents.critic_agent import JudgePanelVerdict, SingleJudgeVerdict

    agent = CriticAgent(tenant_id=1)
    agent._store = mock_store
    result = ExecutionResult(
        task_id="obs-task-003",
        success=True,
        output="Output that lands in the ambiguous scoring zone for panel test.",
        execution_time=1.0,
    )
    panel_verdict = JudgePanelVerdict(
        consensus=0.55,
        verdicts=[SingleJudgeVerdict(judge_index=0, score=0.55)],
        raw_scores=[0.55],
    )

    with patch.object(
        agent, "_record_method_observation", new=AsyncMock(return_value=None)
    ) as mock_record:
        with patch.object(agent._heuristic_scorer, "score", return_value=(0.60, [], [])):
            with patch.object(agent, "_llm_critique", new=AsyncMock(return_value=(0.60, [], []))):
                with patch.object(
                    agent,
                    "_judge_panel_critique",
                    new=AsyncMock(return_value=panel_verdict),
                ):
                    await agent.critique_task(
                        agent_name="TestAgent",
                        task_id="obs-task-003",
                        result=result,
                        use_llm=True,
                    )

    _, kwargs = mock_record.call_args
    result_snapshot = kwargs.get("result_snapshot") or mock_record.call_args[0][2]
    assert abs(result_snapshot["score"] - 0.55) < 1e-6, (
        f"Expected panel consensus score 0.55, got {result_snapshot['score']}"
    )
