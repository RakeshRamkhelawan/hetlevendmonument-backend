"""E2E test: notification budget -- 26th signal is routed to digest.

Budget key: copilot:notif:{tenant_id}:{user_id}:{date_key}
Default daily_limit = 25 (NotificationPreferences default).
After seeding the counter to 25, the next dispatch hits the Lua limit guard
and routes to Channel.DIGEST instead of WS.

Unhappy path: CRITICAL severity bypasses the budget entirely (POPUP).
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import pytest

from src.core.copilot.council.types import CouncilDecision, DecisionVerdict
from src.core.copilot.notification.budget import BudgetVerdict, NotificationBudgetTracker
from src.core.copilot.notification.digest import DigestQueue
from src.core.copilot.notification.dispatcher import Channel, NotificationDispatcher
from src.core.copilot.notification.preferences_repo import UserNotificationPreferencesRepo
from src.core.copilot.proactive.types import Signal
from src.core.copilot.council.types import DataClassification, Severity
from tests.integration.copilot.conftest import seed_tenants

logger = logging.getLogger(__name__)


def _approved_decision(tenant_id: int, user_id: int) -> CouncilDecision:
    h = hashlib.sha256(str(uuid4()).encode()).hexdigest()
    return CouncilDecision(
        proposal_id=uuid4(),
        tenant_id=tenant_id,
        user_id=user_id,
        verdict=DecisionVerdict.APPROVED,
        officer_verdicts=(),
        explanation_for_user="Approved in budget E2E test",
        decision_hash=h,
        previous_decision_hash=None,
        deliberation_ms=5,
    )


def _make_signal(
    tenant_id: int,
    user_id: int,
    severity: Severity = Severity.HIGH,
) -> Signal:
    return Signal(
        tenant_id=tenant_id,
        affected_user_id=user_id,
        monitor_name="agent_health",
        title="Agent failing",
        body="Agent has high error rate.",
        severity=severity,
        data_classification=DataClassification.INTERNAL,
        suggested_actions=[],
        detection_reasoning="error_rate > threshold",
        confidence=0.95,
        context={},
    )


class _MockWSPusher:
    def __init__(self) -> None:
        self.pushed: list[dict[str, Any]] = []

    async def push(self, user_id: int, payload: dict[str, Any]) -> None:
        self.pushed.append(payload)


@pytest.mark.integration
@pytest.mark.als
@pytest.mark.e2e
async def test_26th_signal_routed_to_digest_when_budget_exhausted(
    db_session: Any,
    real_redis_client: Any,
) -> None:
    """Budget at limit: 26th signal goes to DIGEST, not WS."""
    tenant_id = 301
    user_id = 3001

    await seed_tenants(db_session, [tenant_id])

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    budget_key = NotificationBudgetTracker.KEY_TEMPLATE.format(
        tenant_id=tenant_id, user_id=user_id, date_key=today
    )
    digest_key = DigestQueue.KEY_TEMPLATE.format(tenant_id=tenant_id, user_id=user_id)

    # Pre-seed and cleanup
    await real_redis_client.delete(budget_key)
    await real_redis_client.delete(digest_key)

    logger.info(
        "e2e_start",
        extra={
            "test_name": "test_26th_signal_routed_to_digest_when_budget_exhausted",
            "tenant_id": tenant_id,
        },
    )

    try:
        # Seed counter to 25 (daily_limit reached)
        await real_redis_client.set(budget_key, "25")

        ws_mock = _MockWSPusher()
        prefs_repo = UserNotificationPreferencesRepo(db_session)
        dispatcher = NotificationDispatcher(
            budget_tracker=NotificationBudgetTracker(real_redis_client),
            preferences_repo=prefs_repo,
            ws_pusher=ws_mock,  # type: ignore[arg-type]
            digest_queue=DigestQueue(real_redis_client),
        )

        signal = _make_signal(tenant_id, user_id, Severity.HIGH)
        decision = _approved_decision(tenant_id, user_id)

        result = await dispatcher.dispatch(signal, decision)

        # Budget exhausted -> DEFERRED -> DIGEST channel
        assert result.budget_verdict == BudgetVerdict.DEFERRED
        assert result.channel == Channel.DIGEST
        assert result.user_id == user_id

        # Digest queue must have the signal
        queued = await real_redis_client.lrange(digest_key, 0, -1)
        assert len(queued) >= 1, "Signal must be in digest queue"

        # WS was NOT pushed (routed to digest instead)
        assert len(ws_mock.pushed) == 0

        logger.info(
            "e2e_complete",
            extra={
                "test_name": "test_26th_signal_routed_to_digest_when_budget_exhausted",
                "tenant_id": tenant_id,
                "channel": result.channel.value,
            },
        )
    finally:
        await real_redis_client.delete(budget_key)
        await real_redis_client.delete(digest_key)


@pytest.mark.integration
@pytest.mark.als
@pytest.mark.e2e
async def test_critical_signal_bypasses_budget_and_reaches_user(
    db_session: Any,
    real_redis_client: Any,
) -> None:
    """CRITICAL severity bypasses daily budget and is delivered via POPUP."""
    tenant_id = 302
    user_id = 3002

    await seed_tenants(db_session, [tenant_id])

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    budget_key = NotificationBudgetTracker.KEY_TEMPLATE.format(
        tenant_id=tenant_id, user_id=user_id, date_key=today
    )
    digest_key = DigestQueue.KEY_TEMPLATE.format(tenant_id=tenant_id, user_id=user_id)

    await real_redis_client.delete(budget_key)
    await real_redis_client.delete(digest_key)

    try:
        # Budget already at limit
        await real_redis_client.set(budget_key, "25")

        ws_mock = _MockWSPusher()
        prefs_repo = UserNotificationPreferencesRepo(db_session)
        dispatcher = NotificationDispatcher(
            budget_tracker=NotificationBudgetTracker(real_redis_client),
            preferences_repo=prefs_repo,
            ws_pusher=ws_mock,  # type: ignore[arg-type]
            digest_queue=DigestQueue(real_redis_client),
        )

        # CRITICAL severity -- must bypass budget check entirely
        signal = _make_signal(tenant_id, user_id, Severity.CRITICAL)
        decision = _approved_decision(tenant_id, user_id)

        result = await dispatcher.dispatch(signal, decision)

        # CRITICAL -> POPUP (budget override, not deferred)
        assert result.channel == Channel.POPUP
        assert result.budget_verdict == BudgetVerdict.OVERRIDE

        # WS was pushed, digest was NOT
        assert len(ws_mock.pushed) == 1
        assert ws_mock.pushed[0]["severity"] == "critical"

        queued = await real_redis_client.lrange(digest_key, 0, -1)
        assert len(queued) == 0, "CRITICAL signal must not go to digest"

    finally:
        await real_redis_client.delete(budget_key)
        await real_redis_client.delete(digest_key)
