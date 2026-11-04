from unittest.mock import AsyncMock

import pytest

from src.core.agents.learning_loop import LearningSource, LearningType
from src.core.learning.services.observation_service import ObservationService


@pytest.mark.asyncio
async def test_observation_triggers_pattern_analysis() -> None:
    service = ObservationService(tenant_id=1, observation_threshold=2)
    result1 = await service.record(
        source=LearningSource.TASK_EXECUTION,
        learning_type=LearningType.PERFORMANCE_OPTIMIZATION,
        context={"agent_id": "a1", "agent_type": "specialist", "task_type": "text"},
        observation_data={"step": 1},
        outcome_metrics={"success": 1.0, "execution_time": 0.1},
        confidence_score=0.9,
    )
    result2 = await service.record(
        source=LearningSource.TASK_EXECUTION,
        learning_type=LearningType.PERFORMANCE_OPTIMIZATION,
        context={"agent_id": "a1", "agent_type": "specialist", "task_type": "text"},
        observation_data={"step": 2},
        outcome_metrics={"success": 1.0, "execution_time": 0.2},
        confidence_score=0.95,
    )
    assert result1 is not None
    assert result2 is not None
    assert len(service.pattern_service.patterns) >= 1
    assert len(service.adaptation_service.rules) >= 1
    assert len(service.insight_service.insights) >= 1


@pytest.mark.asyncio
async def test_low_confidence_pattern_does_not_create_rule_or_insight() -> None:
    service = ObservationService(tenant_id=1, observation_threshold=2)
    for step in range(2):
        await service.record(
            source=LearningSource.TASK_EXECUTION,
            learning_type=LearningType.PERFORMANCE_OPTIMIZATION,
            context={"agent_id": "a2", "agent_type": "specialist", "task_type": "text"},
            observation_data={"step": step},
            outcome_metrics={"success": 0.0, "execution_time": 0.1},
            confidence_score=0.2,
        )
    assert len(service.pattern_service.patterns) >= 1
    assert len(service.adaptation_service.rules) == 0
    assert len(service.insight_service.insights) == 0


@pytest.mark.asyncio
async def test_chain_handles_pattern_service_error() -> None:
    service = ObservationService(tenant_id=1, observation_threshold=1)
    mock_pattern_service = AsyncMock()
    mock_pattern_service.register = AsyncMock(side_effect=RuntimeError("pattern boom"))
    service._pattern_service = mock_pattern_service
    observation_id = await service.record(
        source=LearningSource.TASK_EXECUTION,
        learning_type=LearningType.PERFORMANCE_OPTIMIZATION,
        context={"agent_id": "a3", "agent_type": "specialist", "task_type": "text"},
        observation_data={"step": 1},
        outcome_metrics={"success": 1.0, "execution_time": 0.1},
    )
    assert observation_id is not None


def test_relevant_rules_filter_by_context() -> None:
    from src.core.agents.learning_loop import AdaptationRule
    from src.core.learning.services.adaptation_service import AdaptationService

    service = AdaptationService(tenant_id=1)
    rule = AdaptationRule(
        id="rule-1",
        name="Prefer specialist path",
        condition='{"agent_type": "specialist", "task_type": "text"}',
        action='{"hint": "use learned path"}',
        parameters={},
        success_metrics=[],
        active=True,
    )
    service.rules[rule.id] = rule
    rules = service.get_relevant_rules({"agent_type": "specialist", "task_type": "text"})
    assert len(rules) == 1
