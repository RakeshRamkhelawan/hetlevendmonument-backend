"""
Performance tests for Agent Council deliberation.

Set RUN_PERFORMANCE=1 to execute these benchmarks.
These tests live under tests/integration/copilot/ so they can reuse the
real_council fixture and postgres_session infrastructure.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time

import pytest

from src.core.copilot.council.types import DecisionVerdict, ProposalTrigger
from tests.integration.copilot.conftest import make_proposal

RUN_PERFORMANCE = os.getenv("RUN_PERFORMANCE") == "1"

pytestmark = pytest.mark.performance

logger = logging.getLogger(__name__)


@pytest.mark.skipif(
    not RUN_PERFORMANCE,
    reason="Set RUN_PERFORMANCE=1 to run performance tests",
)
@pytest.mark.integration
@pytest.mark.als
@pytest.mark.requires_postgres
@pytest.mark.asyncio
async def test_council_deliberation_p95_under_500ms(real_council, db_session):
    """P95 deliberation latency over 1000 proposals < 500ms (ADR-027 SLA)."""
    latencies_ms: list[float] = []

    for i in range(1000):
        # Mix proposals to exercise realistic paths
        if i % 10 == 0:
            proposal = make_proposal(
                action_type="delete_user_data",
                reasoning="Bulk cleanup requested.",
            )
        elif i % 10 == 1:
            proposal = make_proposal(
                reasoning="Typisch voor mannen om dit te willen.",
            )
        elif i % 10 == 2:
            proposal = make_proposal(
                trigger=ProposalTrigger.PROACTIVE_MONITOR,
                action_type="notify_user",
            )
        else:
            proposal = make_proposal(
                user_id=(i % 50) + 1,  # vary user to avoid budget exhaustion
            )

        start = time.perf_counter()
        decision = await real_council.deliberate(proposal)
        elapsed_ms = (time.perf_counter() - start) * 1000
        latencies_ms.append(elapsed_ms)

        # Basic sanity: decision must be one of the expected verdicts
        assert decision.verdict in {
            DecisionVerdict.APPROVED,
            DecisionVerdict.MODIFIED,
            DecisionVerdict.HITL_REQUIRED,
            DecisionVerdict.DEFERRED,
            DecisionVerdict.BLOCKED,
        }

    # Percentiles (simple sort-based calculation)
    latencies_ms.sort()
    p50 = latencies_ms[int(len(latencies_ms) * 0.50)]
    p95 = latencies_ms[int(len(latencies_ms) * 0.95)]
    p99 = latencies_ms[int(len(latencies_ms) * 0.99)]

    logger.info("Council deliberation latency: P50=%.1fms P95=%.1fms P99=%.1fms", p50, p95, p99)

    # Soft assertion: warn if close, fail if over
    assert p95 < 500, f"P95 = {p95:.1f}ms exceeds 500ms SLA"


@pytest.mark.skipif(
    not RUN_PERFORMANCE,
    reason="Set RUN_PERFORMANCE=1 to run performance tests",
)
@pytest.mark.integration
@pytest.mark.als
@pytest.mark.requires_postgres
@pytest.mark.asyncio
async def test_council_handles_100_concurrent_deliberations(real_council, db_session):
    """100 parallel deliberations without errors, no race conditions."""
    proposals = [
        make_proposal(
            user_id=(i % 50) + 1,
            action_type="navigate_to",
            action_params={"page": f"/page{i}"},
        )
        for i in range(100)
    ]

    results = await asyncio.gather(
        *[real_council.deliberate(p) for p in proposals],
        return_exceptions=True,
    )

    exceptions = [r for r in results if isinstance(r, Exception)]
    assert not exceptions, f"{len(exceptions)} exceptions during concurrent run: {exceptions[:3]}"

    # Idempotency check: all decision IDs must be unique
    decision_ids = {r.decision_id for r in results}
    assert len(decision_ids) == 100
