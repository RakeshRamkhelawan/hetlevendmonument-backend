"""Unit tests: ShadowCEO critique-score als risicosignaal (Check 6).

SP-AGT-008 Dag 1 -- Item E
Tests zijn ROOD voor implementatie: _CRITIQUE_RISK_THRESHOLD en
_assess_critique_risk() bestaan nog niet op ShadowCEO.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.core.als.enterprise.shadow.shadow_ceo import RiskLevel, ShadowCEO
from src.core.shared.interfaces import TaskData
from src.core.types import TaskPriority


def _make_signal_bus() -> MagicMock:
    bus = MagicMock()
    bus.emit = AsyncMock()
    return bus


def _make_task(task_id: str = "task-001") -> TaskData:
    return TaskData(
        id=task_id,
        title="Test task",
        description="Test description",
        priority=TaskPriority.MEDIUM,
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_shadow_ceo_has_critique_risk_threshold() -> None:
    """ShadowCEO._CRITIQUE_RISK_THRESHOLD moet bestaan en gelijk zijn aan 0.35."""
    # AttributeError als niet geimplementeerd -- RED voor implementatie
    assert hasattr(ShadowCEO, "_CRITIQUE_RISK_THRESHOLD"), (
        "ShadowCEO._CRITIQUE_RISK_THRESHOLD moet gedefinieerd zijn"
    )
    assert ShadowCEO._CRITIQUE_RISK_THRESHOLD == 0.35


@pytest.mark.unit
@pytest.mark.asyncio
async def test_review_task_veto_when_critique_score_low() -> None:
    """review_task() geeft veto als gemiddelde critique-score < _CRITIQUE_RISK_THRESHOLD."""
    shadow = ShadowCEO(tenant_id=1, signal_bus=_make_signal_bus())
    task = _make_task()

    with patch.object(
        shadow,
        "_assess_critique_risk",
        new=AsyncMock(return_value=(RiskLevel.HIGH, "critique_score_low avg=0.20")),
    ):
        # Zorg dat de overige 5 checks laag blijven -- patch ze weg
        with patch.object(shadow, "_assess_complexity", return_value=0.1):
            with patch.object(shadow, "_assess_byzantine_risk", return_value=0.1):
                with patch.object(shadow, "_assess_cascade_risk", return_value=0.1):
                    with patch.object(shadow, "_check_threat_patterns", return_value=None):
                        veto = await shadow.review_task(task, proposed_agent="LowScoreAgent")

    assert veto is not None
    assert veto.risk_level in [RiskLevel.HIGH, RiskLevel.CRITICAL]
    assert "critique_score" in veto.veto_reason.lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_review_task_no_veto_when_critique_score_high() -> None:
    """review_task() geeft GEEN veto bij hoge critique-score (score > threshold)."""
    shadow = ShadowCEO(tenant_id=1, signal_bus=_make_signal_bus())
    task = _make_task()

    with patch.object(
        shadow, "_assess_critique_risk", new=AsyncMock(return_value=(RiskLevel.NONE, None))
    ):
        with patch.object(shadow, "_assess_complexity", return_value=0.1):
            with patch.object(shadow, "_assess_byzantine_risk", return_value=0.1):
                with patch.object(shadow, "_assess_cascade_risk", return_value=0.1):
                    with patch.object(shadow, "_check_threat_patterns", return_value=None):
                        veto = await shadow.review_task(task, proposed_agent="HighScoreAgent")

    assert veto is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_review_task_no_veto_when_no_critique_data() -> None:
    """review_task() geeft GEEN veto als er geen critique-data bestaat voor de agent."""
    shadow = ShadowCEO(tenant_id=1, signal_bus=_make_signal_bus())
    task = _make_task()

    with patch.object(
        shadow, "_assess_critique_risk", new=AsyncMock(return_value=(RiskLevel.NONE, None))
    ):
        with patch.object(shadow, "_assess_complexity", return_value=0.1):
            with patch.object(shadow, "_assess_byzantine_risk", return_value=0.1):
                with patch.object(shadow, "_assess_cascade_risk", return_value=0.1):
                    with patch.object(shadow, "_check_threat_patterns", return_value=None):
                        veto = await shadow.review_task(task, proposed_agent="NewAgent")

    assert veto is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_assess_critique_risk_pulls_from_critique_store() -> None:
    """_assess_critique_risk() bestaat, roept CritiqueStore.get_by_agent() aan."""
    # AttributeError als _assess_critique_risk niet bestaat -- RED voor implementatie
    shadow = ShadowCEO(tenant_id=1, signal_bus=_make_signal_bus())
    assert hasattr(shadow, "_assess_critique_risk"), (
        "ShadowCEO._assess_critique_risk() moet geimplementeerd zijn"
    )

    from src.core.agents.critique_store import Critique

    low_critique = Critique(
        critique_id="c1",
        agent_name="TestAgent",
        task_id="t1",
        tenant_id=1,
        score=0.25,
        issues=[],
        suggestions=[],
        mode="advisory",
    )

    mock_store = MagicMock()
    mock_store.get_by_agent = AsyncMock(return_value=[low_critique])

    with patch(
        "src.core.agents.critique_store.get_critique_store",
        return_value=mock_store,
    ):
        risk_level, reason = await shadow._assess_critique_risk("TestAgent")

    assert risk_level == RiskLevel.HIGH
    assert reason is not None
    assert "critique_score" in reason.lower()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_assess_critique_risk_absorbs_store_exception() -> None:
    """_assess_critique_risk() absorbeert exceptions -- nooit propageren naar review_task()."""
    shadow = ShadowCEO(tenant_id=1, signal_bus=_make_signal_bus())

    with patch(
        "src.core.agents.critique_store.get_critique_store",
        side_effect=RuntimeError("store unavailable"),
    ):
        risk_level, reason = await shadow._assess_critique_risk("AnyAgent")

    assert risk_level == RiskLevel.NONE
    assert reason is None
