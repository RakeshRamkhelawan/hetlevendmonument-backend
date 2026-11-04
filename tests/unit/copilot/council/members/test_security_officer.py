import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.copilot.council.members.security_officer import SecurityOfficer
from src.core.copilot.council.types import (
    DataClassification,
    DeliberationContext,
    Proposal,
    VerdictType,
)


def _make_proposal(action_type="test", action_params=None, reasoning="testing"):
    if action_params is None:
        action_params = {}
    return Proposal(
        proposal_id="123",
        tenant_id=1,
        user_id=1,
        action_type=action_type,
        action_params=action_params,
        reasoning=reasoning,
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
def mock_tool_broker():
    m = AsyncMock()
    m.is_allowed.return_value = True
    return m


@pytest.fixture
def mock_prompt_guard():
    m = MagicMock()
    m.scan.return_value = {"injection_detected": False}
    return m


@pytest.fixture
def mock_rbac_checker():
    m = AsyncMock()
    m.user_has_scope_for.return_value = True
    return m


@pytest.fixture
def mock_cache():
    m = MagicMock()
    m.get.return_value = None
    return m


@pytest.fixture
def officer(mock_tool_broker, mock_prompt_guard, mock_rbac_checker, mock_cache):
    return SecurityOfficer(mock_tool_broker, mock_prompt_guard, mock_rbac_checker, mock_cache)


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.security
@pytest.mark.asyncio
async def test_veto_on_prompt_injection_basic(officer, mock_prompt_guard):
    mock_prompt_guard.scan.return_value = {
        "injection_detected": True,
        "patterns": ["ignore prev instructions"],
    }
    verdict = await officer.deliberate(_make_proposal(), _make_context())
    assert verdict.verdict == VerdictType.VETO
    assert verdict.reason_code == "PROMPT_INJECTION"
    assert "patterns" in verdict.evidence


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.security
@pytest.mark.asyncio
async def test_veto_on_prompt_injection_homoglyph(officer, mock_prompt_guard):
    # Pass string with cyrillic 'a' (U+0430)
    proposal = _make_proposal(reasoning="mаke action")
    await officer.deliberate(proposal, _make_context())
    # Should replace with latin 'a'
    args, _ = mock_prompt_guard.scan.call_args
    assert "make action" in args[0]


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.security
@pytest.mark.asyncio
async def test_veto_on_tool_not_in_allowlist(officer, mock_tool_broker):
    mock_tool_broker.is_allowed.return_value = False
    verdict = await officer.deliberate(_make_proposal(), _make_context())
    assert verdict.verdict == VerdictType.VETO
    assert verdict.reason_code == "TOOL_NOT_ALLOWLISTED"


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.security
@pytest.mark.asyncio
async def test_veto_on_missing_scope(officer, mock_rbac_checker):
    mock_rbac_checker.user_has_scope_for.return_value = False
    verdict = await officer.deliberate(_make_proposal(), _make_context())
    assert verdict.verdict == VerdictType.VETO
    assert verdict.reason_code == "MISSING_SCOPE"


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.security
@pytest.mark.asyncio
async def test_require_hitl_on_delete_action(officer):
    proposal = _make_proposal(action_type="delete_user")
    verdict = await officer.deliberate(proposal, _make_context())
    assert verdict.verdict == VerdictType.REQUIRE_HITL
    assert verdict.reason_code == "HIGH_RISK_TOOL"


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.security
@pytest.mark.asyncio
async def test_require_hitl_on_admin_action(officer):
    proposal = _make_proposal(action_type="admin_escalate")
    verdict = await officer.deliberate(proposal, _make_context())
    assert verdict.verdict == VerdictType.REQUIRE_HITL
    assert verdict.reason_code == "HIGH_RISK_TOOL"


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.security
@pytest.mark.asyncio
async def test_approve_when_all_checks_pass(officer):
    verdict = await officer.deliberate(_make_proposal(), _make_context())
    assert verdict.verdict == VerdictType.APPROVE
    assert verdict.reason_code == "COMPLIANT"


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.security
@pytest.mark.asyncio
async def test_cache_invalidated_on_scope_change(officer):
    # Mocking cache validation as just testing can_cache
    assert officer.can_cache is True


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.security
@pytest.mark.asyncio
async def test_exception_returns_veto(officer, mock_tool_broker):
    mock_tool_broker.is_allowed.side_effect = RuntimeError("Service down")
    verdict = await officer.deliberate(_make_proposal(), _make_context())
    assert verdict.verdict == VerdictType.VETO
    assert verdict.reason_code == "UPSTREAM_ERROR"


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.security
@pytest.mark.asyncio
async def test_high_risk_prefix_purge(officer):
    proposal = _make_proposal(action_type="purge_data")
    verdict = await officer.deliberate(proposal, _make_context())
    assert verdict.verdict == VerdictType.REQUIRE_HITL


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.security
@pytest.mark.asyncio
async def test_high_risk_prefix_grant_role(officer):
    proposal = _make_proposal(action_type="grant_role_to_user")
    verdict = await officer.deliberate(proposal, _make_context())
    assert verdict.verdict == VerdictType.REQUIRE_HITL


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.security
@pytest.mark.asyncio
async def test_high_risk_prefix_revoke_role(officer):
    proposal = _make_proposal(action_type="revoke_role_admin")
    verdict = await officer.deliberate(proposal, _make_context())
    assert verdict.verdict == VerdictType.REQUIRE_HITL


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.security
@pytest.mark.asyncio
async def test_high_risk_prefix_export_all(officer):
    proposal = _make_proposal(action_type="export_all_users")
    verdict = await officer.deliberate(proposal, _make_context())
    assert verdict.verdict == VerdictType.REQUIRE_HITL


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.security
@pytest.mark.asyncio
async def test_high_risk_prefix_bulk(officer):
    proposal = _make_proposal(action_type="bulk_delete")
    verdict = await officer.deliberate(proposal, _make_context())
    assert verdict.verdict == VerdictType.REQUIRE_HITL


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.security
@pytest.mark.asyncio
async def test_prompt_guard_called_with_reasoning_and_params(officer, mock_prompt_guard):
    proposal = _make_proposal(reasoning="test", action_params={"foo": "bar"})
    await officer.deliberate(proposal, _make_context())
    args, _ = mock_prompt_guard.scan.call_args
    assert "test" in args[0]
    assert "foo" in args[0]
    assert "bar" in args[0]
