from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timezone

import pytest

from src.core.agents.learning_loop import LearningObservation, LearningSource, LearningType
from tests.helpers.factories import (
    make_observation_context,
    make_observation_payload,
    make_outcome_metrics,
)

if os.getenv("RUN_PHASE7_BENCHMARKS") != "true":
    pytest.skip(
        "Phase 7 benchmarks disabled. Set RUN_PHASE7_BENCHMARKS=true.",
        allow_module_level=True,
    )


PHASE7_P95_BUDGET_SECONDS = float(os.getenv("PHASE7_P95_BUDGET_SECONDS", "0.05"))


@pytest.mark.asyncio
@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.slow
@pytest.mark.no_mocks
async def test_observation_recording_latency_p95_within_budget(
    phase7_learning_stack,
    phase7_tenant_id: int,
) -> None:
    repository = phase7_learning_stack["repository"]
    durations: list[float] = []

    for index in range(30):
        observation = LearningObservation(
            id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
            source=LearningSource.TASK_EXECUTION,
            learning_type=LearningType.PATTERN_RECOGNITION,
            context=make_observation_context(
                tenant_id=phase7_tenant_id,
                agent_id=f"phase7-benchmark-{index}",
                agent_type="python_pro",
            ),
            observation_data=make_observation_payload(index),
            outcome_metrics=make_outcome_metrics(index),
            confidence_score=0.8,
            importance_score=0.5,
        )
        started_at = time.perf_counter()
        await repository.save_observation(phase7_tenant_id, observation)
        durations.append(time.perf_counter() - started_at)

    sorted_durations = sorted(durations)
    p95_index = max(0, min(len(sorted_durations) - 1, int(len(sorted_durations) * 0.95) - 1))
    p95_seconds = sorted_durations[p95_index]

    assert p95_seconds < PHASE7_P95_BUDGET_SECONDS
