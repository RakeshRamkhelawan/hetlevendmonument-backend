from __future__ import annotations

import pytest

from src.core.agents.learning_loop import LearningSource, LearningType
from tests.conftest import requires_postgres
from tests.helpers.db_verify import count_all_learning_records, total_learning_records
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
async def test_complete_learning_lifecycle_creates_learning_artifacts(
    phase7_learning_stack,
    phase7_session,
    phase7_tenant_id: int,
) -> None:
    observation_service = phase7_learning_stack["observation_service"]

    for index in range(20):
        await observation_service.record(
            source=LearningSource.TASK_EXECUTION,
            learning_type=LearningType.PATTERN_RECOGNITION,
            context=make_observation_context(
                tenant_id=phase7_tenant_id,
                agent_id="phase7-agent",
                agent_type="python_pro",
            ),
            observation_data=make_observation_payload(index),
            outcome_metrics=make_outcome_metrics(index),
        )

    counts = await count_all_learning_records(phase7_session, phase7_tenant_id)

    assert counts["observations"] >= 20
    assert counts["patterns"] >= 1
    assert counts["adaptations"] >= 1
    assert counts["insights"] >= 1
    assert total_learning_records(counts) >= 23
