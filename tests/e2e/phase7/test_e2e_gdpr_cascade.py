from __future__ import annotations

import pytest

from src.core.agents.learning_loop import LearningSource, LearningType
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
async def test_gdpr_full_cascade_removes_learning_records(
    phase7_learning_stack,
    phase7_session,
    phase7_tenant_id: int,
) -> None:
    observation_service = phase7_learning_stack["observation_service"]
    gdpr_service = phase7_learning_stack["gdpr_service"]
    user_id = "phase7-user"

    for index in range(20):
        context = make_observation_context(
            tenant_id=phase7_tenant_id,
            agent_id="phase7-agent",
            agent_type="python_pro",
        )
        context["user_id"] = user_id
        payload = make_observation_payload(index)
        payload["user_id"] = user_id
        await observation_service.record(
            source=LearningSource.TASK_EXECUTION,
            learning_type=LearningType.PATTERN_RECOGNITION,
            context=context,
            observation_data=payload,
            outcome_metrics=make_outcome_metrics(index),
        )

    before_counts = await count_all_learning_records(phase7_session, phase7_tenant_id)
    report = await gdpr_service.delete_user_data(
        user_id=user_id,
        tenant_id=phase7_tenant_id,
        requested_by_user_id=1,
        reason="phase7_e2e_cleanup",
    )
    after_counts = await count_all_learning_records(phase7_session, phase7_tenant_id)

    assert total_learning_records(before_counts) > 0
    assert report.total_deleted > 0
    assert after_counts["observations"] == 0
    assert after_counts["patterns"] == 0
    assert after_counts["adaptations"] == 0
    assert after_counts["insights"] == 0
    assert after_counts["audit_entries"] >= 1
