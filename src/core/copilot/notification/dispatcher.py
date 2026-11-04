"""
Notification Dispatcher -- routes signals to the correct delivery channel.

Channel selection priority (highest to lowest):
  1. CRITICAL severity          -> POPUP  (life-safety, non-overridable)
  2. Council DEFERRED verdict   -> DIGEST
  3. Budget DEFERRED verdict    -> DIGEST (quiet hours or daily limit reached)
  4. User delivery_mode digest/batched -> DIGEST
  5. HIGH severity              -> INLINE
  6. INFO/LOW/MEDIUM            -> SILENT (dot indicator only)

WS push and digest enqueue are wrapped in best_effort: if dispatch fails
after the Council has already APPROVED, only UI delivery is lost -- the
audit chain is unaffected.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from src.core.copilot.council.types import CouncilDecision, DecisionVerdict
from src.core.copilot.notification.budget import BudgetVerdict, NotificationBudgetTracker
from src.core.copilot.notification.digest import DigestQueue
from src.core.copilot.notification.preferences_repo import UserNotificationPreferencesRepo
from src.core.copilot.notification.ws_pusher import WSPusher
from src.core.copilot.council.types import Severity
from src.core.copilot.proactive.types import Signal
from src.core.utils.best_effort import best_effort

logger = logging.getLogger(__name__)

# Relative URL template for the right-to-explanation endpoint (ADR-027 sec 10).
# Class-level constant to avoid inline string duplication.
_EXPLANATION_URL_TEMPLATE = "/api/v1/copilot/audit/{decision_id}"


class Channel(Enum):
    SILENT = "silent"  # Coloured dot on Co-Pilot icon
    INLINE = "inline"  # Toast / card on current page
    POPUP = "popup"  # Modal -- interrupts user
    DIGEST = "digest"  # Daily summary batch


@dataclass(frozen=True)
class DispatchResult:
    channel: Channel
    delivered_at: datetime
    user_id: int
    budget_verdict: BudgetVerdict


class NotificationDispatcher:
    """Route a proactive signal to the correct notification channel."""

    def __init__(
        self,
        budget_tracker: NotificationBudgetTracker,
        preferences_repo: UserNotificationPreferencesRepo,
        ws_pusher: WSPusher,
        digest_queue: DigestQueue,
    ) -> None:
        self._budget_tracker = budget_tracker
        self._preferences_repo = preferences_repo
        self._ws_pusher = ws_pusher
        self._digest_queue = digest_queue

    async def dispatch(
        self,
        signal: Signal,
        decision: CouncilDecision,
    ) -> DispatchResult:
        # 1. Load per-user, tenant-scoped preferences.
        prefs = await self._preferences_repo.get_for_user(
            user_id=signal.affected_user_id,
            tenant_id=signal.tenant_id,
        )

        # 2. Consume budget (or OVERRIDE for CRITICAL). This must always run
        #    so the daily counter stays accurate even for CRITICAL signals.
        budget_result = await self._budget_tracker.consume(
            tenant_id=signal.tenant_id,
            user_id=signal.affected_user_id,
            prefs=prefs,
            severity=signal.severity.value,
        )

        # 3. Channel selection in strict priority order.
        if signal.severity == Severity.CRITICAL:
            # CRITICAL is checked first and is NEVER overridden by budget or
            # preference -- life-safety signals must always reach the user.
            channel = Channel.POPUP
        elif decision.verdict == DecisionVerdict.DEFERRED:
            channel = Channel.DIGEST
        elif budget_result.verdict == BudgetVerdict.DEFERRED:
            # Quiet hours or daily limit reached.
            channel = Channel.DIGEST
        elif prefs.delivery_mode in ("digest", "batched"):
            channel = Channel.DIGEST
        elif signal.severity == Severity.HIGH:
            channel = Channel.INLINE
        else:
            # NOTE: INFO, LOW, and MEDIUM severity signals use a silent dot
            # indicator only. This is intentional per ADR-027 sec 9.2:
            # low-urgency signals should not interrupt user workflow.
            channel = Channel.SILENT

        logger.info(
            "dispatch",
            extra={
                "channel": channel.value,
                "severity": signal.severity.value,
                "user_id": signal.affected_user_id,
                "tenant_id": signal.tenant_id,
                "decision_id": str(decision.decision_id),
            },
        )

        # 4. Deliver via selected channel. Exactly one branch executes (no
        #    double-delivery). Both are wrapped in best_effort so a Redis
        #    failure never surfaces as a 500 after Council approval.
        if channel == Channel.DIGEST:
            async with best_effort("digest_enqueue"):
                await self._digest_queue.enqueue(
                    signal.affected_user_id,
                    signal,
                    str(decision.decision_id),
                )
        else:
            async with best_effort("ws_push"):
                await self._ws_pusher.push(
                    user_id=signal.affected_user_id,
                    payload={
                        "type": "signal",
                        "severity": signal.severity.value,
                        "channel": channel.value,
                        "title": signal.title,
                        "body": signal.body,
                        "actions": signal.suggested_actions,
                        "decision_id": str(decision.decision_id),
                        "explanation_url": _EXPLANATION_URL_TEMPLATE.format(
                            decision_id=decision.decision_id
                        ),
                    },
                )

        return DispatchResult(
            channel=channel,
            delivered_at=datetime.now(timezone.utc),
            user_id=signal.affected_user_id,
            budget_verdict=budget_result.verdict,
        )
