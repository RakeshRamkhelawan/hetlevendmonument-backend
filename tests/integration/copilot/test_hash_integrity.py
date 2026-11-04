"""
Integration tests for Council Hash Chain Integrity (ChainVerifier).
Sprint 7, Day 2.
"""

import hashlib
import json
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any, AsyncGenerator

import pytest
from sqlalchemy import select, update, delete

from src.core.copilot.audit.chain_verifier import ChainVerifier
from tests.integration.copilot.conftest import seed_tenants
from src.core.copilot.council.audit_writer import CouncilAuditWriter
from src.core.copilot.council.models import CouncilDecisionRow, OfficerVerdictRow
from src.core.copilot.council.types import (
    CouncilDecision,
    DataClassification,
    DecisionVerdict,
    OfficerVerdict,
    Proposal,
    ProposalTrigger,
    VerdictType,
)


def _make_dummy_proposal(tenant_id: int) -> Proposal:
    return Proposal(
        tenant_id=tenant_id,
        user_id=1,
        trigger=ProposalTrigger.USER_REQUEST,
        action_type="test_action",
        action_params={"key": "value"},
        message="Test message",
        reasoning="Test reasoning",
        data_classification=DataClassification.PUBLIC,
        confidence=0.9,
        model_id="test-model",
        model_version="1.0",
        context_snapshot={},
    )


def _make_dummy_officer_verdicts() -> tuple[OfficerVerdict, ...]:
    return (
        OfficerVerdict(
            officer_name="TestOfficer",
            officer_version="1.0.0",
            verdict=VerdictType.APPROVE,
            reason_code="TEST_OK",
            reason_text="Looks good",
            evidence={},
            deliberation_ms=10,
            confidence=0.95,
        ),
    )


@pytest.mark.asyncio
async def test_chain_verifier_intact_chain(db_session: Any) -> None:
    """Verifies a fully intact hash chain."""
    await seed_tenants(db_session, [701])
    
    @asynccontextmanager
    async def mock_session_factory() -> AsyncGenerator[Any, None]:
        yield db_session
        
    writer = CouncilAuditWriter(mock_session_factory)  # type: ignore  # type: ignore
    
    # We must mock or use the writer's actual persist method.
    # Since write_decision takes Proposal, verdicts, etc.
    for _ in range(3):
        proposal = _make_dummy_proposal(701)
        verdicts = _make_dummy_officer_verdicts()
        decision = CouncilDecision(
            proposal_id=proposal.proposal_id,
            tenant_id=proposal.tenant_id,
            user_id=proposal.user_id,
            verdict=DecisionVerdict.APPROVED,
            officer_verdicts=verdicts,
            explanation_for_user="Test",
            decision_hash="", # Writer will overwrite
            previous_decision_hash=None,
            deliberation_ms=100,
        )
        await writer.persist(decision, proposal, verdicts)
        
    verifier = ChainVerifier(db_session)
    result = await verifier.verify_tenant_chain(701)
    
    assert result.is_valid is True
    assert result.total_entries == 3
    assert result.verified_entries == 3
    assert len(result.broken_links) == 0


@pytest.mark.asyncio
async def test_chain_verifier_tampered_hash(db_session: Any) -> None:
    """Verifies that tampering with a decision breaks the chain."""
    await seed_tenants(db_session, [702])
    
    @asynccontextmanager
    async def mock_session_factory() -> AsyncGenerator[Any, None]:
        yield db_session
        
    writer = CouncilAuditWriter(mock_session_factory)  # type: ignore
    
    proposal = _make_dummy_proposal(702)
    verdicts = _make_dummy_officer_verdicts()
    decision = CouncilDecision(
        proposal_id=proposal.proposal_id,
        tenant_id=proposal.tenant_id,
        user_id=proposal.user_id,
        verdict=DecisionVerdict.APPROVED,
        officer_verdicts=verdicts,
        explanation_for_user="Test",
        decision_hash="",
        previous_decision_hash=None,
        deliberation_ms=100,
    )
    await writer.persist(decision, proposal, verdicts)
    
    # Tamper with the row
    await db_session.execute(
        update(CouncilDecisionRow)
        .where(CouncilDecisionRow.tenant_id == 702)
        .values(action_type="hacked_action")
    )
    await db_session.commit()
    
    verifier = ChainVerifier(db_session)
    result = await verifier.verify_tenant_chain(702)
    
    assert result.is_valid is False
    assert len(result.broken_links) == 1
    assert "tampering detected" in result.broken_links[0].reason


@pytest.mark.asyncio
async def test_chain_verifier_missing_link(db_session: Any) -> None:
    """Verifies that a deleted row breaks the chain's previous_hash linkage."""
    await seed_tenants(db_session, [703])
    
    @asynccontextmanager
    async def mock_session_factory() -> AsyncGenerator[Any, None]:
        yield db_session
        
    writer = CouncilAuditWriter(mock_session_factory)  # type: ignore
    
    # Write 3 decisions
    decisions = []
    for _ in range(3):
        proposal = _make_dummy_proposal(703)
        verdicts = _make_dummy_officer_verdicts()
        decision = CouncilDecision(
            proposal_id=proposal.proposal_id,
            tenant_id=proposal.tenant_id,
            user_id=proposal.user_id,
            verdict=DecisionVerdict.APPROVED,
            officer_verdicts=verdicts,
            explanation_for_user="Test",
            decision_hash="", 
            previous_decision_hash=None,
            deliberation_ms=100,
        )
        await writer.persist(decision, proposal, verdicts)
        decisions.append(decision)
        
    # Delete the middle decision
    # Wait, the writer modifies the decision object passed in, but the real DB row has the uuid.
    # We can just delete the 2nd row ordered by timestamp.
    result = await db_session.execute(
        select(CouncilDecisionRow)
        .where(CouncilDecisionRow.tenant_id == 703)
        .order_by(CouncilDecisionRow.timestamp.asc())
        .offset(1)
        .limit(1)
    )
    row_to_delete = result.scalar_one()
    await db_session.execute(
        delete(CouncilDecisionRow).where(CouncilDecisionRow.decision_id == row_to_delete.decision_id)
    )
    await db_session.commit()
    
    verifier = ChainVerifier(db_session)
    verify_result = await verifier.verify_tenant_chain(703)
    
    assert verify_result.is_valid is False
    assert len(verify_result.broken_links) == 1
    assert "Previous hash link mismatch" in verify_result.broken_links[0].reason
