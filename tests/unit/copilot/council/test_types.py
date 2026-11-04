"""
Unit tests for Agent Council datatypes.
Testing happy paths, unhappy paths (validations), and behavioral immutability.
"""

from datetime import datetime, timezone
from uuid import uuid4
import pytest

from src.core.copilot.council.types import (
    Proposal,
    ProposalTrigger,
    DataClassification,
    OfficerVerdict,
    VerdictType,
    CouncilDecision,
    DecisionVerdict,
)

@pytest.mark.unit
def test_proposal_constructs_with_all_required_fields():
    p = Proposal(
        tenant_id=10,
        user_id=20,
        trigger=ProposalTrigger.USER_REQUEST,
        action_type="navigate_to",
        action_params={"path": "/home"},
        reasoning="Test reasoning",
        data_classification=DataClassification.INTERNAL,
        confidence=0.8,
        model_id="test-model",
        model_version="1.0",
        context_snapshot={},
    )
    assert p.tenant_id == 10
    assert p.confidence == 0.8
    assert p.timestamp.tzinfo is not None

@pytest.mark.unit
def test_council_decision_default_timestamp_is_utc():
    cd = CouncilDecision(
        proposal_id=uuid4(),
        tenant_id=1,
        user_id=1,
        verdict=DecisionVerdict.APPROVED,
        officer_verdicts=tuple(),
        explanation_for_user="Explain",
        decision_hash="hash",
        previous_decision_hash=None,
        deliberation_ms=100,
    )
    assert cd.timestamp.tzinfo == timezone.utc

@pytest.mark.unit
def test_officer_verdict_default_id_unique():
    v1 = OfficerVerdict("Audit", "1.0", VerdictType.APPROVE, "OK", "OK", {}, 10, 1.0)
    v2 = OfficerVerdict("Audit", "1.0", VerdictType.APPROVE, "OK", "OK", {}, 10, 1.0)
    assert v1.verdict_id != v2.verdict_id

@pytest.mark.unit
def test_proposal_rejects_negative_confidence():
    with pytest.raises(ValueError, match="confidence must be in"):
        Proposal(
            tenant_id=10,
            user_id=20,
            trigger=ProposalTrigger.USER_REQUEST,
            action_type="navigate_to",
            action_params={},
            reasoning="Test",
            data_classification=DataClassification.INTERNAL,
            confidence=-0.1,
            model_id="test",
            model_version="1.0",
            context_snapshot={},
        )

@pytest.mark.unit
def test_proposal_rejects_confidence_over_one():
    with pytest.raises(ValueError, match="confidence must be in"):
        Proposal(
            tenant_id=10,
            user_id=20,
            trigger=ProposalTrigger.USER_REQUEST,
            action_type="navigate_to",
            action_params={},
            reasoning="Test",
            data_classification=DataClassification.INTERNAL,
            confidence=1.1,
            model_id="test",
            model_version="1.0",
            context_snapshot={},
        )

@pytest.mark.unit
def test_proposal_rejects_naive_datetime():
    with pytest.raises(ValueError, match="timezone-aware"):
        Proposal(
            tenant_id=10,
            user_id=20,
            trigger=ProposalTrigger.USER_REQUEST,
            action_type="navigate_to",
            action_params={},
            reasoning="Test",
            data_classification=DataClassification.INTERNAL,
            confidence=0.5,
            model_id="test",
            model_version="1.0",
            context_snapshot={},
            timestamp=datetime.now(), # naive
        )

@pytest.mark.unit
def test_proposal_rejects_zero_tenant_id():
    with pytest.raises(ValueError, match="tenant_id must be > 0"):
        Proposal(
            tenant_id=0,
            user_id=20,
            trigger=ProposalTrigger.USER_REQUEST,
            action_type="navigate_to",
            action_params={},
            reasoning="Test",
            data_classification=DataClassification.INTERNAL,
            confidence=0.5,
            model_id="test",
            model_version="1.0",
            context_snapshot={},
        )

@pytest.mark.unit
def test_proposal_rejects_zero_user_id():
    with pytest.raises(ValueError, match="user_id must be > 0"):
        Proposal(
            tenant_id=10,
            user_id=0,
            trigger=ProposalTrigger.USER_REQUEST,
            action_type="navigate_to",
            action_params={},
            reasoning="Test",
            data_classification=DataClassification.INTERNAL,
            confidence=0.5,
            model_id="test",
            model_version="1.0",
            context_snapshot={},
        )

@pytest.mark.unit
def test_officer_verdict_rejects_invalid_confidence():
    with pytest.raises(ValueError, match="confidence must be in"):
        OfficerVerdict("Audit", "1.0", VerdictType.APPROVE, "OK", "OK", {}, 10, 1.5)

@pytest.mark.unit
def test_council_decision_rejects_naive_datetime():
    with pytest.raises(ValueError, match="timezone-aware"):
        CouncilDecision(
            proposal_id=uuid4(),
            tenant_id=1,
            user_id=1,
            verdict=DecisionVerdict.APPROVED,
            officer_verdicts=tuple(),
            explanation_for_user="Explain",
            decision_hash="hash",
            previous_decision_hash=None,
            deliberation_ms=100,
            timestamp=datetime.now()
        )

@pytest.mark.unit
def test_council_decision_is_immutable():
    cd = CouncilDecision(
        proposal_id=uuid4(),
        tenant_id=1,
        user_id=1,
        verdict=DecisionVerdict.APPROVED,
        officer_verdicts=tuple(),
        explanation_for_user="Explain",
        decision_hash="hash",
        previous_decision_hash=None,
        deliberation_ms=100,
    )
    with pytest.raises(AttributeError):
        # Using typing ignore or relying on pytest.raises to catch the dataclass frozen error
        cd.deliberation_ms = 200 # type: ignore
