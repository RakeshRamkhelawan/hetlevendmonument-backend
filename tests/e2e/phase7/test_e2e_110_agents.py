from __future__ import annotations

import asyncio

import pytest

from src.core.agents.learning_loop import LearningSource, LearningType
from tests.helpers.db_verify import count_observations
from tests.helpers.factories import (
    make_observation_context,
    make_observation_payload,
    make_outcome_metrics,
)


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.no_mocks
async def test_110_agents_simultaneous_preserves_tenant_isolation(
    phase7_learning_stack,
    phase7_stack_factory,
    phase7_session,
    phase7_tenant_id: int,
    phase7_secondary_tenant_id: int,
) -> None:
    primary_observation_service = phase7_learning_stack["observation_service"]
    secondary_stack = await phase7_stack_factory(phase7_secondary_tenant_id)
    secondary_observation_service = secondary_stack["observation_service"]

    async def record(
        *,
        observation_service,
        tenant_id: int,
        agent_id: str,
        agent_type: str,
        index: int,
    ) -> None:
        await observation_service.record(
            source=LearningSource.TASK_EXECUTION,
            learning_type=LearningType.PATTERN_RECOGNITION,
            context=make_observation_context(
                tenant_id=tenant_id,
                agent_id=agent_id,
                agent_type=agent_type,
            ),
            observation_data=make_observation_payload(index),
            outcome_metrics=make_outcome_metrics(index),
        )

    primary_tasks = [
        record(
            observation_service=primary_observation_service,
            tenant_id=phase7_tenant_id,
            agent_id=f"phase7-agent-{index:03d}",
            agent_type="python_pro",
            index=index,
        )
        for index in range(110)
    ]
    secondary_tasks = [
        record(
            observation_service=secondary_observation_service,
            tenant_id=phase7_secondary_tenant_id,
            agent_id=f"phase7-secondary-agent-{index:03d}",
            agent_type="ai_engineer",
            index=index,
        )
        for index in range(25)
    ]

    await asyncio.gather(*primary_tasks, *secondary_tasks)

    primary_count = await count_observations(phase7_session, phase7_tenant_id)
    secondary_count = await count_observations(phase7_session, phase7_secondary_tenant_id)

    assert primary_count == 110
    assert secondary_count == 25
