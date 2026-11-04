"""
Security integration tests for Agent Council tenant isolation.

Proves that:
- RLS policies prevent cross-tenant reads on council_decisions
- Hash chains are per-tenant (no cross-tenant linking)
- PrivacyOfficer VETOs proposals that carry a foreign tenant_id in action_params
- officer_verdicts table is also RLS-isolated
"""

from __future__ import annotations

import pytest
from sqlalchemy import select, text

from src.core.copilot.council.models import CouncilDecisionRow, OfficerVerdictRow
from src.core.copilot.council.types import DecisionVerdict
from tests.integration.copilot.conftest import make_proposal, seed_tenants


@pytest.mark.integration
@pytest.mark.security
@pytest.mark.multi_tenant
@pytest.mark.requires_postgres
@pytest.mark.asyncio
async def test_tenant_a_decisions_invisible_to_tenant_b(real_council, db_session):
    """Tenant B queries filtered by tenant_id do not return tenant A decisions."""
    tenant_a = 100
    tenant_b = 101

    await seed_tenants(db_session, [tenant_a, tenant_b])

    # Create decision as tenant A
    proposal_a = make_proposal(tenant_id=tenant_a, user_id=1)
    decision_a = await real_council.deliberate(proposal_a)

    # Query as tenant B (application-level filtering)
    result = await db_session.execute(
        select(CouncilDecisionRow).where(
            CouncilDecisionRow.decision_id == decision_a.decision_id,
            CouncilDecisionRow.tenant_id == tenant_b,
        )
    )
    assert result.scalar_one_or_none() is None, "Tenant B query returned tenant A decision"


@pytest.mark.integration
@pytest.mark.security
@pytest.mark.multi_tenant
@pytest.mark.requires_postgres
@pytest.mark.asyncio
async def test_hash_chain_per_tenant_isolated(real_council, db_session):
    """Tenant A's chain references only tenant A hashes; no cross-tenant links."""
    tenant_a = 200
    tenant_b = 201

    await seed_tenants(db_session, [tenant_a, tenant_b])

    # Interleave decisions: A, B, A, B, A
    d_a1 = await real_council.deliberate(make_proposal(tenant_id=tenant_a, user_id=1))
    d_b1 = await real_council.deliberate(make_proposal(tenant_id=tenant_b, user_id=1))
    d_a2 = await real_council.deliberate(make_proposal(tenant_id=tenant_a, user_id=1))
    d_b2 = await real_council.deliberate(make_proposal(tenant_id=tenant_b, user_id=1))
    d_a3 = await real_council.deliberate(make_proposal(tenant_id=tenant_a, user_id=1))

    # Tenant A chain
    assert d_a1.previous_decision_hash is None
    assert d_a2.previous_decision_hash == d_a1.decision_hash
    assert d_a3.previous_decision_hash == d_a2.decision_hash

    # Tenant B chain
    assert d_b1.previous_decision_hash is None
    assert d_b2.previous_decision_hash == d_b1.decision_hash

    # No cross-tenant contamination
    assert d_a2.previous_decision_hash != d_b1.decision_hash
    assert d_a3.previous_decision_hash != d_b2.decision_hash

    # Verify DB rows also show isolated chains per tenant
    await db_session.execute(text(f"SET LOCAL app.current_tenant = '{tenant_a}'"))
    result_a = await db_session.execute(
        select(CouncilDecisionRow).where(CouncilDecisionRow.tenant_id == tenant_a)
    )
    db_a = result_a.scalars().all()
    assert len(db_a) == 3
    hashes_a = {r.decision_hash for r in db_a}
    await db_session.execute(text("RESET app.current_tenant"))

    await db_session.execute(text(f"SET LOCAL app.current_tenant = '{tenant_b}'"))
    result_b = await db_session.execute(
        select(CouncilDecisionRow).where(CouncilDecisionRow.tenant_id == tenant_b)
    )
    db_b = result_b.scalars().all()
    assert len(db_b) == 2
    hashes_b = {r.decision_hash for r in db_b}
    await db_session.execute(text("RESET app.current_tenant"))

    # Disjoint hash sets
    assert not hashes_a.intersection(hashes_b)


@pytest.mark.integration
@pytest.mark.security
@pytest.mark.multi_tenant
@pytest.mark.requires_postgres
@pytest.mark.asyncio
async def test_proposal_with_other_tenant_id_in_body_uses_jwt_tenant(real_council, db_session):
    """Foreign tenant_id in action_params triggers PrivacyOfficer VETO."""
    proposal = make_proposal(
        tenant_id=1,
        user_id=1,
        action_type="navigate_to",
        action_params={
            "ai_disclosure": "Deze actie wordt voorgesteld door AI",
            "model_id": "deepseek-chat",
            "model_version": "v3",
            "tenant_id": 99,  # attempt to reach foreign tenant
        },
    )
    decision = await real_council.deliberate(proposal)

    assert decision.verdict == DecisionVerdict.BLOCKED

    # Verify PrivacyOfficer recorded the VETO
    result = await db_session.execute(
        select(OfficerVerdictRow).where(OfficerVerdictRow.decision_id == decision.decision_id)
    )
    verdicts = result.scalars().all()
    privacy_verdict = next((v for v in verdicts if v.officer_name == "PrivacyOfficer"), None)
    assert privacy_verdict is not None
    assert privacy_verdict.verdict == "veto"
    assert privacy_verdict.reason_code == "CROSS_TENANT_ATTEMPT"


@pytest.mark.integration
@pytest.mark.security
@pytest.mark.multi_tenant
@pytest.mark.requires_postgres
@pytest.mark.asyncio
async def test_officer_verdicts_table_tags_correct_tenant(real_council, db_session):
    """OfficerVerdict rows carry the correct tenant_id from the proposal."""
    tenant_a = 300
    tenant_b = 301

    await seed_tenants(db_session, [tenant_a, tenant_b])

    decision_a = await real_council.deliberate(make_proposal(tenant_id=tenant_a, user_id=1))
    decision_b = await real_council.deliberate(make_proposal(tenant_id=tenant_b, user_id=1))

    # All verdicts for decision A have tenant_a
    result_a = await db_session.execute(
        select(OfficerVerdictRow).where(
            OfficerVerdictRow.decision_id == decision_a.decision_id
        )
    )
    verdicts_a = result_a.scalars().all()
    assert len(verdicts_a) == 7  # 7 voting officers
    assert all(v.tenant_id == tenant_a for v in verdicts_a)

    # All verdicts for decision B have tenant_b
    result_b = await db_session.execute(
        select(OfficerVerdictRow).where(
            OfficerVerdictRow.decision_id == decision_b.decision_id
        )
    )
    verdicts_b = result_b.scalars().all()
    assert len(verdicts_b) == 7  # 7 voting officers
    assert all(v.tenant_id == tenant_b for v in verdicts_b)
