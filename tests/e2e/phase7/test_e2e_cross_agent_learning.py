from __future__ import annotations

import pytest

from src.core.agents.learning_loop import LearningSource, LearningType
from src.core.learning.cross_agent_service import CrossAgentLearningService
from tests.conftest import requires_postgres
from tests.helpers.db_verify import count_all_learning_records
from tests.helpers.factories import (
    make_observation_context,
    make_observation_payload,
    make_outcome_metrics,
)


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.no_mocks
@requires_postgres
async def test_cross_agent_learning_shares_patterns_to_related_agents(
    phase7_learning_stack,
    phase7_session,
    phase7_tenant_id: int,
) -> None:
    observation_service = phase7_learning_stack["observation_service"]
    cross_agent_service = CrossAgentLearningService(
        tenant_id=phase7_tenant_id,
        pattern_service=phase7_learning_stack["pattern_service"],
    )

    for index in range(20):
        await observation_service.record(
            source=LearningSource.TASK_EXECUTION,
            learning_type=LearningType.PATTERN_RECOGNITION,
            context=make_observation_context(
                tenant_id=phase7_tenant_id,
                agent_id="python-pro-phase7",
                agent_type="python_pro",
            ),
            observation_data=make_observation_payload(index),
            outcome_metrics=make_outcome_metrics(index),
        )

    related_patterns = await cross_agent_service.get_related_patterns(
        agent_type="ai_engineer",
        task_type="analysis",
    )
    counts = await count_all_learning_records(phase7_session, phase7_tenant_id)

    assert related_patterns
    assert any(
        pattern.trigger_conditions.get("agent_type") == "ai_engineer"
        and pattern.trigger_conditions.get("shared_from_agent_type") == "python_pro"
        for pattern in related_patterns
    )
    assert counts["patterns"] >= 1
    assert counts["audit_entries"] >= 1
