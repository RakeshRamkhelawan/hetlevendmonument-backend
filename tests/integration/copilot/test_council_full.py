"""
End-to-end integration tests for the Agent Council with all 7 real Officers.

These tests prove that the Coordinator correctly aggregates verdicts from
real Officer instances and persists decisions to the database with an intact
hash chain.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from src.core.copilot.council.models import CouncilDecisionRow, OfficerVerdictRow
from src.core.copilot.council.types import (
    DataClassification,
    DecisionVerdict,
    ProposalTrigger,
    VerdictType,
)
from tests.integration.copilot.conftest import make_proposal


@pytest.mark.integration
@pytest.mark.als
@pytest.mark.requires_postgres
@pytest.mark.asyncio
async def test_full_council_approve_path(real_council, db_session):
    """Safe proposal -> all Officers APPROVE -> final APPROVED."""
    proposal = make_proposal(
        tenant_id=1,
        user_id=1,
        action_type="navigate_to",
        action_params={
            "url": "/dashboard",
            "ai_disclosure": "Deze actie wordt voorgesteld door AI",
            "model_id": "deepseek-chat",
            "model_version": "v3",
        },
        reasoning="User vroeg om naar dashboard te navigeren.",
        data_classification=DataClassification.PUBLIC,
    )

    decision = await real_council.deliberate(proposal)

    print("VERDICT:", decision.verdict)
    print("DECISION_HASH:", decision.decision_hash)
    print("PREV_HASH:", decision.previous_decision_hash)
    for v in decision.officer_verdicts:
        print(f"  {v.officer_name}: {v.verdict} ({v.reason_code}) id={v.verdict_id}")

    assert decision.verdict == DecisionVerdict.APPROVED

    # Audit-trail check: 6 officer_verdicts in DB (AuditOfficer writes, does not vote)
    result = await db_session.execute(
        select(OfficerVerdictRow).where(OfficerVerdictRow.decision_id == decision.decision_id)
    )
    verdicts = result.scalars().all()
    print("DB VERDICTS COUNT:", len(verdicts))
    for v in verdicts:
        print(f"  DB {v.officer_name}: {v.verdict_id}")
    officer_names = {v.officer_name for v in verdicts}
    expected = {
        "ComplianceOfficer",
        "PrivacyOfficer",
        "SecurityOfficer",
        "RiskOfficer",
        "EthicsOfficer",
        "ResourceOfficer",
        "SanityOfficer",
    }
    assert officer_names == expected

    # Hash chain: decision_hash is populated
    assert decision.decision_hash is not None
    assert len(decision.decision_hash) == 64  # SHA-256 hex

    # DB row exists
    row_result = await db_session.execute(
        select(CouncilDecisionRow).where(CouncilDecisionRow.decision_id == decision.decision_id)
    )
    db_row = row_result.scalar_one()
    assert db_row.verdict == "approved"
    assert db_row.decision_hash == decision.decision_hash


@pytest.mark.integration
@pytest.mark.als
@pytest.mark.requires_postgres
@pytest.mark.asyncio
async def test_full_council_compliance_veto_blocks(real_council, db_session):
    """Forbidden practice -> ComplianceOfficer VETO -> BLOCKED."""
    # Patch classifier to emit FORBIDDEN_PRACTICE
    real_council._voting_officers[0]._classifier.classify.return_value = "FORBIDDEN_PRACTICE"

    proposal = make_proposal(
        tenant_id=1,
        user_id=1,
        action_type="social_scoring",
        action_params={
            "score_users": True,
            "ai_disclosure": "Deze actie wordt voorgesteld door AI",
            "model_id": "deepseek-chat",
            "model_version": "v3",
        },
        reasoning="Score all users for risk profiling.",
    )
    decision = await real_council.deliberate(proposal)

    assert decision.verdict == DecisionVerdict.BLOCKED

    # Verify ComplianceOfficer VETO is recorded
    result = await db_session.execute(
        select(OfficerVerdictRow).where(OfficerVerdictRow.decision_id == decision.decision_id)
    )
    verdicts = result.scalars().all()
    compliance_verdict = next((v for v in verdicts if v.officer_name == "ComplianceOfficer"), None)
    assert compliance_verdict is not None
    assert compliance_verdict.verdict == "veto"
    assert compliance_verdict.reason_code == "FORBIDDEN_PRACTICE"

    # Reset mock to avoid polluting other tests
    real_council._voting_officers[0]._classifier.classify.return_value = "LOW_RISK"


@pytest.mark.integration
@pytest.mark.als
@pytest.mark.requires_postgres
@pytest.mark.asyncio
async def test_full_council_modification_path(real_council, db_session):
    """EthicsOfficer detects bias term, others approve -> MODIFIED."""
    proposal = make_proposal(
        tenant_id=1,
        user_id=1,
        reasoning="Typisch voor mannen om dit te willen.",  # HIGH bias term (NL)
        action_params={
            "ai_disclosure": "Deze actie wordt voorgesteld door AI",
            "model_id": "deepseek-chat",
            "model_version": "v3",
        },
    )
    decision = await real_council.deliberate(proposal)

    assert decision.verdict == DecisionVerdict.MODIFIED
    assert decision.modifications is not None
    assert "EthicsOfficer" in decision.modifications

    # Verify EthicsOfficer recorded a modification verdict
    result = await db_session.execute(
        select(OfficerVerdictRow).where(OfficerVerdictRow.decision_id == decision.decision_id)
    )
    verdicts = result.scalars().all()
    ethics_verdict = next((v for v in verdicts if v.officer_name == "EthicsOfficer"), None)
    assert ethics_verdict is not None
    assert ethics_verdict.verdict == "modify"
    assert ethics_verdict.reason_code == "HIGH_BIAS_LANGUAGE_DETECTED"


@pytest.mark.integration
@pytest.mark.als
@pytest.mark.requires_postgres
@pytest.mark.asyncio
async def test_full_council_hitl_path(real_council, db_session):
    """SecurityOfficer high-risk -> REQUIRE_HITL -> HITL_REQUIRED."""
    proposal = make_proposal(
        tenant_id=1,
        user_id=1,
        action_type="delete_user_data",
        action_params={
            "user_ids": [1, 2, 3, 4, 5],
            "ai_disclosure": "Deze actie wordt voorgesteld door AI",
            "model_id": "deepseek-chat",
            "model_version": "v3",
        },
        data_classification=DataClassification.RESTRICTED,
    )
    decision = await real_council.deliberate(proposal)

    assert decision.verdict == DecisionVerdict.HITL_REQUIRED

    # Verify SecurityOfficer recorded REQUIRE_HITL
    result = await db_session.execute(
        select(OfficerVerdictRow).where(OfficerVerdictRow.decision_id == decision.decision_id)
    )
    verdicts = result.scalars().all()
    security_verdict = next((v for v in verdicts if v.officer_name == "SecurityOfficer"), None)
    assert security_verdict is not None
    assert security_verdict.verdict == "require_hitl"
    assert security_verdict.reason_code == "HIGH_RISK_TOOL"


@pytest.mark.integration
@pytest.mark.als
@pytest.mark.requires_postgres
@pytest.mark.asyncio
async def test_full_council_defer_path(real_council, db_session):
    """ResourceOfficer notification budget exhausted -> DEFERRED."""
    tenant_id = 1
    user_id = 99

    # Pre-seed the fake Redis counter at the daily limit (25) so the next
    # proactive_monitor proposal triggers DEFERRED immediately.
    from datetime import datetime, timezone

    date_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    redis_key = f"copilot:notif:{tenant_id}:{user_id}:{date_key}"
    resource_officer = real_council._voting_officers[5]
    resource_officer._budget._redis._counters[redis_key] = 25

    proposal = make_proposal(
        tenant_id=tenant_id,
        user_id=user_id,
        trigger=ProposalTrigger.PROACTIVE_MONITOR,
        action_type="notify_user",
        context_snapshot={"severity": "normal"},
        action_params={
            "ai_disclosure": "Deze actie wordt voorgesteld door AI",
            "model_id": "deepseek-chat",
            "model_version": "v3",
        },
    )
    decision = await real_council.deliberate(proposal)

    assert decision.verdict == DecisionVerdict.DEFERRED

    # Verify ResourceOfficer recorded REQUIRE_DEFERRAL
    result = await db_session.execute(
        select(OfficerVerdictRow).where(OfficerVerdictRow.decision_id == decision.decision_id)
    )
    verdicts = result.scalars().all()
    resource_verdict = next((v for v in verdicts if v.officer_name == "ResourceOfficer"), None)
    assert resource_verdict is not None
    assert resource_verdict.verdict == "defer"
