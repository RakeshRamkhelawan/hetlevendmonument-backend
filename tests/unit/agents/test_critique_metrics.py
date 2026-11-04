"""Unit tests: CriticAgent Prometheus metrics emission.

SP-AGT-007 Dag 1 -- Item A
Tests are RED before implementation (critique_score_histogram / critique_latency_seconds /
critique_panel_invocations_total do not yet exist in src/core/observability/metrics.py).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.agents.critic_agent import CriticAgent
from src.core.shared.interfaces import ExecutionResult


@pytest.fixture(autouse=True)
def reset_critic_singleton():
    """Ensure each test gets a fresh CriticAgent instance."""
    CriticAgent._instances.clear()
    yield
    CriticAgent._instances.clear()


@pytest.fixture
def mock_store():
    store = MagicMock()
    store.store = AsyncMock(return_value=True)
    return store


@pytest.mark.unit
@pytest.mark.asyncio
async def test_critique_score_histogram_observed(mock_store):
    """critique_score_histogram.labels(...).observe(score) called after critique_task()."""
    from src.core.observability.metrics import critique_score_histogram  # ImportError if not added

    agent = CriticAgent(tenant_id=1)
    agent._store = mock_store
    result = ExecutionResult(
        task_id="t1",
        success=True,
        output="Valid output with sufficient content for testing purposes.",
        execution_time=1.0,
    )

    with patch("src.core.agents.critic_agent.critique_score_histogram") as mock_hist:
        mock_obs = MagicMock()
        mock_hist.labels.return_value = mock_obs
        await agent.critique_task(agent_name="TestAgent", task_id="t1", result=result)

    mock_hist.labels.assert_called_once_with(tenant_id="1", mode="advisory")
    mock_obs.observe.assert_called_once()
    score = mock_obs.observe.call_args[0][0]
    assert 0.0 <= score <= 1.0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_critique_latency_histogram_observed(mock_store):
    """critique_latency_seconds.labels(...).observe(latency) called after critique_task()."""
    from src.core.observability.metrics import critique_latency_seconds  # ImportError if not added

    agent = CriticAgent(tenant_id=1)
    agent._store = mock_store
    result = ExecutionResult(
        task_id="t2",
        success=True,
        output="Valid output for latency test.",
        execution_time=1.0,
    )

    with patch("src.core.agents.critic_agent.critique_latency_seconds") as mock_lat:
        mock_obs = MagicMock()
        mock_lat.labels.return_value = mock_obs
        await agent.critique_task(agent_name="TestAgent", task_id="t2", result=result)

    mock_lat.labels.assert_called_once_with(mode="advisory")
    mock_obs.observe.assert_called_once()
    latency = mock_obs.observe.call_args[0][0]
    assert latency >= 0.0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_panel_counter_incremented_when_panel_activated(mock_store):
    """critique_panel_invocations_total.labels(...).inc() called when judge panel activates."""
    from src.core.observability.metrics import (
        critique_panel_invocations_total,
    )  # ImportError if not added

    agent = CriticAgent(tenant_id=1)
    agent._store = mock_store
    result = ExecutionResult(
        task_id="t3",
        success=True,
        output="Output with adequate length for ambiguous zone testing.",
        execution_time=1.0,
    )

    with patch("src.core.agents.critic_agent.critique_panel_invocations_total") as mock_ctr:
        mock_inc = MagicMock()
        mock_ctr.labels.return_value = mock_inc
        with patch.object(agent._heuristic_scorer, "score", return_value=(0.55, [], [])):
            with patch.object(agent, "_llm_critique", new=AsyncMock(return_value=(0.55, [], []))):
                with patch.object(
                    agent,
                    "_judge_panel_critique",
                    new=AsyncMock(return_value=None),
                ):
                    await agent.critique_task(
                        agent_name="TestAgent",
                        task_id="t3",
                        result=result,
                        use_llm=True,
                    )

    mock_ctr.labels.assert_called_once()
    mock_inc.inc.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_panel_counter_not_incremented_outside_ambiguous_zone(mock_store):
    """critique_panel_invocations_total.inc() NOT called when score is outside ambiguous zone."""
    from src.core.observability.metrics import (
        critique_panel_invocations_total,
    )  # ImportError if not added

    agent = CriticAgent(tenant_id=1)
    agent._store = mock_store
    result = ExecutionResult(
        task_id="t4",
        success=True,
        output="Very high quality output that passes all checks with excellent content.",
        execution_time=1.0,
    )

    with patch("src.core.agents.critic_agent.critique_panel_invocations_total") as mock_ctr:
        mock_inc = MagicMock()
        mock_ctr.labels.return_value = mock_inc
        with patch.object(agent._heuristic_scorer, "score", return_value=(0.95, [], [])):
            await agent.critique_task(
                agent_name="TestAgent",
                task_id="t4",
                result=result,
                use_llm=True,
            )

    mock_inc.inc.assert_not_called()
