"""
Unit tests for SanityOfficer.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.core.copilot.council.members.sanity_officer import SanityOfficer
from src.core.copilot.council.types import DeliberationContext, Proposal, ProposalTrigger, VerdictType, DataClassification


@pytest.fixture
def sanity_officer():
    return SanityOfficer()


@pytest.fixture
def mock_context():
    return MagicMock(spec=DeliberationContext)


def make_proposal(message: str, reasoning: str = "This is a valid reasoning over 10 chars", confidence: float = 0.9):
    return Proposal(
        tenant_id=1,
        user_id=1,
        trigger=ProposalTrigger.USER_REQUEST,
        action_type="noop",
        action_params={},
        message=message,
        reasoning=reasoning,
        data_classification=DataClassification.PUBLIC,
        confidence=confidence,
        model_id="test-model",
        model_version="1.0",
        context_snapshot={},
    )


@pytest.mark.asyncio
async def test_sanity_officer_approves_valid_proposal(sanity_officer, mock_context):
    proposal = make_proposal("Hello, how can I help you?")
    verdict = await sanity_officer.deliberate(proposal, mock_context)
    
    assert verdict.verdict == VerdictType.APPROVE
    assert verdict.reason_code == "SANITY_OK"


@pytest.mark.asyncio
async def test_sanity_officer_vetos_low_confidence(sanity_officer, mock_context):
    proposal = make_proposal("Valid message", confidence=0.2)
    verdict = await sanity_officer.deliberate(proposal, mock_context)
    
    assert verdict.verdict == VerdictType.VETO
    assert verdict.reason_code == "INSUFFICIENT_CONFIDENCE"


@pytest.mark.asyncio
async def test_sanity_officer_vetos_ai_refusal(sanity_officer, mock_context):
    refusals = [
        "I'm sorry, I cannot do that.",
        "As an AI model, I am unable to assist.",
        "Ik kan niet helpen met dit verzoek.",
        "Helaas kan ik dit niet uitvoeren.",
    ]
    for msg in refusals:
        proposal = make_proposal(msg)
        verdict = await sanity_officer.deliberate(proposal, mock_context)
        assert verdict.verdict == VerdictType.VETO
        assert verdict.reason_code == "AI_REFUSAL_DETECTED"


@pytest.mark.asyncio
async def test_sanity_officer_vetos_insufficient_reasoning(sanity_officer, mock_context):
    proposal = make_proposal("Valid message", reasoning="Short")
    verdict = await sanity_officer.deliberate(proposal, mock_context)
    
    assert verdict.verdict == VerdictType.VETO
    assert verdict.reason_code == "INSUFFICIENT_EXPLANATION"


@pytest.mark.asyncio
@patch("src.core.learning.safety.hallucination_guard.HallucinationGuard.check")
async def test_sanity_officer_vetos_hallucination(mock_check, sanity_officer, mock_context):
    mock_check.return_value = (False, "ungrounded_file_ref:secret.py")

    proposal = make_proposal("Referencing secret.py")
    verdict = await sanity_officer.deliberate(proposal, mock_context)

    assert verdict.verdict == VerdictType.VETO
    assert verdict.reason_code == "HALLUCINATION_DETECTED"
    # ADR-036 D2-002/OP-38 (fix-sprint dag 6): alleen de CATEGORIE ("ungrounded_file_ref") mag
    # in reason_text/evidence staan, niet de gematchte modeltekst ("secret.py") -- die tekst
    # kan een persoonsgegeven zijn (bv. een bestandsnaam als "jan_jansen_salaris.pdf") en gaat
    # ongeredigeerd de onuitwisbare hashketen in via officer_verdicts.reason_text/evidence.
    assert "ungrounded_file_ref" in verdict.reason_text
    assert "secret.py" not in verdict.reason_text, (
        "De gematchte modeltekst staat verbatim in reason_text -- dat is precies het lek dat "
        "ADR-036 D2-002/OP-38 dicht. Alleen de categorie voor het triggeren mag hier staan."
    )
    assert verdict.evidence.get("hallucination_reason") == "ungrounded_file_ref"
