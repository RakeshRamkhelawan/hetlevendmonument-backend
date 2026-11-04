import uuid
from unittest.mock import MagicMock

import pytest

from src.core.copilot.council.members.compliance_officer import ComplianceOfficer
from src.core.copilot.council.types import (
    DataClassification,
    DecisionVerdict,
    DeliberationContext,
    Proposal,
    VerdictType,
)


def _make_proposal(action_type="test", action_params=None, data_class=DataClassification.PUBLIC):
    if action_params is None:
        action_params = {"model_id": "1", "model_version": "v1", "ai_disclosure": "yes"}
    return Proposal(
        proposal_id="123",
        tenant_id=1,
        user_id=1,
        action_type=action_type,
        action_params=action_params,
        data_classification=data_class,
        confidence=0.9,
        trigger="test_trigger",
        reasoning="test_reasoning",
        model_id="gpt-4o",
        model_version="2024-05-13",
        context_snapshot={},
    )


def _make_context():
    return DeliberationContext(
        tenant_settings={},
        user_preferences={},
        twin_profile=None,
        recent_decisions=(),
        deadline_ms=500,
        request_id=uuid.uuid4(),
    )


@pytest.fixture
def mock_guardian():
    return MagicMock()


@pytest.fixture
def mock_classifier():
    m = MagicMock()
    m.classify.return_value = "MINIMAL"
    return m


@pytest.fixture
def mock_cache():
    m = MagicMock()
    m.get.return_value = None
    return m


@pytest.fixture
def officer(mock_guardian, mock_classifier, mock_cache):
    return ComplianceOfficer(mock_guardian, mock_classifier, mock_cache)


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_approve_when_low_risk_action(officer, mock_classifier):
    mock_classifier.classify.return_value = "MINIMAL"
    verdict = await officer.deliberate(_make_proposal(), _make_context())
    assert verdict.verdict == VerdictType.APPROVE
    assert verdict.reason_code == "COMPLIANT"


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_veto_when_forbidden_practice(officer, mock_classifier):
    mock_classifier.classify.return_value = "FORBIDDEN_PRACTICE"
    verdict = await officer.deliberate(
        _make_proposal(action_type="social_scoring"), _make_context()
    )
    assert verdict.verdict == VerdictType.VETO
    assert verdict.reason_code == "FORBIDDEN_PRACTICE"


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_modify_when_missing_ai_disclosure(officer):
    proposal = _make_proposal(action_params={"model_id": "1", "model_version": "v1"})
    verdict = await officer.deliberate(proposal, _make_context())
    assert verdict.verdict == VerdictType.APPROVE_WITH_MODIFICATION
    assert verdict.reason_code == "MISSING_AI_DISCLOSURE"


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_modify_adds_disclosure_text(officer):
    proposal = _make_proposal(action_params={"model_id": "1", "model_version": "v1"})
    verdict = await officer.deliberate(proposal, _make_context())
    assert "modifications" in verdict.evidence
    assert (
        verdict.evidence["modifications"]["action_params"]["ai_disclosure"]
        == "Deze actie wordt voorgesteld door AI"
    )


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_veto_when_missing_model_id(officer):
    proposal = _make_proposal(action_params={"ai_disclosure": "yes"})
    # proposal is frozen, but we can bypass or recreate it. We will just bypass via object.__setattr__
    object.__setattr__(proposal, "model_id", "")
    verdict = await officer.deliberate(proposal, _make_context())
    assert verdict.verdict == VerdictType.VETO
    assert verdict.reason_code == "MISSING_METADATA"


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_cache_hit_returns_cached_verdict(officer, mock_cache):
    mock_cache.get.return_value = {
        "verdict": VerdictType.APPROVE.value,
        "reason_code": "CACHED",
        "reason_text": "text",
        "evidence": {},
    }
    verdict = await officer.deliberate(_make_proposal(), _make_context())
    assert verdict.verdict == VerdictType.APPROVE
    assert verdict.reason_code == "CACHED"


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_cache_miss_invokes_classifier(officer, mock_cache, mock_classifier):
    mock_cache.get.return_value = None
    await officer.deliberate(_make_proposal(), _make_context())
    mock_classifier.classify.assert_called_once()
    mock_cache.set.assert_called_once()


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_evidence_contains_classification_metadata(officer):
    verdict = await officer.deliberate(_make_proposal(), _make_context())
    assert "classification_metadata" in verdict.evidence
    assert verdict.evidence["classification_metadata"] is True


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_veto_when_missing_model_version(officer):
    proposal = _make_proposal(action_params={"ai_disclosure": "yes"})
    object.__setattr__(proposal, "model_version", "")
    verdict = await officer.deliberate(proposal, _make_context())
    assert verdict.verdict == VerdictType.VETO
    assert verdict.reason_code == "MISSING_METADATA"


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_veto_on_exception(officer, mock_classifier):
    mock_classifier.classify.side_effect = ValueError("Boom")
    verdict = await officer.deliberate(_make_proposal(), _make_context())
    assert verdict.verdict == VerdictType.VETO
    assert verdict.reason_code == "EXCEPTION"
    assert "Boom" in verdict.reason_text


@pytest.mark.unit
@pytest.mark.als
def test_can_cache_is_true(officer):
    assert officer.can_cache is True


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_classifier_called_with_correct_args(officer, mock_classifier):
    prop = _make_proposal(action_type="my_action")
    await officer.deliberate(prop, _make_context())
    mock_classifier.classify.assert_called_once_with("my_action", prop.action_params)


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_cache_set_with_expiration(officer, mock_cache):
    mock_cache.get.return_value = None
    prop = _make_proposal()
    await officer.deliberate(prop, _make_context())
    mock_cache.set.assert_called_once()
    args, kwargs = mock_cache.set.call_args
    assert kwargs.get("ex") == 60


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_deliberate_no_cache_injected(mock_guardian, mock_classifier):
    # test without cache
    off = ComplianceOfficer(mock_guardian, mock_classifier, None)
    prop = _make_proposal()
    verdict = await off.deliberate(prop, _make_context())
    assert verdict.verdict == VerdictType.APPROVE


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_deliberate_cache_hit_returns_evidence(officer, mock_cache):
    mock_cache.get.return_value = {
        "verdict": VerdictType.APPROVE.value,
        "reason_code": "C",
        "reason_text": "T",
        "evidence": {"cached_evidence": True},
    }
    verdict = await officer.deliberate(_make_proposal(), _make_context())
    assert verdict.evidence == {"cached_evidence": True}
