import uuid
from unittest.mock import MagicMock

import pytest

from src.core.copilot.council.members.privacy_officer import PrivacyOfficer
from src.core.copilot.council.types import (
    DataClassification,
    DeliberationContext,
    Proposal,
    VerdictType,
)


def _make_proposal(
    action_type="test", action_params=None, data_class=DataClassification.PUBLIC, tenant_id=1
):
    if action_params is None:
        action_params = {}
    return Proposal(
        proposal_id="123",
        tenant_id=tenant_id,
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


def _make_context(twin_profile=None):
    return DeliberationContext(
        tenant_settings={},
        user_preferences={},
        twin_profile=twin_profile,
        recent_decisions=(),
        deadline_ms=500,
        request_id=uuid.uuid4(),
    )


@pytest.fixture
def mock_gdpr():
    m = MagicMock()
    m.detect_pii.return_value = []
    return m


from unittest.mock import AsyncMock

@pytest.fixture
def mock_consent():
    m = AsyncMock()
    m.has_consent.return_value = True
    return m


@pytest.fixture
def mock_twin():
    return MagicMock()


@pytest.fixture
def officer(mock_gdpr, mock_consent, mock_twin):
    return PrivacyOfficer(mock_gdpr, mock_consent, mock_twin)


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_veto_on_cross_tenant_attempt(officer):
    # Action params has tenant_id=2, but proposal is tenant_id=1
    proposal = _make_proposal(action_params={"tenant_id": 2}, tenant_id=1)
    verdict = await officer.deliberate(proposal, _make_context())
    assert verdict.verdict == VerdictType.VETO
    assert verdict.reason_code == "CROSS_TENANT_ATTEMPT"


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_require_hitl_on_pii_export(officer, mock_gdpr):
    mock_gdpr.detect_pii.return_value = ["email"]
    proposal = _make_proposal(action_type="export_users")
    verdict = await officer.deliberate(proposal, _make_context())
    assert verdict.verdict == VerdictType.REQUIRE_HITL
    assert verdict.reason_code == "PII_BULK_ACTION"


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_veto_on_missing_twin_consent(officer, mock_consent):
    mock_consent.has_consent.return_value = False
    context = _make_context(twin_profile={"some": "profile"})
    verdict = await officer.deliberate(_make_proposal(), context)
    assert verdict.verdict == VerdictType.VETO
    assert verdict.reason_code == "MISSING_TWIN_CONSENT"


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_approve_when_no_pii(officer):
    verdict = await officer.deliberate(_make_proposal(), _make_context())
    assert verdict.verdict == VerdictType.APPROVE


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_approve_when_pii_but_read_only(officer, mock_gdpr):
    mock_gdpr.detect_pii.return_value = ["email"]
    # Action type does not start with export/share/send
    proposal = _make_proposal(action_type="read_users")
    verdict = await officer.deliberate(proposal, _make_context())
    assert verdict.verdict == VerdictType.APPROVE


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_veto_on_dsar_without_activation(officer):
    proposal = _make_proposal(action_type="dsar_request", action_params={"dsar_activated": False})
    verdict = await officer.deliberate(proposal, _make_context())
    assert verdict.verdict == VerdictType.VETO
    assert verdict.reason_code == "DSAR_NOT_ACTIVATED"


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_evidence_includes_pii_types_found(officer, mock_gdpr):
    mock_gdpr.detect_pii.return_value = ["phone", "email"]
    verdict = await officer.deliberate(_make_proposal(), _make_context())
    assert verdict.evidence["pii_types"] == ["phone", "email"]


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.security
@pytest.mark.gdpr
@pytest.mark.asyncio
async def test_proposal_for_tenant_a_with_tenant_b_reference_vetos(officer):
    proposal = _make_proposal(action_params={"tenant_id": 3}, tenant_id=2)
    verdict = await officer.deliberate(proposal, _make_context())
    assert verdict.verdict == VerdictType.VETO
    assert verdict.reason_code == "CROSS_TENANT_ATTEMPT"


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_allow_dsar_with_activation(officer):
    proposal = _make_proposal(action_type="dsar_request", action_params={"dsar_activated": True})
    verdict = await officer.deliberate(proposal, _make_context())
    assert verdict.verdict == VerdictType.APPROVE


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_pii_bulk_action_share(officer, mock_gdpr):
    mock_gdpr.detect_pii.return_value = ["email"]
    proposal = _make_proposal(action_type="share_report")
    verdict = await officer.deliberate(proposal, _make_context())
    assert verdict.verdict == VerdictType.REQUIRE_HITL


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_pii_bulk_action_send(officer, mock_gdpr):
    mock_gdpr.detect_pii.return_value = ["email"]
    proposal = _make_proposal(action_type="send_email")
    verdict = await officer.deliberate(proposal, _make_context())
    assert verdict.verdict == VerdictType.REQUIRE_HITL


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_twin_consent_allows_action(officer, mock_consent):
    mock_consent.has_consent.return_value = True
    context = _make_context(twin_profile={"some": "profile"})
    verdict = await officer.deliberate(_make_proposal(), context)
    assert verdict.verdict == VerdictType.APPROVE


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_exception_returns_veto(officer, mock_gdpr):
    mock_gdpr.detect_pii.side_effect = RuntimeError("DB down")
    verdict = await officer.deliberate(_make_proposal(), _make_context())
    assert verdict.verdict == VerdictType.VETO
    assert verdict.reason_code == "EXCEPTION"
    assert "DB down" in verdict.reason_text


@pytest.mark.unit
@pytest.mark.als
def test_can_cache_is_false(officer):
    assert officer.can_cache is False


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_no_tenant_id_in_params_allowed(officer):
    proposal = _make_proposal(action_params={"other_id": 123}, tenant_id=1)
    verdict = await officer.deliberate(proposal, _make_context())
    assert verdict.verdict == VerdictType.APPROVE
