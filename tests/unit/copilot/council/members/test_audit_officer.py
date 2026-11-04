import time
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.copilot.council.audit_writer import AuditWriteError, CouncilAuditWriter
from src.core.copilot.council.members.audit_officer import AuditOfficer
from src.core.copilot.council.metrics import AUDIT_WRITES_TOTAL
from src.core.copilot.council.models import CouncilDecisionRow, OfficerVerdictRow
from src.core.copilot.council.types import (
    DataClassification,
    DecisionVerdict,
    DeliberationContext,
    OfficerVerdict,
    Proposal,
    ProposalTrigger,
    VerdictType,
)


def _make_proposal():
    return Proposal(
        proposal_id=uuid.uuid4(),
        tenant_id=1,
        user_id=1,
        trigger=ProposalTrigger.USER_REQUEST,
        action_type="test",
        action_params={},
        reasoning="testing",
        data_classification=DataClassification.PUBLIC,
        confidence=0.9,
        model_id="gpt-4",
        model_version="1.0",
        context_snapshot={},
    )


def _make_officer_verdict(verdict=VerdictType.APPROVE):
    return OfficerVerdict(
        officer_name="TestOfficer",
        officer_version="1.0",
        verdict=verdict,
        reason_code="OK",
        reason_text="Because I said so",
        evidence={},
        deliberation_ms=10,
        confidence=0.9,
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
def mock_db_session_factory():
    session_mock = AsyncMock()
    # Support async with
    session_mock.__aenter__.return_value = session_mock

    # Force execute to return a normal MagicMock
    result_mock = MagicMock()
    session_mock.execute.return_value = result_mock

    factory = MagicMock(return_value=session_mock)
    factory.session = session_mock  # for easy access in tests
    factory.result_mock = result_mock
    return factory


@pytest.fixture
def audit_writer(mock_db_session_factory):
    return CouncilAuditWriter(mock_db_session_factory)


@pytest.fixture
def officer(audit_writer):
    return AuditOfficer(audit_writer)


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_persist_creates_council_decision_row(officer, mock_db_session_factory):
    session = mock_db_session_factory.session
    result_mock = mock_db_session_factory.result_mock
    result_mock.scalar_one_or_none.return_value = "prev_hash"

    await officer.finalize_and_persist(
        proposal=_make_proposal(),
        officer_verdicts=(_make_officer_verdict(),),
        final_verdict=DecisionVerdict.APPROVED,
        modifications=None,
        hitl_request_id=None,
        start_ms=time.perf_counter() - 0.1,
        context=_make_context(),
    )

    # Assert session.add was called with a CouncilDecisionRow
    added_objects = [call[0][0] for call in session.add.call_args_list]
    assert any(isinstance(obj, CouncilDecisionRow) for obj in added_objects)
    assert session.commit.called


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_persist_creates_all_officer_verdicts_rows(officer, mock_db_session_factory):
    session = mock_db_session_factory.session
    result_mock = mock_db_session_factory.result_mock
    result_mock.scalar_one_or_none.return_value = "prev_hash"

    verdicts = (_make_officer_verdict(), _make_officer_verdict())
    await officer.finalize_and_persist(
        proposal=_make_proposal(),
        officer_verdicts=verdicts,
        final_verdict=DecisionVerdict.APPROVED,
        modifications=None,
        hitl_request_id=None,
        start_ms=time.perf_counter() - 0.1,
        context=_make_context(),
    )

    added_objects = [call[0][0] for call in session.add.call_args_list]
    verdict_rows = [obj for obj in added_objects if isinstance(obj, OfficerVerdictRow)]
    assert len(verdict_rows) == 2


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_decision_hash_changes_with_input(officer, audit_writer):
    proposal1 = _make_proposal()
    c1 = audit_writer.compute_canonical_json(proposal1, (), DecisionVerdict.APPROVED, None, "test explanation")
    hash1 = audit_writer.compute_decision_hash(c1)

    # Change tenant_id to affect hash
    proposal2 = Proposal(
        proposal_id=proposal1.proposal_id,
        tenant_id=2,  # Changed
        user_id=proposal1.user_id,
        trigger=proposal1.trigger,
        action_type=proposal1.action_type,
        action_params=proposal1.action_params,
        reasoning=proposal1.reasoning,
        data_classification=proposal1.data_classification,
        confidence=proposal1.confidence,
        model_id=proposal1.model_id,
        model_version=proposal1.model_version,
        context_snapshot=proposal1.context_snapshot,
    )

    c2 = audit_writer.compute_canonical_json(proposal2, (), DecisionVerdict.APPROVED, None, "test explanation")
    hash2 = audit_writer.compute_decision_hash(c2)

    assert hash1 != hash2


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_previous_hash_is_genesis_for_first_decision(officer, mock_db_session_factory):
    session = mock_db_session_factory.session
    result_mock = mock_db_session_factory.result_mock
    # First decision ever
    result_mock.scalar_one_or_none.return_value = None

    await officer.finalize_and_persist(
        proposal=_make_proposal(),
        officer_verdicts=(),
        final_verdict=DecisionVerdict.APPROVED,
        modifications=None,
        hitl_request_id=None,
        start_ms=time.perf_counter(),
        context=_make_context(),
    )

    added_decision = [
        call[0][0]
        for call in session.add.call_args_list
        if isinstance(call[0][0], CouncilDecisionRow)
    ][0]
    assert added_decision.previous_decision_hash is None


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_previous_hash_is_last_decision_for_subsequent(officer, mock_db_session_factory):
    session = mock_db_session_factory.session
    result_mock = mock_db_session_factory.result_mock
    result_mock.scalar_one_or_none.return_value = "deadbeef"

    await officer.finalize_and_persist(
        proposal=_make_proposal(),
        officer_verdicts=(),
        final_verdict=DecisionVerdict.APPROVED,
        modifications=None,
        hitl_request_id=None,
        start_ms=time.perf_counter(),
        context=_make_context(),
    )

    added_decision = [
        call[0][0]
        for call in session.add.call_args_list
        if isinstance(call[0][0], CouncilDecisionRow)
    ][0]
    assert added_decision.previous_decision_hash == "deadbeef"


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_explanation_does_not_leak_internal_reasons_on_blocked(officer):
    explanation = officer._generate_explanation(
        (_make_officer_verdict(VerdictType.VETO),), DecisionVerdict.BLOCKED
    )
    assert "De Co-Pilot kan deze actie niet uitvoeren." in explanation
    assert "Because I said so" not in explanation  # Reason text should not be leaked on BLOCKED


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_explanation_is_not_broken_when_hitl_required_has_no_officer_reason(officer):
    """ADR-036 D4-003 (OP-166): de coordinator kan een APPROVED-verdict optillen naar
    HITL_REQUIRED via `ALWAYS_HITL_ACTIONS` (GDPR art. 22) zonder dat een officer
    REQUIRE_HITL stemde. Voor deze fix (gevonden door Gate 2, dag 5) eindigde de string
    op "vanwege: ." (lege join) -- een kapotte, niet-informatieve uitleg in precies het
    pad dat GDPR art. 22 uitlegbaarheid vereist."""
    explanation = officer._generate_explanation(
        (_make_officer_verdict(VerdictType.APPROVE),), DecisionVerdict.HITL_REQUIRED
    )
    assert not explanation.rstrip().endswith("vanwege: .")
    assert "platformbeleidsregel" in explanation


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_explanation_is_not_broken_when_hitl_required_was_upgraded_from_modified(officer):
    """ADR-036 OP-168 (HITL-ticket-volledigheid sprint dag 3): sinds deze fix kan de
    coordinator ook een MODIFIED-verdict optillen naar HITL_REQUIRED via
    `ALWAYS_HITL_ACTIONS`. Geen enkele officer stemde daarbij REQUIRE_HITL (ze stemden
    APPROVE_WITH_MODIFICATION) -- dezelfde lege-join-val als de APPROVED-upgrade hierboven,
    nu voor een tweede oorsprong van dat verdict."""
    explanation = officer._generate_explanation(
        (_make_officer_verdict(VerdictType.APPROVE_WITH_MODIFICATION),),
        DecisionVerdict.HITL_REQUIRED,
    )
    assert not explanation.rstrip().endswith("vanwege: .")
    assert "platformbeleidsregel" in explanation


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_audit_write_failure_raises_audit_write_error(officer, mock_db_session_factory):
    session = mock_db_session_factory.session
    session.commit.side_effect = Exception("DB offline")

    with pytest.raises(AuditWriteError):
        await officer.finalize_and_persist(
            proposal=_make_proposal(),
            officer_verdicts=(),
            final_verdict=DecisionVerdict.APPROVED,
            modifications=None,
            hitl_request_id=None,
            start_ms=time.perf_counter(),
            context=_make_context(),
        )


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_failed_persist_increments_prometheus_failure_counter(
    officer, mock_db_session_factory
):
    session = mock_db_session_factory.session
    session.commit.side_effect = Exception("DB offline")

    # Sample before
    before = AUDIT_WRITES_TOTAL.labels(status="failed")._value.get()

    with pytest.raises(AuditWriteError):
        await officer.finalize_and_persist(
            proposal=_make_proposal(),
            officer_verdicts=(),
            final_verdict=DecisionVerdict.APPROVED,
            modifications=None,
            hitl_request_id=None,
            start_ms=time.perf_counter(),
            context=_make_context(),
        )

    # Sample after
    after = AUDIT_WRITES_TOTAL.labels(status="failed")._value.get()
    assert after == before + 1


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_deliberate_is_noop(officer):
    verdict = await officer.deliberate(_make_proposal(), _make_context())
    assert verdict.verdict == VerdictType.APPROVE
    assert verdict.reason_code == "AUDIT_ACK"
    assert verdict.used_cache is False


@pytest.mark.unit
@pytest.mark.als
def test_can_cache_is_false(officer):
    assert officer.can_cache is False
