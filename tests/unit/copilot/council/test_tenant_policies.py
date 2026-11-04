"""Unit tests for dynamic per-tenant Agent Council policies."""

import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from src.core.copilot.council.coordinator import AgentCouncil
from src.core.copilot.council.types import (
    Proposal, 
    DeliberationContext, 
    VerdictType, 
    DecisionVerdict,
    ProposalTrigger,
    DataClassification,
    OfficerVerdict,
    CouncilDecision
)
from src.core.copilot.council.policies.models import CouncilPolicy, OfficerPolicy

@pytest.fixture
def mock_officers():
    officers = {
        "compliance": MagicMock(name="ComplianceOfficer"),
        "privacy": MagicMock(name="PrivacyOfficer"),
        "security": MagicMock(name="SecurityOfficer"),
        "risk": MagicMock(name="RiskOfficer"),
        "ethics": MagicMock(name="EthicsOfficer"),
        "resource": MagicMock(name="ResourceOfficer"),
        "sanity": MagicMock(name="SanityOfficer"),
        "audit": MagicMock(name="AuditOfficer"),
    }
    for name, m in officers.items():
        m.name = name.capitalize() + "Officer"
        m.version = "1.0.0"
        m.timeout_ms = 500
        m.health_check.return_value = True
        
        # Async mock for deliberate
        async def mock_delib(p, c, name=m.name):
            return OfficerVerdict(
                officer_name=name,
                officer_version="1.0.0",
                verdict=VerdictType.APPROVE,
                reason_code="OK",
                reason_text="Approved",
                evidence={},
                deliberation_ms=10,
                confidence=1.0
            )
        m.deliberate.side_effect = mock_delib
        
    # Special setup for AuditOfficer
    officers["audit"].finalize_and_persist = AsyncMock()
    return officers

@pytest.fixture
def council(mock_officers):
    return AgentCouncil(**mock_officers)

def create_proposal(tenant_id: int):
    return Proposal(
        tenant_id=tenant_id,
        user_id=1,
        trigger=ProposalTrigger.USER_REQUEST,
        action_type="TEST",
        action_params={},
        message="Test",
        reasoning="Test",
        data_classification=DataClassification.PUBLIC,
        confidence=1.0,
        model_id="test-model",
        model_version="1.0",
        context_snapshot={}
    )

def mock_decision_builder(proposal, final_verdict, officer_verdicts):
    return CouncilDecision(
        proposal_id=proposal.proposal_id,
        tenant_id=proposal.tenant_id,
        user_id=proposal.user_id,
        verdict=final_verdict,
        officer_verdicts=officer_verdicts,
        explanation_for_user="Explanation",
        decision_hash="hash",
        previous_decision_hash=None,
        deliberation_ms=100
    )

@pytest.mark.asyncio
async def test_policy_default_veto_blocks(council, mock_officers):
    # Security Officer gives a VETO
    mock_officers["security"].deliberate.side_effect = AsyncMock(return_value=OfficerVerdict(
        officer_name="SecurityOfficer",
        officer_version="1.0.0",
        verdict=VerdictType.VETO,
        reason_code="SECURITY_RISK",
        reason_text="Blocked",
        evidence={},
        deliberation_ms=10,
        confidence=1.0
    ))
    
    policy = CouncilPolicy(officers={
        "SecurityOfficer": OfficerPolicy(can_veto=True)
    })
    
    with patch("src.core.copilot.council.coordinator.load_policy", return_value=policy):
        proposal = create_proposal(tenant_id=1)
        mock_officers["audit"].finalize_and_persist.side_effect = lambda **kwargs: mock_decision_builder(
            kwargs["proposal"], kwargs["final_verdict"], kwargs["officer_verdicts"]
        )
        
        decision = await council.deliberate(proposal)
        assert decision.verdict == DecisionVerdict.BLOCKED

@pytest.mark.asyncio
async def test_policy_override_veto_downgrade(council, mock_officers):
    # Security Officer gives a VETO
    mock_officers["security"].deliberate.side_effect = AsyncMock(return_value=OfficerVerdict(
        officer_name="SecurityOfficer",
        officer_version="1.0.0",
        verdict=VerdictType.VETO,
        reason_code="SECURITY_RISK",
        reason_text="Blocked",
        evidence={},
        deliberation_ms=10,
        confidence=1.0
    ))
    
    # Policy with can_veto=False override for this tenant
    policy = CouncilPolicy(officers={
        "SecurityOfficer": OfficerPolicy(can_veto=False)
    })
    
    with patch("src.core.copilot.council.coordinator.load_policy", return_value=policy):
        proposal = create_proposal(tenant_id=2)
        mock_officers["audit"].finalize_and_persist.side_effect = lambda **kwargs: mock_decision_builder(
            kwargs["proposal"], kwargs["final_verdict"], kwargs["officer_verdicts"]
        )
        
        decision = await council.deliberate(proposal)
        
        # Should NOT be blocked, but DEFERRED because of the downgraded veto
        assert decision.verdict == DecisionVerdict.DEFERRED

@pytest.mark.asyncio
async def test_policy_timeout_override(council, mock_officers):
    # Mock deliberate to take longer than override but less than default
    async def slow_deliberate(*args, **kwargs):
        await asyncio.sleep(0.2) # 200ms
        return OfficerVerdict(
            officer_name="PrivacyOfficer",
            officer_version="1.0.0",
            verdict=VerdictType.APPROVE,
            reason_code="OK",
            reason_text="Approved",
            evidence={},
            deliberation_ms=200,
            confidence=1.0
        )
    
    mock_officers["privacy"].deliberate.side_effect = slow_deliberate
    mock_officers["privacy"].timeout_ms = 500 # Default
    
    # Policy override: 100ms timeout
    policy = CouncilPolicy(officers={
        "PrivacyOfficer": OfficerPolicy(timeout_ms=100)
    })
    
    with patch("src.core.copilot.council.coordinator.load_policy", return_value=policy):
        proposal = create_proposal(tenant_id=3)
        mock_officers["audit"].finalize_and_persist.side_effect = lambda **kwargs: mock_decision_builder(
            kwargs["proposal"], kwargs["final_verdict"], kwargs["officer_verdicts"]
        )
        
        decision = await council.deliberate(proposal)
        
        # PrivacyOfficer should have timed out: sinds 2026-10-27 uitstel naar een mens, geen synthetisch VETO
        assert decision.verdict == DecisionVerdict.HITL_REQUIRED
        # Verify it was indeed a timeout
        found_timeout = any(v.reason_code == "TIMEOUT" and v.officer_name == "PrivacyOfficer" for v in decision.officer_verdicts)
        assert found_timeout
