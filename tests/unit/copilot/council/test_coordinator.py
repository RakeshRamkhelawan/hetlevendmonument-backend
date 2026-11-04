"""
Tests for AgentCouncil coordinator aggregation logic.

Test taxonomy per CLAUDE.md kwaliteitsloop:
    - Happy paths      (test_aggregate_all_approve, test_aggregate_with_modification)
    - Unhappy paths    (test_aggregate_with_veto, test_aggregate_with_timeout)
    - Edge cases       (test_aggregate_empty_verdicts, test_aggregate_multiple_vetos)
    - Security tests   (test_no_tenant_id_leakage_in_logs)
    - Behavioral test  (test_user_sees_blocked_when_compliance_vetos)

Markers:
    @pytest.mark.unit              -- fast, no external dependencies
    @pytest.mark.als               -- Agent Lifecycle System tests
    @pytest.mark.multi_tenant      -- multi-tenancy verification
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

import asyncio
from src.core.copilot.council import coordinator as coordinator_module
from src.core.copilot.council.coordinator import AgentCouncil, ConfigurationError
from src.core.copilot.council.types import (
    DataClassification,
    DecisionVerdict,
    OfficerVerdict,
    Proposal,
    ProposalTrigger,
    VerdictType,
)


# ----------------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------------


def _make_verdict(officer_name: str, verdict: VerdictType, **kwargs) -> OfficerVerdict:
    """Helper: build a synthetic OfficerVerdict."""
    return OfficerVerdict(
        officer_name=officer_name,
        officer_version="1.0.0-test",
        verdict=verdict,
        reason_code=kwargs.get("reason_code", "TEST_OK"),
        reason_text=kwargs.get("reason_text", "Test verdict"),
        evidence=kwargs.get("evidence", {}),
        deliberation_ms=kwargs.get("deliberation_ms", 10),
        confidence=kwargs.get("confidence", 1.0),
    )


def _make_proposal(
    tenant_id: int = 42, user_id: int = 1337, action_type: str = "navigate_to"
) -> Proposal:
    """Helper: build a synthetic Proposal."""
    return Proposal(
        tenant_id=tenant_id,
        user_id=user_id,
        trigger=ProposalTrigger.USER_REQUEST,
        action_type=action_type,
        action_params={"route": "/dashboard"},
        reasoning="User asked to navigate to dashboard",
        data_classification=DataClassification.INTERNAL,
        confidence=0.95,
        model_id="test-model",
        model_version="0.0.1",
        context_snapshot={},
        timestamp=datetime.now(timezone.utc),
    )


@pytest.fixture
def mock_council() -> AgentCouncil:
    """Build an AgentCouncil with 8 mock Officers."""
    officers = {
        name: MagicMock(
            name=name,
            deliberate=AsyncMock(),
            can_cache=MagicMock(return_value=False),
            timeout_ms=500,
        )
        for name in [
            "compliance", "privacy", "security",
            "risk", "ethics", "resource", "sanity", "audit",
        ]
    }
    for o in officers.values():
        o.version = "1.0.0"
        o.health_check = MagicMock(return_value=True)
    return AgentCouncil(**officers)


# ----------------------------------------------------------------------------
# Happy paths
# ----------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
def test_aggregate_all_approve_yields_approved(mock_council: AgentCouncil) -> None:
    """When all 6 voting Officers approve, final verdict is APPROVED."""
    verdicts = tuple(
        _make_verdict(name, VerdictType.APPROVE)
        for name in ["c", "p", "s", "r", "e", "res"]
    )
    final, mods = mock_council._aggregate(verdicts)
    assert final == DecisionVerdict.APPROVED
    assert mods is None


@pytest.mark.unit
@pytest.mark.als
def test_aggregate_with_modification_yields_modified(mock_council: AgentCouncil) -> None:
    """When EthicsOfficer requires modification, final verdict is MODIFIED."""
    verdicts = (
        _make_verdict("compliance", VerdictType.APPROVE),
        _make_verdict("privacy", VerdictType.APPROVE),
        _make_verdict("security", VerdictType.APPROVE),
        _make_verdict("risk", VerdictType.APPROVE),
        _make_verdict(
            "ethics",
            VerdictType.APPROVE_WITH_MODIFICATION,
            evidence={"modifications": {"reasoning": "Reformulated"}},
        ),
        _make_verdict("resource", VerdictType.APPROVE),
    )
    final, mods = mock_council._aggregate(verdicts)
    assert final == DecisionVerdict.MODIFIED
    assert mods is not None
    assert "ethics" in mods


# ----------------------------------------------------------------------------
# Unhappy paths
# ----------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
def test_aggregate_with_veto_yields_blocked(mock_council: AgentCouncil) -> None:
    """ANY Officer VETO results in BLOCKED, regardless of others."""
    verdicts = (
        _make_verdict("compliance", VerdictType.APPROVE),
        _make_verdict("privacy", VerdictType.VETO, reason_code="CROSS_TENANT"),
        _make_verdict("security", VerdictType.APPROVE),
        _make_verdict("risk", VerdictType.APPROVE),
        _make_verdict("ethics", VerdictType.APPROVE),
        _make_verdict("resource", VerdictType.APPROVE),
    )
    final, mods = mock_council._aggregate(verdicts)
    assert final == DecisionVerdict.BLOCKED
    assert mods is None


@pytest.mark.unit
@pytest.mark.als
def test_veto_beats_hitl(mock_council: AgentCouncil) -> None:
    """When both VETO and HITL are present, VETO wins (most restrictive)."""
    verdicts = (
        _make_verdict("compliance", VerdictType.VETO),
        _make_verdict("privacy", VerdictType.REQUIRE_HITL),
        _make_verdict("security", VerdictType.APPROVE),
        _make_verdict("risk", VerdictType.APPROVE),
        _make_verdict("ethics", VerdictType.APPROVE),
        _make_verdict("resource", VerdictType.APPROVE),
    )
    final, _ = mock_council._aggregate(verdicts)
    assert final == DecisionVerdict.BLOCKED


@pytest.mark.unit
@pytest.mark.als
def test_hitl_beats_defer(mock_council: AgentCouncil) -> None:
    """HITL wins over DEFERRAL when no VETO."""
    verdicts = (
        _make_verdict("compliance", VerdictType.APPROVE),
        _make_verdict("privacy", VerdictType.APPROVE),
        _make_verdict("security", VerdictType.APPROVE),
        _make_verdict("risk", VerdictType.REQUIRE_HITL),
        _make_verdict("ethics", VerdictType.APPROVE),
        _make_verdict("resource", VerdictType.REQUIRE_DEFERRAL),
    )
    final, _ = mock_council._aggregate(verdicts)
    assert final == DecisionVerdict.HITL_REQUIRED


# ----------------------------------------------------------------------------
# Edge cases
# ----------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
def test_aggregate_multiple_vetos_all_recorded(mock_council: AgentCouncil) -> None:
    """When multiple Officers veto, all reasons appear in officer_verdicts."""
    verdicts = (
        _make_verdict("compliance", VerdictType.VETO, reason_code="FORBIDDEN_PRACTICE"),
        _make_verdict("privacy", VerdictType.VETO, reason_code="CROSS_TENANT"),
        _make_verdict("security", VerdictType.APPROVE),
        _make_verdict("risk", VerdictType.APPROVE),
        _make_verdict("ethics", VerdictType.APPROVE),
        _make_verdict("resource", VerdictType.APPROVE),
    )
    final, _ = mock_council._aggregate(verdicts)
    assert final == DecisionVerdict.BLOCKED
    veto_codes = [v.reason_code for v in verdicts if v.verdict == VerdictType.VETO]
    assert "FORBIDDEN_PRACTICE" in veto_codes
    assert "CROSS_TENANT" in veto_codes


# ----------------------------------------------------------------------------
# Security tests (CLAUDE.md regel 6, 10, 11)
# ----------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.security
@pytest.mark.multi_tenant
def test_proposal_requires_tenant_id() -> None:
    """Proposal must carry tenant_id; cannot be constructed without it."""
    with pytest.raises(TypeError):
        Proposal(  # type: ignore[call-arg]
            user_id=1,
            trigger=ProposalTrigger.USER_REQUEST,
            action_type="x",
            action_params={},
            reasoning="x",
            data_classification=DataClassification.INTERNAL,
            confidence=0.5,
            model_id="m",
            model_version="1",
            context_snapshot={},
        )


@pytest.mark.unit
@pytest.mark.security
def test_proposal_rejects_naive_datetime() -> None:
    """Proposal timestamp must be timezone-aware (CLAUDE.md regel 3)."""
    with pytest.raises(ValueError, match="timezone-aware"):
        Proposal(
            tenant_id=1,
            user_id=1,
            trigger=ProposalTrigger.USER_REQUEST,
            action_type="x",
            action_params={},
            reasoning="x",
            data_classification=DataClassification.INTERNAL,
            confidence=0.5,
            model_id="m",
            model_version="1",
            context_snapshot={},
            timestamp=datetime(2026, 5, 22, 14, 0, 0),  # naive!
        )


@pytest.mark.unit
@pytest.mark.security
def test_proposal_rejects_out_of_range_confidence() -> None:
    """Confidence must be in [0, 1]."""
    with pytest.raises(ValueError, match="confidence"):
        Proposal(
            tenant_id=1,
            user_id=1,
            trigger=ProposalTrigger.USER_REQUEST,
            action_type="x",
            action_params={},
            reasoning="x",
            data_classification=DataClassification.INTERNAL,
            confidence=1.5,  # out of range
            model_id="m",
            model_version="1",
            context_snapshot={},
            timestamp=datetime.now(timezone.utc),
        )


# ----------------------------------------------------------------------------
# Behavioral test (CLAUDE.md kwaliteitsloop stap 4)
# ----------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
def test_user_sees_blocked_when_privacy_officer_vetos(mock_council: AgentCouncil) -> None:
    """
    Behavioral: when PrivacyOfficer detects a cross-tenant attempt,
    the user receives a BLOCKED decision (no execution proceeds).
    """
    verdicts = (
        _make_verdict("compliance", VerdictType.APPROVE),
        _make_verdict(
            "privacy",
            VerdictType.VETO,
            reason_code="CROSS_TENANT_ATTEMPT",
            reason_text="Deze actie probeert data van een andere tenant te raken.",
        ),
        _make_verdict("security", VerdictType.APPROVE),
        _make_verdict("risk", VerdictType.APPROVE),
        _make_verdict("ethics", VerdictType.APPROVE),
        _make_verdict("resource", VerdictType.APPROVE),
    )
    final, mods = mock_council._aggregate(verdicts)
    assert final == DecisionVerdict.BLOCKED
    assert mods is None
    # The user-facing service should map BLOCKED to a generic refusal message
    # (do NOT leak the specific reason -- that's an info disclosure risk).
    # This is verified by CopilotService tests in test_service.py.

@pytest.mark.unit
@pytest.mark.als
def test_init_rejects_officer_without_version() -> None:
    officers = {
        name: MagicMock(
            name=name,
            version="",
            deliberate=AsyncMock(),
            can_cache=MagicMock(return_value=False),
            timeout_ms=500,
        )
        for name in ["compliance", "privacy", "security", "risk", "ethics", "resource", "sanity", "audit"]
    }
    with pytest.raises(ConfigurationError, match="missing a version string"):
        AgentCouncil(**officers)

@pytest.mark.unit
@pytest.mark.als
def test_synthetic_veto_carries_reason_code(mock_council: AgentCouncil) -> None:
    officer = mock_council._voting_officers[0]
    veto = mock_council._synthetic_verdict(officer, "TEST_REASON")
    assert veto.verdict == VerdictType.VETO
    assert veto.reason_code == "TEST_REASON"
    assert "TEST_REASON" in veto.reason_text

@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_deliberate_one_officer_times_out_asks_a_human(mock_council: AgentCouncil) -> None:
    # Brief 2026-10-27: een TIJDOVERSCHRIJDING is uitstel naar een mens (HITL), geen veto en nooit een goedkeuring.
    proposal = _make_proposal()
    context = await mock_council._build_context(proposal)
    
    # Make compliance officer timeout
    async def slow_deliberate(*args, **kwargs):
        await asyncio.sleep(0.5)
        return _make_verdict("compliance", VerdictType.APPROVE)
        
    mock_council._voting_officers[0].deliberate.side_effect = slow_deliberate
    mock_council._voting_officers[0].timeout_ms = 10  # 10ms timeout
    
    # Others approve instantly
    for o in mock_council._voting_officers[1:]:
        o.deliberate.return_value = _make_verdict(o.name, VerdictType.APPROVE)
        
    verdicts = await mock_council._gather_verdicts(proposal, context)
    final, _ = mock_council._aggregate(verdicts)
    assert final == DecisionVerdict.HITL_REQUIRED
    
    timeout_veto = next(v for v in verdicts if v.officer_name == mock_council._voting_officers[0].name)
    assert timeout_veto.verdict == VerdictType.REQUIRE_HITL
    assert timeout_veto.reason_code == "TIMEOUT"

@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_deliberate_one_officer_crashes_blocks(mock_council: AgentCouncil) -> None:
    proposal = _make_proposal()
    context = await mock_council._build_context(proposal)
    
    mock_council._voting_officers[0].deliberate.side_effect = ValueError("Some crash")
    
    for o in mock_council._voting_officers[1:]:
        o.deliberate.return_value = _make_verdict(o.name, VerdictType.APPROVE)
        
    verdicts = await mock_council._gather_verdicts(proposal, context)
    final, _ = mock_council._aggregate(verdicts)
    assert final == DecisionVerdict.BLOCKED
    
    crash_veto = next(v for v in verdicts if v.officer_name == mock_council._voting_officers[0].name)
    assert crash_veto.verdict == VerdictType.VETO
    assert crash_veto.reason_code == "INTERNAL_ERROR"

@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_deliberate_parallel_execution_completes_within_max_timeout(mock_council: AgentCouncil) -> None:
    proposal = _make_proposal()
    context = await mock_council._build_context(proposal)
    
    async def deliberate_sleep(*args, **kwargs):
        await asyncio.sleep(0.1)
        return _make_verdict("mock", VerdictType.APPROVE)
        
    for o in mock_council._voting_officers:
        o.deliberate.side_effect = deliberate_sleep
        o.timeout_ms = 500
        
    import time
    t0 = time.perf_counter()
    await mock_council._gather_verdicts(proposal, context)
    t1 = time.perf_counter()
    
    # It should take ~0.1s, not 6 * 0.1s
    assert t1 - t0 < 0.3

@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_user_sees_blocked_message_on_council_internal_failure(mock_council: AgentCouncil) -> None:
    # Deliberate entirely fails, e.g. _build_context crashes
    mock_council._build_context = AsyncMock(side_effect=RuntimeError("Secret DB issue"))
    
    proposal = _make_proposal()
    decision = await mock_council.deliberate(proposal)
    
    assert decision.verdict == DecisionVerdict.BLOCKED
    # The message should be user-facing and NOT leak "RuntimeError" or "Secret DB issue"
    assert "Een interne fout" in decision.explanation_for_user
    assert "Secret DB issue" not in decision.explanation_for_user

@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_deliberate_officer_fails_health_check(mock_council: AgentCouncil) -> None:
    proposal = _make_proposal()
    context = await mock_council._build_context(proposal)
    
    mock_council._voting_officers[0].health_check.return_value = False
    
    for o in mock_council._voting_officers[1:]:
        o.deliberate.return_value = _make_verdict(o.name, VerdictType.APPROVE)
        
    verdicts = await mock_council._gather_verdicts(proposal, context)
    final, _ = mock_council._aggregate(verdicts)
    assert final == DecisionVerdict.BLOCKED
    
    cb_veto = next(v for v in verdicts if v.officer_name == mock_council._voting_officers[0].name)
    assert cb_veto.verdict == VerdictType.VETO
    assert cb_veto.reason_code == "CIRCUIT_BREAKER_OPEN"

@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_deliberate_happy_path(mock_council: AgentCouncil) -> None:
    proposal = _make_proposal()
    
    # Mock finalize to avoid NotImplementedError
    from src.core.copilot.council.types import CouncilDecision
    mock_council._finalize = AsyncMock(return_value=CouncilDecision(
        proposal_id=proposal.proposal_id,
        tenant_id=proposal.tenant_id,
        user_id=proposal.user_id,
        verdict=DecisionVerdict.APPROVED,
        officer_verdicts=(),
        explanation_for_user="OK",
        decision_hash="HASH",
        previous_decision_hash=None,
        deliberation_ms=10,
    ))
    
    for o in mock_council._voting_officers:
        o.deliberate.return_value = _make_verdict(o.name, VerdictType.APPROVE)
        
    decision = await mock_council.deliberate(proposal)
    assert decision.verdict == DecisionVerdict.APPROVED
    mock_council._finalize.assert_called_once()


# ----------------------------------------------------------------------------
# ADR-036 D4-003 (GDPR art. 22 / OP-166): always-HITL action-type override
# ----------------------------------------------------------------------------


def _mock_finalize_capturing_final_verdict(mock_council: AgentCouncil, proposal: Proposal) -> AsyncMock:
    """Mockt `_finalize` en geeft een `CouncilDecision` terug MET het verdict dat er
    daadwerkelijk aan werd doorgegeven -- niet een hardcoded waarde. `test_deliberate_
    happy_path` mockt `_finalize` met een vaste `CouncilDecision(verdict=APPROVED, ...)`,
    wat niets bewijst over wat `deliberate()` intern aan `_finalize` doorgeeft. Voor de
    D4-003-tests moet de assertie op de daadwerkelijke aanroep-argumenten staan.
    """
    from src.core.copilot.council.types import CouncilDecision

    async def _finalize_side_effect(**kwargs: object) -> CouncilDecision:
        return CouncilDecision(
            proposal_id=proposal.proposal_id,
            tenant_id=proposal.tenant_id,
            user_id=proposal.user_id,
            verdict=kwargs["final_verdict"],  # type: ignore[typeddict-item]
            officer_verdicts=(),
            explanation_for_user="OK",
            decision_hash="HASH",
            previous_decision_hash=None,
            deliberation_ms=10,
        )

    mock_council._finalize = AsyncMock(side_effect=_finalize_side_effect)
    return mock_council._finalize


@pytest.mark.unit
@pytest.mark.als
def test_always_hitl_actions_contains_mandatory_high_risk_actions() -> None:
    """ADR-036 OP-164 (beleidsbesluit Rakesh 2026-08-25): ALWAYS_HITL_ACTIONS is
    gevuld met de 7 getriageerde onomkeerbare hoog-risico actietypes conform
    AVG art. 22 en EU AI Act art. 14. Geen enkel AI-model mag deze acties autonoom
    uitvoeren."""
    expected_actions = {
        "terminate_employee",
        "hire_candidate",
        "adjust_compensation",
        "disciplinary_action",
        "sign_external_contract",
        "execute_high_value_payout",
        "delete_tenant_data",
    }
    assert coordinator_module.ALWAYS_HITL_ACTIONS == frozenset(expected_actions), (
        f"ALWAYS_HITL_ACTIONS komt niet overeen met het beleidsbesluit. Verwacht: {expected_actions}, "
        f"Actueel: {set(coordinator_module.ALWAYS_HITL_ACTIONS)}"
    )


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action_type",
    [
        "terminate_employee",
        "hire_candidate",
        "adjust_compensation",
        "disciplinary_action",
        "sign_external_contract",
        "execute_high_value_payout",
        "delete_tenant_data",
    ],
)
async def test_live_always_hitl_actions_trigger_hitl_required(
    action_type: str, mock_council: AgentCouncil
) -> None:
    """Elk van de 7 acties in de live ALWAYS_HITL_ACTIONS set moet gegarandeerd
    upgraden naar HITL_REQUIRED bij unanieme APPROVE zonder monkeypatching."""
    proposal = _make_proposal(action_type=action_type)
    finalize_mock = _mock_finalize_capturing_final_verdict(mock_council, proposal)

    for o in mock_council._voting_officers:
        o.deliberate.return_value = _make_verdict(o.name, VerdictType.APPROVE)

    decision = await mock_council.deliberate(proposal)

    assert decision.verdict == DecisionVerdict.HITL_REQUIRED
    assert finalize_mock.call_args.kwargs["final_verdict"] is DecisionVerdict.HITL_REQUIRED


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_deliberate_upgrades_approved_to_hitl_required_for_always_hitl_action(
    monkeypatch: pytest.MonkeyPatch, mock_council: AgentCouncil
) -> None:
    """Een actie op `ALWAYS_HITL_ACTIONS` mag NOOIT automatisch doorgaan, ook niet als
    alle Officers voor stemmen (ADR-036 D4-003 / OP-166, GDPR art. 22)."""
    monkeypatch.setattr(
        coordinator_module, "ALWAYS_HITL_ACTIONS", frozenset({"__test_always_hitl_example__"})
    )
    proposal = _make_proposal(action_type="__test_always_hitl_example__")
    finalize_mock = _mock_finalize_capturing_final_verdict(mock_council, proposal)

    for o in mock_council._voting_officers:
        o.deliberate.return_value = _make_verdict(o.name, VerdictType.APPROVE)

    decision = await mock_council.deliberate(proposal)

    assert decision.verdict == DecisionVerdict.HITL_REQUIRED
    assert finalize_mock.call_args.kwargs["final_verdict"] is DecisionVerdict.HITL_REQUIRED


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_deliberate_upgrades_modified_to_hitl_required_for_always_hitl_action(
    monkeypatch: pytest.MonkeyPatch, mock_council: AgentCouncil
) -> None:
    """ADR-036 OP-168 (HITL-ticket-volledigheid sprint dag 3): een actie op
    `ALWAYS_HITL_ACTIONS` mag ook niet stilzwijgend voorbijgaan aan menselijk toezicht
    wanneer een Officer 'm alleen met een aanpassing wil goedkeuren. `APPROVE_WITH_
    MODIFICATION` (bijv. ComplianceOfficer bij een ontbrekende ai_disclosure) is een
    routinematig verdict, niet een edge case -- voor deze fix liet dat een gelijste actie
    zonder ticket en zonder mens hangen, het spiegelbeeld van de APPROVED-upgrade
    hierboven."""
    monkeypatch.setattr(
        coordinator_module, "ALWAYS_HITL_ACTIONS", frozenset({"__test_always_hitl_example__"})
    )
    proposal = _make_proposal(action_type="__test_always_hitl_example__")
    finalize_mock = _mock_finalize_capturing_final_verdict(mock_council, proposal)

    officers = mock_council._voting_officers
    officers[0].deliberate.return_value = _make_verdict(
        officers[0].name,
        VerdictType.APPROVE_WITH_MODIFICATION,
        evidence={"modifications": {"redacted_field": "value"}},
    )
    for o in officers[1:]:
        o.deliberate.return_value = _make_verdict(o.name, VerdictType.APPROVE)

    decision = await mock_council.deliberate(proposal)

    assert decision.verdict == DecisionVerdict.HITL_REQUIRED
    assert finalize_mock.call_args.kwargs["final_verdict"] is DecisionVerdict.HITL_REQUIRED
    # De officier-voorgestelde aanpassingen blijven meegegeven aan _finalize() -- relevante
    # context voor de mens die straks goedkeurt/afwijst, ook al is het eindverdict nu
    # HITL_REQUIRED en niet meer MODIFIED.
    assert finalize_mock.call_args.kwargs["modifications"] is not None


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_deliberate_leaves_approved_unchanged_when_action_not_on_always_hitl_list(
    mock_council: AgentCouncil,
) -> None:
    """Regressie: de DEFAULT (lege) `ALWAYS_HITL_ACTIONS` verandert vandaag geen enkel
    bestaand gedrag -- een gewone actie die alle Officers goedkeuren blijft APPROVED."""
    proposal = _make_proposal(action_type="navigate_to")
    finalize_mock = _mock_finalize_capturing_final_verdict(mock_council, proposal)

    for o in mock_council._voting_officers:
        o.deliberate.return_value = _make_verdict(o.name, VerdictType.APPROVE)

    decision = await mock_council.deliberate(proposal)

    assert decision.verdict == DecisionVerdict.APPROVED
    assert finalize_mock.call_args.kwargs["final_verdict"] is DecisionVerdict.APPROVED


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_deliberate_leaves_modified_unchanged_when_action_not_on_always_hitl_list(
    monkeypatch: pytest.MonkeyPatch, mock_council: AgentCouncil
) -> None:
    """ADR-036 OP-168 (HITL-ticket-volledigheid sprint dag 3, sprint-opstarten-brief SS3
    tabelrij dag 3): de negatieve richting van de MODIFIED-upgrade-mutatie was tot deze test
    ONGETEST -- alleen bewezen dat een MODIFIED op een GELISTE actie omhoog gaat naar
    HITL_REQUIRED (`test_deliberate_upgrades_modified_to_hitl_required_for_always_hitl_action`
    hierboven), nooit dat een MODIFIED op een actie DIE NIET op `ALWAYS_HITL_ACTIONS` staat
    gewoon MODIFIED blijft. `ALWAYS_HITL_ACTIONS` wordt hier bewust NIET leeg gelaten
    (`test_deliberate_leaves_approved_unchanged_when_action_not_on_always_hitl_list` hierboven
    bewijst alleen de default-lege lijst, wat de MODIFIED-conditie zelf niet raakt): met een
    NIET-lege lijst die de proposal's action_type mist, bewijst deze test dat de `in
    ALWAYS_HITL_ACTIONS`-voorwaarde daadwerkelijk filtert, niet alleen dat een lege lijst
    toevallig niets doet."""
    monkeypatch.setattr(
        coordinator_module,
        "ALWAYS_HITL_ACTIONS",
        frozenset({"__some_other_listed_action__"}),
    )
    proposal = _make_proposal(action_type="navigate_to")
    finalize_mock = _mock_finalize_capturing_final_verdict(mock_council, proposal)

    officers = mock_council._voting_officers
    officers[0].deliberate.return_value = _make_verdict(
        officers[0].name,
        VerdictType.APPROVE_WITH_MODIFICATION,
        evidence={"modifications": {"redacted_field": "value"}},
    )
    for o in officers[1:]:
        o.deliberate.return_value = _make_verdict(o.name, VerdictType.APPROVE)

    decision = await mock_council.deliberate(proposal)

    assert decision.verdict == DecisionVerdict.MODIFIED
    assert finalize_mock.call_args.kwargs["final_verdict"] is DecisionVerdict.MODIFIED


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("dissenting_verdict", "expected_final_verdict"),
    [
        (VerdictType.VETO, DecisionVerdict.BLOCKED),
        (VerdictType.REQUIRE_DEFERRAL, DecisionVerdict.DEFERRED),
        (VerdictType.REQUIRE_HITL, DecisionVerdict.HITL_REQUIRED),
    ],
)
async def test_deliberate_never_downgrades_a_non_approved_verdict_for_always_hitl_action(
    monkeypatch: pytest.MonkeyPatch,
    mock_council: AgentCouncil,
    dissenting_verdict: VerdictType,
    expected_final_verdict: DecisionVerdict,
) -> None:
    """De always-HITL-upgrade is een upgrade vanaf APPROVED **of** MODIFIED (ADR-036
    OP-168, sprint dag 3) -- maar mag een BLOCKED/DEFERRED/reeds-HITL_REQUIRED-verdict
    nooit aanraken, ook niet als de actie op `ALWAYS_HITL_ACTIONS` staat. APPROVE_WITH_
    MODIFICATION is BEWUST NIET in deze parametrisatie: sinds OP-168 wordt dat verdict wel
    degelijk geraakt (opgetild naar HITL_REQUIRED) -- zie
    `test_deliberate_upgrades_modified_to_hitl_required_for_always_hitl_action` hieronder
    voor die assertie. Getest tegen elk van de drie resterende verdicten afzonderlijk, niet
    aangenomen op basis van een representatief voorbeeld (ADR-036 fix-sprint dag 4 kostte 6
    reviewrondes precies op dit soort ongeteste "compleet"-aannames)."""
    monkeypatch.setattr(
        coordinator_module, "ALWAYS_HITL_ACTIONS", frozenset({"__test_always_hitl_example__"})
    )
    proposal = _make_proposal(action_type="__test_always_hitl_example__")
    finalize_mock = _mock_finalize_capturing_final_verdict(mock_council, proposal)

    officers = mock_council._voting_officers
    officers[0].deliberate.return_value = _make_verdict(officers[0].name, dissenting_verdict)
    for o in officers[1:]:
        o.deliberate.return_value = _make_verdict(o.name, VerdictType.APPROVE)

    decision = await mock_council.deliberate(proposal)

    assert decision.verdict == expected_final_verdict
    assert finalize_mock.call_args.kwargs["final_verdict"] is expected_final_verdict


@pytest.mark.unit
@pytest.mark.als
def test_aggregate_with_deferral_yields_deferred(mock_council: AgentCouncil) -> None:
    verdicts = (
        _make_verdict("compliance", VerdictType.APPROVE),
        _make_verdict("privacy", VerdictType.APPROVE),
        _make_verdict("security", VerdictType.APPROVE),
        _make_verdict("risk", VerdictType.REQUIRE_DEFERRAL),
        _make_verdict("ethics", VerdictType.APPROVE),
        _make_verdict("resource", VerdictType.APPROVE),
    )
    final, mods = mock_council._aggregate(verdicts)
    assert final == DecisionVerdict.DEFERRED
    assert mods is None

@pytest.mark.unit
@pytest.mark.als
def test_synthetic_veto_has_cache_disabled(mock_council: AgentCouncil) -> None:
    officer = mock_council._voting_officers[0]
    veto = mock_council._synthetic_verdict(officer, "TEST")
    assert veto.used_cache is False


# ----------------------------------------------------------------------------
# Regression tests for sprint-3-day-1 chaos fixes
# ----------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
def test_synthetic_verdict_respects_can_veto_true(mock_council: AgentCouncil) -> None:
    officer = mock_council._voting_officers[0]
    officer.can_veto = True
    # INTERNAL_ERROR: een crash blijft een veto. TIMEOUT is sinds 2026-10-27 uitstel naar een mens (eigen tests in
    # test_een_tijdoverschrijding_gaat_naar_een_mens.py).
    verdict = mock_council._synthetic_verdict(officer, "INTERNAL_ERROR")
    assert verdict.verdict == VerdictType.VETO


@pytest.mark.unit
@pytest.mark.als
def test_synthetic_verdict_respects_can_veto_false(mock_council: AgentCouncil) -> None:
    officer = mock_council._voting_officers[0]
    officer.can_veto = False
    verdict = mock_council._synthetic_verdict(officer, "INTERNAL_ERROR")
    assert verdict.verdict == VerdictType.REQUIRE_DEFERRAL
    assert verdict.reason_code == "INTERNAL_ERROR"


@pytest.mark.unit
@pytest.mark.als
def test_init_rejects_duplicate_officer_names(mock_council: AgentCouncil) -> None:
    """Duplicate officer names must raise ConfigurationError."""
    dup = mock_council._voting_officers[0]
    with pytest.raises(ConfigurationError, match="duplicate officer"):
        AgentCouncil(
            compliance=dup,
            privacy=dup,
            security=mock_council._voting_officers[2],
            risk=mock_council._voting_officers[3],
            ethics=mock_council._voting_officers[4],
            resource=mock_council._voting_officers[5],
            sanity=mock_council._voting_officers[6],
            audit=mock_council._audit_officer,
        )


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_deliberate_officer_crash_reason_code_is_internal_error(
    mock_council: AgentCouncil,
) -> None:
    """Regression: officer crash must produce reason_code INTERNAL_ERROR."""
    proposal = _make_proposal()
    context = await mock_council._build_context(proposal)

    mock_council._voting_officers[0].deliberate.side_effect = ValueError("boom")
    for o in mock_council._voting_officers[1:]:
        o.deliberate.return_value = _make_verdict(o.name, VerdictType.APPROVE)

    verdicts = await mock_council._gather_verdicts(proposal, context)
    crash_verdict = next(
        v for v in verdicts if v.officer_name == mock_council._voting_officers[0].name
    )
    assert crash_verdict.reason_code == "INTERNAL_ERROR"


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_finalize_includes_officer_verdicts_on_audit_failure(
    mock_council: AgentCouncil,
) -> None:
    """Regression: _fail_secure_decision must carry officer_verdicts."""
    proposal = _make_proposal()
    from src.core.copilot.council.audit_writer import AuditWriteError

    mock_council._audit_officer.finalize_and_persist = AsyncMock(
        side_effect=AuditWriteError("db down")
    )

    fake_verdicts = tuple(
        _make_verdict(o.name, VerdictType.APPROVE)
        for o in mock_council._voting_officers
    )
    decision = await mock_council._finalize(
        proposal=proposal,
        officer_verdicts=fake_verdicts,
        final_verdict=DecisionVerdict.APPROVED,
        modifications=None,
        context=await mock_council._build_context(proposal),
        start_ms=0.0,
    )

    assert decision.verdict == DecisionVerdict.BLOCKED
    assert len(decision.officer_verdicts) == 8  # 7 voting + 1 audit synthetic
    audit_v = next(
        v for v in decision.officer_verdicts if v.reason_code == "AUDIT_WRITE_FAILED"
    )
    assert audit_v.officer_name == mock_council._audit_officer.name




@pytest.mark.unit
class TestCritical4DeliberationContextCapabilities:
    """CRITICAL-4: DeliberationContext must include platform capability metadata."""

    async def test_build_context_includes_capability_metadata(self, mock_council: AgentCouncil) -> None:
        """_build_context() must populate registered_tools, agent_health, domain_packs."""
        proposal = _make_proposal()
        context = await mock_council._build_context(proposal)

        assert hasattr(context, "registered_tools")
        assert hasattr(context, "agent_health")
        assert hasattr(context, "domain_packs")

    async def test_build_context_with_capabilities_override(self, mock_council: AgentCouncil) -> None:
        """_build_context() must read capability snapshot from proposal."""
        from dataclasses import replace
        proposal = _make_proposal()
        capabilities = {
            "registered_tools": [{"name": "navigate"}, {"name": "search"}],
            "agent_health": {"navigate": "healthy"},
            "domain_packs": ["core", "finance"],
        }
        proposal_with_caps = replace(proposal, capabilities=capabilities)
        context = await mock_council._build_context(proposal_with_caps)

        assert context.registered_tools == capabilities["registered_tools"]
        assert context.agent_health == capabilities["agent_health"]
        assert context.domain_packs == capabilities["domain_packs"]
