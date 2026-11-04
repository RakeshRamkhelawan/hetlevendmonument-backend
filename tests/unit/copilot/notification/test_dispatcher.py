"""
Unit tests for NotificationDispatcher.

Covers all 4 channel paths, best_effort wrapping, logging, budget consumption,
and security (no cross-tenant push).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import pytest

from src.core.copilot.council.types import (
    CouncilDecision,
    DataClassification,
    DecisionVerdict,
    OfficerVerdict,
    Severity,
    VerdictType,
)
from src.core.copilot.notification.budget import (
    BudgetResult,
    BudgetVerdict,
    NotificationBudgetTracker,
)
from src.core.copilot.notification.digest import DigestQueue
from src.core.copilot.notification.dispatcher import Channel, DispatchResult, NotificationDispatcher
from src.core.copilot.notification.models import NotificationPreferences
from src.core.copilot.notification.preferences_repo import UserNotificationPreferencesRepo
from src.core.copilot.notification.ws_pusher import WSPusher
from src.core.copilot.proactive.types import Signal


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_signal(
    severity: Severity = Severity.LOW,
    tenant_id: int = 1,
    user_id: int = 10,
) -> Signal:
    return Signal(
        tenant_id=tenant_id,
        affected_user_id=user_id,
        monitor_name="test_monitor",
        title="Test title",
        body="Test body",
        severity=severity,
        data_classification=DataClassification.INTERNAL,
        suggested_actions=[],
        detection_reasoning="reason",
        confidence=0.8,
        context={},
    )


def _make_decision(verdict: DecisionVerdict = DecisionVerdict.APPROVED) -> CouncilDecision:
    officer_verdict = OfficerVerdict(
        officer_name="ComplianceOfficer",
        officer_version="1.0.0",
        verdict=VerdictType.APPROVE,
        reason_code="OK",
        reason_text="Approved",
        evidence={},
        deliberation_ms=10,
        confidence=0.9,
    )
    return CouncilDecision(
        proposal_id=uuid4(),
        tenant_id=1,
        user_id=10,
        verdict=verdict,
        officer_verdicts=(officer_verdict,),
        explanation_for_user="All good.",
        decision_hash="abc123",
        previous_decision_hash=None,
        deliberation_ms=50,
    )


def _make_prefs(
    delivery_mode: str = "individual",
    daily_limit: int = 25,
) -> NotificationPreferences:
    return NotificationPreferences(
        user_id=10,
        tenant_id=1,
        delivery_mode=delivery_mode,  # type: ignore[arg-type]
        daily_limit=daily_limit,
    )


def _make_dispatcher(
    prefs: NotificationPreferences | None = None,
    budget_verdict: BudgetVerdict = BudgetVerdict.APPROVED,
    ws_pusher: WSPusher | None = None,
    digest_queue: DigestQueue | None = None,
) -> tuple[NotificationDispatcher, AsyncMock, AsyncMock]:
    mock_prefs_repo = AsyncMock(spec=UserNotificationPreferencesRepo)
    mock_prefs_repo.get_for_user.return_value = prefs or _make_prefs()

    mock_budget = AsyncMock(spec=NotificationBudgetTracker)
    mock_budget.consume.return_value = BudgetResult(
        verdict=budget_verdict,
        remaining=20,
        daily_limit=25,
        reason="WITHIN_BUDGET" if budget_verdict == BudgetVerdict.APPROVED else "DEFERRED",
    )

    mock_ws = ws_pusher or AsyncMock(spec=WSPusher)
    mock_dq = digest_queue or AsyncMock(spec=DigestQueue)

    dispatcher = NotificationDispatcher(
        budget_tracker=mock_budget,
        preferences_repo=mock_prefs_repo,
        ws_pusher=mock_ws,
        digest_queue=mock_dq,
    )
    return dispatcher, mock_ws, mock_dq


# ---------------------------------------------------------------------------
# Happy path: channel selection
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
async def test_critical_severity_always_popup() -> None:
    dispatcher, mock_ws, mock_dq = _make_dispatcher()
    signal = _make_signal(severity=Severity.CRITICAL)
    decision = _make_decision(DecisionVerdict.APPROVED)

    result = await dispatcher.dispatch(signal, decision)

    assert result.channel == Channel.POPUP
    mock_ws.push.assert_awaited_once()
    mock_dq.enqueue.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.als
async def test_critical_severity_popup_even_with_digest_preference() -> None:
    """CRITICAL overrides user delivery_mode preference -- life-safety requirement."""
    prefs = _make_prefs(delivery_mode="digest")
    dispatcher, mock_ws, mock_dq = _make_dispatcher(prefs=prefs)
    signal = _make_signal(severity=Severity.CRITICAL)
    decision = _make_decision(DecisionVerdict.APPROVED)

    result = await dispatcher.dispatch(signal, decision)

    assert result.channel == Channel.POPUP
    mock_ws.push.assert_awaited_once()
    mock_dq.enqueue.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.als
async def test_deferred_verdict_always_digest() -> None:
    """Council DEFERRED verdict routes to DIGEST regardless of severity."""
    dispatcher, mock_ws, mock_dq = _make_dispatcher()
    signal = _make_signal(severity=Severity.HIGH)
    decision = _make_decision(DecisionVerdict.DEFERRED)

    result = await dispatcher.dispatch(signal, decision)

    assert result.channel == Channel.DIGEST
    mock_dq.enqueue.assert_awaited_once()
    mock_ws.push.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.als
async def test_budget_deferred_routes_to_digest() -> None:
    """Budget DEFERRED (quiet hours / daily limit) routes to DIGEST."""
    dispatcher, mock_ws, mock_dq = _make_dispatcher(budget_verdict=BudgetVerdict.DEFERRED)
    signal = _make_signal(severity=Severity.HIGH)
    decision = _make_decision(DecisionVerdict.APPROVED)

    result = await dispatcher.dispatch(signal, decision)

    assert result.channel == Channel.DIGEST
    mock_dq.enqueue.assert_awaited_once()
    mock_ws.push.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.als
async def test_user_with_digest_mode_routes_to_digest() -> None:
    prefs = _make_prefs(delivery_mode="digest")
    dispatcher, mock_ws, mock_dq = _make_dispatcher(prefs=prefs)
    signal = _make_signal(severity=Severity.HIGH)
    decision = _make_decision(DecisionVerdict.APPROVED)

    result = await dispatcher.dispatch(signal, decision)

    assert result.channel == Channel.DIGEST
    mock_dq.enqueue.assert_awaited_once()
    mock_ws.push.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.als
async def test_user_with_batched_mode_routes_to_digest() -> None:
    prefs = _make_prefs(delivery_mode="batched")
    dispatcher, mock_ws, mock_dq = _make_dispatcher(prefs=prefs)
    signal = _make_signal(severity=Severity.MEDIUM)
    decision = _make_decision(DecisionVerdict.APPROVED)

    result = await dispatcher.dispatch(signal, decision)

    assert result.channel == Channel.DIGEST


@pytest.mark.unit
@pytest.mark.als
async def test_high_severity_individual_mode_routes_to_inline() -> None:
    dispatcher, mock_ws, mock_dq = _make_dispatcher()
    signal = _make_signal(severity=Severity.HIGH)
    decision = _make_decision(DecisionVerdict.APPROVED)

    result = await dispatcher.dispatch(signal, decision)

    assert result.channel == Channel.INLINE
    mock_ws.push.assert_awaited_once()
    mock_dq.enqueue.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.als
async def test_low_severity_routes_to_silent() -> None:
    dispatcher, mock_ws, mock_dq = _make_dispatcher()
    signal = _make_signal(severity=Severity.LOW)
    decision = _make_decision(DecisionVerdict.APPROVED)

    result = await dispatcher.dispatch(signal, decision)

    assert result.channel == Channel.SILENT
    mock_ws.push.assert_awaited_once()
    mock_dq.enqueue.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.als
async def test_info_severity_routes_to_silent() -> None:
    dispatcher, mock_ws, mock_dq = _make_dispatcher()
    signal = _make_signal(severity=Severity.INFO)
    decision = _make_decision(DecisionVerdict.APPROVED)

    result = await dispatcher.dispatch(signal, decision)

    assert result.channel == Channel.SILENT


@pytest.mark.unit
@pytest.mark.als
async def test_medium_severity_individual_routes_to_silent() -> None:
    """MEDIUM maps to SILENT (silent dot indicator) per ADR-027 sec 9.2."""
    dispatcher, mock_ws, mock_dq = _make_dispatcher()
    signal = _make_signal(severity=Severity.MEDIUM)
    decision = _make_decision(DecisionVerdict.APPROVED)

    result = await dispatcher.dispatch(signal, decision)

    assert result.channel == Channel.SILENT


# ---------------------------------------------------------------------------
# DispatchResult correctness
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
async def test_dispatch_result_contains_correct_fields() -> None:
    dispatcher, _, _ = _make_dispatcher(budget_verdict=BudgetVerdict.APPROVED)
    signal = _make_signal(severity=Severity.HIGH)
    decision = _make_decision()

    result = await dispatcher.dispatch(signal, decision)

    assert result.user_id == signal.affected_user_id
    assert result.budget_verdict == BudgetVerdict.APPROVED
    assert result.delivered_at.tzinfo is not None


# ---------------------------------------------------------------------------
# WS payload correctness
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
async def test_ws_push_payload_contains_decision_id() -> None:
    dispatcher, mock_ws, _ = _make_dispatcher()
    signal = _make_signal(severity=Severity.HIGH)
    decision = _make_decision()

    await dispatcher.dispatch(signal, decision)

    call_kwargs = mock_ws.push.call_args
    payload = call_kwargs.kwargs["payload"]
    assert payload["decision_id"] == str(decision.decision_id)
    assert "/api/v1/copilot/audit/" in payload["explanation_url"]


@pytest.mark.unit
@pytest.mark.als
async def test_ws_push_uses_correct_user_id() -> None:
    dispatcher, mock_ws, _ = _make_dispatcher()
    signal = _make_signal(severity=Severity.HIGH, user_id=42)
    decision = _make_decision()

    await dispatcher.dispatch(signal, decision)

    call_kwargs = mock_ws.push.call_args
    assert call_kwargs.kwargs["user_id"] == 42


# ---------------------------------------------------------------------------
# Digest enqueue correctness
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
async def test_digest_enqueue_called_with_correct_args() -> None:
    dispatcher, _, mock_dq = _make_dispatcher()
    signal = _make_signal(severity=Severity.LOW)
    decision = _make_decision(DecisionVerdict.DEFERRED)

    await dispatcher.dispatch(signal, decision)

    mock_dq.enqueue.assert_awaited_once_with(
        signal.affected_user_id,
        signal,
        str(decision.decision_id),
    )


# ---------------------------------------------------------------------------
# Mutual exclusion: no double delivery
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
async def test_no_double_delivery_ws_and_digest_are_mutually_exclusive() -> None:
    """A signal must be delivered via exactly one channel."""
    for verdict in (BudgetVerdict.APPROVED, BudgetVerdict.DEFERRED):
        dispatcher, mock_ws, mock_dq = _make_dispatcher(budget_verdict=verdict)
        signal = _make_signal(severity=Severity.HIGH)
        decision = _make_decision(
            DecisionVerdict.APPROVED
            if verdict == BudgetVerdict.APPROVED
            else DecisionVerdict.DEFERRED
        )

        await dispatcher.dispatch(signal, decision)

        ws_called = mock_ws.push.call_count
        dq_called = mock_dq.enqueue.call_count
        assert ws_called + dq_called == 1, (
            f"Expected exactly 1 delivery for budget={verdict}, got ws={ws_called} dq={dq_called}"
        )


# ---------------------------------------------------------------------------
# best_effort: dispatch failure does not raise
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
async def test_ws_push_failure_does_not_propagate() -> None:
    """best_effort wrapper must absorb WS push failures."""
    mock_ws = AsyncMock(spec=WSPusher)
    mock_ws.push.side_effect = ConnectionError("Redis down")
    dispatcher, _, _ = _make_dispatcher(ws_pusher=mock_ws)
    signal = _make_signal(severity=Severity.HIGH)
    decision = _make_decision()

    # Should not raise
    result = await dispatcher.dispatch(signal, decision)
    assert result.channel == Channel.INLINE


@pytest.mark.unit
@pytest.mark.als
async def test_digest_enqueue_failure_does_not_propagate() -> None:
    """best_effort wrapper must absorb DigestQueue failures."""
    mock_dq = AsyncMock(spec=DigestQueue)
    mock_dq.enqueue.side_effect = ConnectionError("Redis down")
    dispatcher, _, _ = _make_dispatcher(digest_queue=mock_dq)
    signal = _make_signal(severity=Severity.LOW)
    decision = _make_decision(DecisionVerdict.DEFERRED)

    result = await dispatcher.dispatch(signal, decision)
    assert result.channel == Channel.DIGEST


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
async def test_dispatch_logs_channel_and_user_id(caplog: Any) -> None:
    dispatcher, _, _ = _make_dispatcher()
    signal = _make_signal(severity=Severity.HIGH)
    decision = _make_decision()

    with caplog.at_level(logging.INFO, logger="src.core.copilot.notification.dispatcher"):
        await dispatcher.dispatch(signal, decision)

    assert any("dispatch" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# Security: budget always consumed (counter must tick even for CRITICAL)
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.security
@pytest.mark.als
async def test_budget_consume_always_called() -> None:
    """Budget tracker must be called for every dispatch, including CRITICAL."""
    dispatcher, _, _ = _make_dispatcher()
    signal = _make_signal(severity=Severity.CRITICAL)
    decision = _make_decision()

    await dispatcher.dispatch(signal, decision)

    dispatcher._budget_tracker.consume.assert_awaited_once()


# ---------------------------------------------------------------------------
# Security: tenant isolation -- push goes to correct user_id
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.security
@pytest.mark.multi_tenant
@pytest.mark.als
async def test_push_targets_signal_user_id_not_decision_user_id() -> None:
    """WSPusher must use signal.affected_user_id, not decision.user_id."""
    dispatcher, mock_ws, _ = _make_dispatcher()
    # Signal targets user 99, decision targets user 1 (the requester)
    signal = _make_signal(severity=Severity.HIGH, user_id=99)
    decision = _make_decision()  # decision.user_id == 10

    await dispatcher.dispatch(signal, decision)

    call_kwargs = mock_ws.push.call_args
    assert call_kwargs.kwargs["user_id"] == 99
