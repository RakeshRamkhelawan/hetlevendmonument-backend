"""TDD tests voor _judge_panel_critique() -- SP-AGT-006 Dag 2."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.agents.critic_agent import CriticAgent, HeuristicScorer


# ---------------------------------------------------------------------------
# Test 2.1 -- Panel geactiveerd bij ambigue score (0.35-0.75)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_judge_panel_activated_in_ambiguous_zone():
    CriticAgent._instances.pop(10, None)
    agent = CriticAgent(tenant_id=10)

    result_mock = MagicMock()
    result_mock.output = "Geldige output met voldoende inhoud voor de test."

    from src.core.agents.critic_agent import JudgePanelVerdict, SingleJudgeVerdict

    fake_verdict = JudgePanelVerdict(
        consensus=0.58,
        verdicts=[SingleJudgeVerdict(judge_index=0, score=0.58)],
        outliers_removed=0,
        failed_judges=0,
        raw_scores=[0.58],
    )

    with (
        patch.object(HeuristicScorer, "score", return_value=(0.55, [], [])),
        patch.object(agent, "_llm_critique", new_callable=AsyncMock, return_value=(0.60, [], [])),
        patch.object(
            agent, "_judge_panel_critique", new_callable=AsyncMock, return_value=fake_verdict
        ) as mock_panel,
        patch.object(agent._store, "store", new_callable=AsyncMock),
    ):
        critique = await agent.critique_task(
            agent_name="TestAgent",
            task_id="t-panel-1",
            result=result_mock,
            use_llm=True,
        )

    mock_panel.assert_called_once_with("TestAgent", result_mock)
    assert critique.metadata.get("judge_panel") is not None
    assert abs(critique.score - 0.58) < 0.01


# ---------------------------------------------------------------------------
# Test 2.2 -- Panel NIET geactiveerd bij lage score (< 0.35)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_judge_panel_not_activated_low_score():
    CriticAgent._instances.pop(11, None)
    agent = CriticAgent(tenant_id=11)

    result_mock = MagicMock()
    result_mock.output = "Geldige output."

    with (
        patch.object(HeuristicScorer, "score", return_value=(0.20, ["error"], [])),
        patch.object(agent, "_llm_critique", new_callable=AsyncMock, return_value=(0.15, [], [])),
        patch.object(agent, "_judge_panel_critique", new_callable=AsyncMock) as mock_panel,
        patch.object(agent._store, "store", new_callable=AsyncMock),
    ):
        critique = await agent.critique_task(
            agent_name="TestAgent",
            task_id="t-panel-2",
            result=result_mock,
            use_llm=True,
        )

    mock_panel.assert_not_called()
    assert critique.metadata.get("judge_panel") is None


# ---------------------------------------------------------------------------
# Test 2.3 -- Panel NIET geactiveerd bij hoge score (> 0.75)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_judge_panel_not_activated_high_score():
    CriticAgent._instances.pop(12, None)
    agent = CriticAgent(tenant_id=12)

    result_mock = MagicMock()
    result_mock.output = "Uitstekende en volledige output met alle vereiste informatie."

    with (
        patch.object(HeuristicScorer, "score", return_value=(0.90, [], [])),
        patch.object(agent, "_judge_panel_critique", new_callable=AsyncMock) as mock_panel,
        patch.object(agent._store, "store", new_callable=AsyncMock),
    ):
        await agent.critique_task(
            agent_name="TestAgent",
            task_id="t-panel-3",
            result=result_mock,
            use_llm=True,
        )

    mock_panel.assert_not_called()


# ---------------------------------------------------------------------------
# Test 2.4 -- Consensus berekening (3 judges, geen outlier)
# ---------------------------------------------------------------------------


def test_judge_panel_consensus_no_outlier():
    CriticAgent._instances.pop(13, None)
    agent = CriticAgent(tenant_id=13)

    raw_results: list[tuple[int, float | None]] = [(0, 0.60), (1, 0.62), (2, 0.58)]
    verdict = agent._build_judge_panel_verdict(raw_results, failed_count=0)

    assert verdict is not None
    assert abs(verdict.consensus - 0.60) < 0.01
    assert len(verdict.verdicts) == 3
    assert verdict.outliers_removed == 0


# ---------------------------------------------------------------------------
# Test 2.5 -- Outlier filtering (3 judges, 1 outlier buiten _OUTLIER_THRESHOLD=0.30)
# ---------------------------------------------------------------------------


def test_judge_panel_outlier_filtering():
    CriticAgent._instances.pop(14, None)
    agent = CriticAgent(tenant_id=14)

    raw_results: list[tuple[int, float | None]] = [(0, 0.60), (1, 0.62), (2, 0.10)]

    verdict = agent._build_judge_panel_verdict(raw_results, failed_count=0)

    assert verdict is not None
    assert verdict.outliers_removed == 1
    assert verdict.consensus > 0.55


# ---------------------------------------------------------------------------
# Test 2.6 -- Volledige timeout fallback (alle judges time out)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_judge_panel_full_timeout_fallback():
    CriticAgent._instances.pop(15, None)
    agent = CriticAgent(tenant_id=15)

    result_mock = MagicMock()
    result_mock.output = "Geldige output voor timeout test."

    with (
        patch.object(HeuristicScorer, "score", return_value=(0.55, [], [])),
        patch.object(agent, "_llm_critique", new_callable=AsyncMock, return_value=(0.60, [], [])),
        patch.object(
            agent,
            "_run_judge_panel",
            new_callable=AsyncMock,
            return_value=[(0, None), (1, None), (2, None)],
        ),
        patch.object(agent._store, "store", new_callable=AsyncMock),
    ):
        critique = await agent.critique_task(
            agent_name="TestAgent",
            task_id="t-timeout",
            result=result_mock,
            use_llm=True,
        )

    assert critique is not None
    panel_meta = critique.metadata.get("judge_panel")
    assert panel_meta is None or panel_meta.get("error") == "panel_timeout"


# ---------------------------------------------------------------------------
# Test 2.7 -- Partial failure (1 van 3 judges time out)
# ---------------------------------------------------------------------------


def test_judge_panel_partial_failure():
    CriticAgent._instances.pop(16, None)
    agent = CriticAgent(tenant_id=16)

    raw_results: list[tuple[int, float | None]] = [(0, 0.58), (1, 0.62), (2, None)]

    verdict = agent._build_judge_panel_verdict(raw_results, failed_count=1)

    assert verdict is not None
    assert verdict.failed_judges == 1
    assert len(verdict.verdicts) == 2
    assert abs(verdict.consensus - 0.60) < 0.01


# ---------------------------------------------------------------------------
# Test 2.8 -- JudgePanelVerdict schema validatie
# ---------------------------------------------------------------------------


def test_judge_panel_verdict_schema():
    from src.core.agents.critic_agent import JudgePanelVerdict, SingleJudgeVerdict

    v = JudgePanelVerdict(
        consensus=0.6,
        verdicts=[SingleJudgeVerdict(judge_index=0, score=0.6)],
        outliers_removed=0,
        failed_judges=0,
        raw_scores=[0.6],
    )

    assert 0.0 <= v.consensus <= 1.0
    assert isinstance(v.verdicts, list)
    assert v.outliers_removed >= 0
    assert v.failed_judges >= 0
