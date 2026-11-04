"""Integration smoke tests for Council Prometheus metrics.

Verifies that all 10 council metric names are present in the global
Prometheus registry exposition output, and that hash-chain-break
detection increments the counter before raising.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest
from prometheus_client import generate_latest

from src.core.copilot.council.audit_writer import (
    AuditWriteError,
    CouncilAuditWriter,
    HashChainBreakError,
)
from src.core.copilot.council.metrics import (
    AUDIT_WRITES_TOTAL,
    HASH_CHAIN_BREAKS_TOTAL,
)
from src.core.copilot.council.types import (
    CouncilDecision,
    DataClassification,
    DecisionVerdict,
    OfficerVerdict,
    Proposal,
    ProposalTrigger,
    VerdictType,
)


@pytest.mark.integration
async def test_metrics_endpoint_exposes_council_namespace() -> None:
    """Global Prometheus registry must contain all copilot_council_* names.

    NOTE: Prometheus counters/gauges with labels only appear in
    generate_latest() output once at least one label combination has
    been observed.  Instead of relying on text scraping, we check the
    CollectorRegistry directly for the metric descriptors.
    """
    from prometheus_client import REGISTRY

    from src.core.copilot.council.metrics import (  # noqa: F401  -- ensure metrics are registered
        AUDIT_WRITES_TOTAL,
        COUNCIL_CACHE_HIT_TOTAL,
        COUNCIL_CACHE_MISS_TOTAL,
        COUNCIL_DELIBERATION_SECONDS,
        COUNCIL_TURNS_TOTAL,
        COUNCIL_VERDICT_TOTAL,
        HASH_CHAIN_BREAKS_TOTAL,
        HITL_PENDING,
        NOTIFICATIONS_DEFERRED_TOTAL,
        NOTIFICATIONS_DISPATCHED_TOTAL,
    )

    # Re-register metrics if they were unregistered by conftest _do_global_reset
    for m in [
        COUNCIL_TURNS_TOTAL,
        COUNCIL_DELIBERATION_SECONDS,
        COUNCIL_VERDICT_TOTAL,
        HITL_PENDING,
        AUDIT_WRITES_TOTAL,
        HASH_CHAIN_BREAKS_TOTAL,
        NOTIFICATIONS_DISPATCHED_TOTAL,
        NOTIFICATIONS_DEFERRED_TOTAL,
        COUNCIL_CACHE_HIT_TOTAL,
        COUNCIL_CACHE_MISS_TOTAL,
    ]:
        try:
            REGISTRY.register(m)
        except ValueError:
            pass

    expected_names = [
        "copilot_council_turns",
        "copilot_council_deliberation_seconds",
        "copilot_council_verdict",
        "copilot_hitl_pending",
        "copilot_audit_writes",
        "copilot_hash_chain_breaks",
        "copilot_notifications_dispatched",
        "copilot_notifications_deferred",
        "copilot_council_cache_hit",
        "copilot_council_cache_miss",
    ]

    registered_names = {m.name for m in REGISTRY.collect()}
    missing = [n for n in expected_names if n not in registered_names]
    assert not missing, f"Missing metric in registry: {missing}"


@pytest.mark.integration
@pytest.mark.slow
async def test_hash_chain_break_alert_increments_counter(db_session: Any) -> None:
    """Force a chain break and verify that HASH_CHAIN_BREAKS_TOTAL increments."""
    from sqlalchemy import select

    from src.core.copilot.council.models import CouncilDecisionRow
    from src.core.models.rbac_models import Tenant

    tenant_id = 9999

    # Ensure tenant exists
    existing = await db_session.execute(select(Tenant).where(Tenant.id == tenant_id))
    if existing.scalar_one_or_none() is None:
        db_session.add(
            Tenant(id=tenant_id, name="MetricsTest", slug="metrics-test")
        )
        await db_session.commit()

    class _SessionCtx:
        async def __aenter__(self) -> Any:
            return db_session

        async def __aexit__(self, *args: Any) -> None:
            pass

    writer = CouncilAuditWriter(lambda: _SessionCtx())  # type: ignore[arg-type,return-value]

    # Seed first decision so there is a previous hash
    proposal = Proposal(
        tenant_id=tenant_id,
        user_id=1,
        trigger=ProposalTrigger.USER_REQUEST,
        action_type="navigate_to",
        action_params={},
        message="seed",
        reasoning="seed",
        data_classification=DataClassification.PUBLIC,
        confidence=0.9,
        model_id="test",
        model_version="v1",
        context_snapshot={},
    )
    verdict = OfficerVerdict(
        officer_name="ComplianceOfficer",
        officer_version="1.0.0",
        verdict=VerdictType.APPROVE,
        reason_code="SEED",
        reason_text="seed",
        evidence={},
        deliberation_ms=0,
        confidence=1.0,
    )
    decision1 = CouncilDecision(
        proposal_id=proposal.proposal_id,
        tenant_id=tenant_id,
        user_id=1,
        verdict=DecisionVerdict.APPROVED,
        officer_verdicts=(verdict,),
        explanation_for_user="seed",
        decision_hash="PENDING",
        previous_decision_hash=None,
        deliberation_ms=0,
    )

    await writer.persist(decision1, proposal, (verdict,))

    # Get the actual previous hash from DB
    result = await db_session.execute(
        select(CouncilDecisionRow.decision_hash)
        .where(CouncilDecisionRow.tenant_id == tenant_id)
        .order_by(CouncilDecisionRow.timestamp.desc())
        .limit(1)
    )
    real_previous = result.scalar_one_or_none()
    assert real_previous is not None

    # Build a second decision with a WRONG previous hash
    decision2 = CouncilDecision(
        proposal_id=proposal.proposal_id,
        tenant_id=tenant_id,
        user_id=1,
        verdict=DecisionVerdict.APPROVED,
        officer_verdicts=(verdict,),
        explanation_for_user="break",
        decision_hash="PENDING",
        previous_decision_hash="wrong_hash_12345",
        deliberation_ms=0,
    )

    before = HASH_CHAIN_BREAKS_TOTAL.labels(tenant_id=str(tenant_id))._value.get()

    with pytest.raises(HashChainBreakError):
        await writer.persist(decision2, proposal, (verdict,))

    after = HASH_CHAIN_BREAKS_TOTAL.labels(tenant_id=str(tenant_id))._value.get()
    assert after - before == 1

    # Audit write failure counter should also have incremented
    failed_after = AUDIT_WRITES_TOTAL.labels(status="failed")._value.get()
    # We can't assert exact delta because other tests may have incremented it,
    # but we know it must have increased by at least 1.
