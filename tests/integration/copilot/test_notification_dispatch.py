"""
Integration test: signal -> NotificationDispatcher -> WSPusher (mock).

Uses real DigestQueue (in-memory FakeRedis), real budget tracker logic,
and a real NotificationDispatcher. WSPusher is mocked to capture push calls.
No database required; preferences repo is mocked.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

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
from src.core.copilot.notification.digest import DigestGenerator, DigestQueue
from src.core.copilot.notification.dispatcher import Channel, NotificationDispatcher
from src.core.copilot.notification.models import NotificationPreferences
from src.core.copilot.notification.preferences_repo import UserNotificationPreferencesRepo
from src.core.copilot.notification.ws_pusher import WSPusher
from src.core.copilot.proactive.types import Signal


# ---------------------------------------------------------------------------
# Shared fake Redis (no actual Redis needed for this integration test)
# ---------------------------------------------------------------------------


class FakeRedis:
    def __init__(self) -> None:
        self._store: dict[str, list[str]] = {}
        self._ttl: dict[str, int] = {}

    async def lpush(self, key: str, value: str) -> int:
        self._store.setdefault(key, []).insert(0, value)
        return len(self._store[key])

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        items = self._store.get(key, [])
        if end == -1:
            return list(items)
        return list(items[start : end + 1])

    async def expire(self, key: str, ttl: int) -> None:
        self._ttl[key] = ttl

    async def delete(self, key: str) -> int:
        return len(self._store.pop(key, []))

    async def eval(self, script: str, numkeys: int, key: str) -> list[str]:
        items = list(self._store.get(key, []))
        if items:
            self._store.pop(key, None)
        return items

    async def publish(self, channel: str, message: str) -> int:
        return 1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_signal(
    severity: Severity = Severity.HIGH,
    tenant_id: int = 1,
    user_id: int = 10,
) -> Signal:
    return Signal(
        tenant_id=tenant_id,
        affected_user_id=user_id,
        monitor_name="integration_monitor",
        title="Integration test signal",
        body="Body",
        severity=severity,
        data_classification=DataClassification.INTERNAL,
        suggested_actions=[{"action": "review"}],
        detection_reasoning="test",
        confidence=0.9,
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
        deliberation_ms=5,
        confidence=0.95,
    )
    return CouncilDecision(
        proposal_id=uuid4(),
        tenant_id=1,
        user_id=10,
        verdict=verdict,
        officer_verdicts=(officer_verdict,),
        explanation_for_user="OK",
        decision_hash="hash123",
        previous_decision_hash=None,
        deliberation_ms=15,
    )


# ---------------------------------------------------------------------------
# Integration: signal -> dispatcher -> WS mock
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.als
async def test_signal_to_dispatcher_to_ws_mock() -> None:
    """
    Full path: signal (HIGH severity, individual mode, within budget)
    -> dispatcher routes to INLINE -> WSPusher.push called with correct payload.
    """
    redis = FakeRedis()
    digest_queue = DigestQueue(redis)
    ws_pusher_mock = AsyncMock(spec=WSPusher)

    prefs = NotificationPreferences(user_id=10, tenant_id=1, delivery_mode="individual")
    mock_prefs_repo = AsyncMock(spec=UserNotificationPreferencesRepo)
    mock_prefs_repo.get_for_user.return_value = prefs

    budget_tracker = AsyncMock(spec=NotificationBudgetTracker)
    budget_tracker.consume.return_value = BudgetResult(
        verdict=BudgetVerdict.APPROVED,
        remaining=24,
        daily_limit=25,
        reason="WITHIN_BUDGET",
    )

    dispatcher = NotificationDispatcher(
        budget_tracker=budget_tracker,
        preferences_repo=mock_prefs_repo,
        ws_pusher=ws_pusher_mock,
        digest_queue=digest_queue,
    )

    signal = _make_signal(severity=Severity.HIGH)
    decision = _make_decision()

    result = await dispatcher.dispatch(signal, decision)

    assert result.channel == Channel.INLINE
    ws_pusher_mock.push.assert_awaited_once()
    payload = ws_pusher_mock.push.call_args.kwargs["payload"]
    assert payload["type"] == "signal"
    assert payload["severity"] == "high"
    assert payload["channel"] == "inline"
    assert payload["title"] == signal.title
    assert payload["decision_id"] == str(decision.decision_id)
    assert "/api/v1/copilot/audit/" in payload["explanation_url"]


@pytest.mark.integration
@pytest.mark.als
async def test_signal_to_dispatcher_to_digest_queue() -> None:
    """
    Full path: signal (LOW severity, digest mode)
    -> dispatcher routes to DIGEST -> DigestQueue contains the signal.
    """
    redis = FakeRedis()
    digest_queue = DigestQueue(redis)
    ws_pusher = WSPusher(redis)

    prefs = NotificationPreferences(user_id=10, tenant_id=1, delivery_mode="digest")
    mock_prefs_repo = AsyncMock(spec=UserNotificationPreferencesRepo)
    mock_prefs_repo.get_for_user.return_value = prefs

    budget_tracker = AsyncMock(spec=NotificationBudgetTracker)
    budget_tracker.consume.return_value = BudgetResult(
        verdict=BudgetVerdict.APPROVED,
        remaining=24,
        daily_limit=25,
        reason="WITHIN_BUDGET",
    )

    dispatcher = NotificationDispatcher(
        budget_tracker=budget_tracker,
        preferences_repo=mock_prefs_repo,
        ws_pusher=ws_pusher,
        digest_queue=digest_queue,
    )

    signal = _make_signal(severity=Severity.LOW)
    decision = _make_decision()

    result = await dispatcher.dispatch(signal, decision)

    assert result.channel == Channel.DIGEST

    # DigestQueue should have the signal stored
    queued = await digest_queue.drain(user_id=10, tenant_id=1)
    assert len(queued) == 1
    assert queued[0].signal.title == signal.title
    assert queued[0].decision_id == str(decision.decision_id)


@pytest.mark.integration
@pytest.mark.als
async def test_critical_signal_bypasses_digest_mode_and_pushes_immediately() -> None:
    """CRITICAL signal goes to POPUP even when user preference is digest."""
    redis = FakeRedis()
    digest_queue = DigestQueue(redis)
    ws_pusher_mock = AsyncMock(spec=WSPusher)

    prefs = NotificationPreferences(
        user_id=10, tenant_id=1, delivery_mode="digest", critical_always_immediate=True
    )
    mock_prefs_repo = AsyncMock(spec=UserNotificationPreferencesRepo)
    mock_prefs_repo.get_for_user.return_value = prefs

    budget_tracker = AsyncMock(spec=NotificationBudgetTracker)
    budget_tracker.consume.return_value = BudgetResult(
        verdict=BudgetVerdict.OVERRIDE,
        remaining=-1,
        daily_limit=25,
        reason="CRITICAL_BYPASS",
    )

    dispatcher = NotificationDispatcher(
        budget_tracker=budget_tracker,
        preferences_repo=mock_prefs_repo,
        ws_pusher=ws_pusher_mock,
        digest_queue=digest_queue,
    )

    signal = _make_signal(severity=Severity.CRITICAL)
    decision = _make_decision()

    result = await dispatcher.dispatch(signal, decision)

    assert result.channel == Channel.POPUP
    ws_pusher_mock.push.assert_awaited_once()

    # DigestQueue must be empty -- CRITICAL was not enqueued
    queued = await digest_queue.drain(user_id=10, tenant_id=1)
    assert queued == []


@pytest.mark.integration
@pytest.mark.als
async def test_digest_generator_full_flow() -> None:
    """
    Full digest flow: 3 signals enqueued -> DigestGenerator builds digest
    -> send_digest pushes one consolidated WS message.
    """
    redis = FakeRedis()
    digest_queue = DigestQueue(redis)
    ws_pusher_mock = AsyncMock(spec=WSPusher)
    generator = DigestGenerator(digest_queue=digest_queue, ws_pusher=ws_pusher_mock)

    for i in range(3):
        signal = _make_signal(severity=Severity.LOW, user_id=10)
        await digest_queue.enqueue(user_id=10, signal=signal, decision_id=str(uuid4()))

    digest = await generator.generate_for_user(user_id=10, tenant_id=1)
    assert digest is not None
    assert len(digest.signals) == 3

    await generator.send_digest(digest)

    ws_pusher_mock.push.assert_awaited_once()
    payload = ws_pusher_mock.push.call_args.kwargs["payload"]
    assert payload["type"] == "digest"
    assert len(payload["signals"]) == 3

    # Queue drained after generate_for_user
    assert await digest_queue.drain(user_id=10, tenant_id=1) == []
