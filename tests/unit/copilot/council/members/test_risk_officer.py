import uuid
from unittest.mock import AsyncMock

import pytest

from src.core.copilot.council.members.risk_officer import RiskOfficer
from src.core.copilot.council.types import (
    DataClassification,
    DeliberationContext,
    Proposal,
    VerdictType,
)


def _make_proposal(action_type="test", action_params=None):
    if action_params is None:
        action_params = {}
    return Proposal(
        proposal_id="123",
        tenant_id=1,
        user_id=1,
        action_type=action_type,
        action_params=action_params,
        reasoning="testing",
        data_classification=DataClassification.PUBLIC,
        confidence=0.9,
        trigger="test_trigger",
        model_id="gpt-4",
        model_version="1.0",
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
def mock_shadow_ceo():
    m = AsyncMock()
    m.assess.return_value = "LOW"
    return m


@pytest.fixture
def mock_risk_register():
    m = AsyncMock()
    m.actor_track_record.return_value = ["prev_1", "prev_2"]
    return m


@pytest.fixture
def officer(mock_shadow_ceo, mock_risk_register):
    return RiskOfficer(mock_shadow_ceo, mock_risk_register)


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_veto_on_critical_shadow_ceo_score(officer, mock_shadow_ceo):
    mock_shadow_ceo.assess.return_value = "CRITICAL"
    verdict = await officer.deliberate(_make_proposal(), _make_context())
    assert verdict.verdict == VerdictType.VETO
    assert verdict.reason_code == "SHADOW_CEO_CRITICAL"


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_require_hitl_on_high_risk(officer, mock_shadow_ceo):
    mock_shadow_ceo.assess.return_value = "HIGH"
    verdict = await officer.deliberate(_make_proposal(), _make_context())
    assert verdict.verdict == VerdictType.REQUIRE_HITL
    assert verdict.reason_code == "HIGH_RISK"


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_require_hitl_on_medium_first_time_actor(
    officer, mock_shadow_ceo, mock_risk_register
):
    mock_shadow_ceo.assess.return_value = "MEDIUM"
    mock_risk_register.actor_track_record.return_value = []
    verdict = await officer.deliberate(_make_proposal(), _make_context())
    assert verdict.verdict == VerdictType.REQUIRE_HITL
    assert verdict.reason_code == "FIRST_TIME_ACTOR"


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_approve_on_medium_with_track_record(officer, mock_shadow_ceo, mock_risk_register):
    mock_shadow_ceo.assess.return_value = "MEDIUM"
    mock_risk_register.actor_track_record.return_value = ["event_1"]
    verdict = await officer.deliberate(_make_proposal(), _make_context())
    assert verdict.verdict == VerdictType.APPROVE


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_approve_on_low_risk(officer, mock_shadow_ceo):
    mock_shadow_ceo.assess.return_value = "LOW"
    verdict = await officer.deliberate(_make_proposal(), _make_context())
    assert verdict.verdict == VerdictType.APPROVE


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_evidence_includes_shadow_ceo_score(officer, mock_shadow_ceo):
    mock_shadow_ceo.assess.return_value = "HIGH"
    verdict = await officer.deliberate(_make_proposal(), _make_context())
    assert verdict.evidence.get("shadow_ceo_score") == "HIGH"


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_evidence_includes_actor_history(officer, mock_shadow_ceo, mock_risk_register):
    mock_shadow_ceo.assess.return_value = "LOW"
    mock_risk_register.actor_track_record.return_value = ["e1", "e2", "e3"]
    verdict = await officer.deliberate(_make_proposal(), _make_context())
    assert verdict.evidence.get("actor_history_count") == 3


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_exception_returns_veto_with_upstream_error(officer, mock_shadow_ceo):
    mock_shadow_ceo.assess.side_effect = Exception("Shadow CEO down")
    verdict = await officer.deliberate(_make_proposal(), _make_context())
    assert verdict.verdict == VerdictType.VETO
    assert verdict.reason_code == "UPSTREAM_ERROR"


@pytest.mark.unit
@pytest.mark.als
def test_can_cache_is_false(officer):
    assert officer.can_cache is False


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_evidence_includes_shadow_ceo_score_critical(officer, mock_shadow_ceo):
    mock_shadow_ceo.assess.return_value = "CRITICAL"
    verdict = await officer.deliberate(_make_proposal(), _make_context())
    assert verdict.evidence.get("shadow_ceo_score") == "CRITICAL"


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_evidence_includes_shadow_ceo_score_medium(
    officer, mock_shadow_ceo, mock_risk_register
):
    mock_shadow_ceo.assess.return_value = "MEDIUM"
    mock_risk_register.actor_track_record.return_value = []
    verdict = await officer.deliberate(_make_proposal(), _make_context())
    assert verdict.evidence.get("shadow_ceo_score") == "MEDIUM"


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_evidence_includes_actor_history_count_medium_approve(
    officer, mock_shadow_ceo, mock_risk_register
):
    mock_shadow_ceo.assess.return_value = "MEDIUM"
    mock_risk_register.actor_track_record.return_value = ["event"]
    verdict = await officer.deliberate(_make_proposal(), _make_context())
    assert verdict.evidence.get("actor_history_count") == 1


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_shadow_ceo_called_with_proposal(officer, mock_shadow_ceo):
    proposal = _make_proposal()
    await officer.deliberate(proposal, _make_context())
    mock_shadow_ceo.assess.assert_called_once_with(proposal)


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_risk_register_called_with_user_and_action(
    officer, mock_shadow_ceo, mock_risk_register
):
    mock_shadow_ceo.assess.return_value = "MEDIUM"
    proposal = _make_proposal(action_type="export")
    await officer.deliberate(proposal, _make_context())
    mock_risk_register.actor_track_record.assert_called_once_with(1, "export")


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_behavioral_delete_user_risk_officer_hitl(
    officer, mock_shadow_ceo, mock_risk_register
):
    # This simulates a user trying delete_user. It might be scored HIGH by shadow CEO.
    mock_shadow_ceo.assess.return_value = "HIGH"
    proposal = _make_proposal(action_type="delete_user")
    verdict = await officer.deliberate(proposal, _make_context())
    assert verdict.verdict == VerdictType.REQUIRE_HITL
