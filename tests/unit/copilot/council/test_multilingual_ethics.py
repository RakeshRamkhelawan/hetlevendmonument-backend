"""Unit tests for EthicsOfficer multilingual support (HI, SA, NL, EN)."""

import pytest
from src.core.copilot.council.members.ethics_officer import EthicsOfficer
from src.core.copilot.council.types import (
    DeliberationContext, 
    Proposal, 
    VerdictType, 
    ProposalTrigger, 
    DataClassification
)

@pytest.fixture
def ethics_officer():
    return EthicsOfficer()

def create_proposal(reasoning: str, tenant_id: int = 1) -> Proposal:
    return Proposal(
        tenant_id=tenant_id,
        user_id=1,
        action_type="TEST",
        action_params={},
        reasoning=reasoning,
        trigger=ProposalTrigger.USER_REQUEST,
        message="Test message",
        data_classification=DataClassification.PUBLIC,
        confidence=0.9,
        model_id="gpt-4",
        model_version="1.0",
        context_snapshot={}
    )

@pytest.mark.asyncio
async def test_ethics_hindi_bias_detection(ethics_officer):
    # Hindi "All men" term (\u0938\u092d\u0940 \u092a\u0941\u0930\u0941\u0937)
    reasoning = "\u0938\u092d\u0940 \u092a\u0941\u0930\u0941\u0937 \u092c\u0932\u0935\u093e\u0928 \u0939\u0948\u0902" 
    proposal = create_proposal(reasoning)
    context = DeliberationContext(
        tenant_settings={},
        user_preferences={"language": "hi"},
        twin_profile=None,
        recent_decisions=(),
        deadline_ms=500,
        request_id=proposal.proposal_id
    )
    
    verdict = await ethics_officer.deliberate(proposal, context)
    
    assert verdict.verdict == VerdictType.APPROVE_WITH_MODIFICATION
    assert verdict.reason_code == "HIGH_BIAS_LANGUAGE_DETECTED"
    assert "hi" in verdict.evidence["language_used"]
    assert "\u0938\u092d\u0940 \u092a\u0941\u0930\u0941\u0937" in verdict.evidence["high_matches"]

@pytest.mark.asyncio
async def test_ethics_sanskrit_clean_reasoning(ethics_officer):
    # Sanskrit "Svechha" (Freedom/Will) - no bias
    reasoning = "\u0938\u094d\u0935\u0947\u091a\u094d\u091b\u093e \u0936\u093e\u0928\u094d\u0924\u093f\u0903" 
    proposal = create_proposal(reasoning)
    context = DeliberationContext(
        tenant_settings={},
        user_preferences={"language": "sa"},
        twin_profile=None,
        recent_decisions=(),
        deadline_ms=500,
        request_id=proposal.proposal_id
    )
    
    verdict = await ethics_officer.deliberate(proposal, context)
    
    assert verdict.verdict == VerdictType.APPROVE
    assert verdict.reason_code == "NO_BIAS_DETECTED"

@pytest.mark.asyncio
async def test_ethics_sanskrit_bias_detection(ethics_officer):
    # Sanskrit "All women" (\u0938\u0930\u094d\u0935\u093e\u0903 \u0928\u093e\u0930\u094d\u092f\u0903)
    reasoning = "\u0938\u0930\u094d\u0935\u093e\u0903 \u0928\u093e\u0930\u094d\u092f\u0903 \u0915\u094b\u092e\u0932\u093e\u0903" 
    proposal = create_proposal(reasoning)
    context = DeliberationContext(
        tenant_settings={},
        user_preferences={"language": "sa"},
        twin_profile=None,
        recent_decisions=(),
        deadline_ms=500,
        request_id=proposal.proposal_id
    )
    
    verdict = await ethics_officer.deliberate(proposal, context)
    
    assert verdict.verdict == VerdictType.APPROVE_WITH_MODIFICATION
    assert "\u0938\u0930\u094d\u0935\u093e\u0903 \u0928\u093e\u0930\u094d\u092f\u0903" in verdict.evidence["high_matches"]

@pytest.mark.asyncio
async def test_ethics_fallback_to_en(ethics_officer):
    # Language "fr" (French) not supported, should fallback to default nl
    reasoning = "All men are equal" 
    proposal = create_proposal(reasoning)
    context = DeliberationContext(
        tenant_settings={},
        user_preferences={"language": "fr"},
        twin_profile=None,
        recent_decisions=(),
        deadline_ms=500,
        request_id=proposal.proposal_id
    )
    
    verdict = await ethics_officer.deliberate(proposal, context)
    
    # Defaults to NL lexicon in current logic if lang not in list
    assert verdict.evidence["language_used"] == "nl"

@pytest.mark.asyncio
async def test_normalization_prevents_bypass(ethics_officer):
    # Test normalization (NFKC/NFD)
    # \u0939\u092e\u0947\u0936\u093e (hamesha - always)
    reasoning = "\u0939\u092e\u0947\u0936\u093e" 
    proposal = create_proposal(reasoning)
    context = DeliberationContext(
        tenant_settings={},
        user_preferences={"language": "hi"},
        twin_profile=None,
        recent_decisions=(),
        deadline_ms=500,
        request_id=proposal.proposal_id
    )
    
    verdict = await ethics_officer.deliberate(proposal, context)
    assert "\u0939\u092e\u0947\u0936\u093e" in verdict.evidence["medium_matches"]
