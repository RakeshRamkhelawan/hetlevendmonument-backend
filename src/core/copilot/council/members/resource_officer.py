"""
Resource Officer Implementation.
Guards rate limits, Prana tokens, and Notification budget.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar

from src.core.copilot.council.cache import OfficerVerdictCache
from src.core.copilot.council.members.base import Officer
from src.core.copilot.council.types import (
    DeliberationContext,
    OfficerVerdict,
    Proposal,
    VerdictType,
)
from src.core.copilot.protocols import IRateLimiter, IPranaService
from src.core.copilot.notification.budget import BudgetVerdict, NotificationBudgetTracker
from src.core.copilot.notification.preferences_repo import UserNotificationPreferencesRepo
from src.core.observability.tracing import get_tracer

tracer = get_tracer(__name__)
logger = logging.getLogger(__name__)


class ResourceOfficer(Officer):
    name: ClassVar[str] = "ResourceOfficer"
    version: ClassVar[str] = "1.0.1"  # bump: timeout fix per ADR-027 Section 5.2.6 (2026-05-23)
    # ADR-027 Section 5.2.6 + Implementation Defaults: ResourceOfficer doet alleen
    # snelle Redis-counter checks; timeout moet 200ms zijn voor SLA-conformiteit.
    timeout_ms: ClassVar[int] = 200
    can_veto: ClassVar[bool] = False  # mag enkel APPROVE / REQUIRE_DEFERRAL / OVERRIDE_BUDGET
    allowed_verdicts: ClassVar[frozenset[VerdictType]] = frozenset(
        [VerdictType.APPROVE, VerdictType.REQUIRE_DEFERRAL, VerdictType.OVERRIDE_BUDGET]
    )
    can_cache: ClassVar[bool] = False

    def __init__(
        self,
        *,
        rate_limiter: IRateLimiter,
        prana_service: IPranaService,  # mock voor sprint 2
        budget_tracker: NotificationBudgetTracker,
        preferences_repo: UserNotificationPreferencesRepo,
        cache: OfficerVerdictCache | None = None,
    ) -> None:
        super().__init__(cache=cache)
        self._rate_limiter = rate_limiter
        self._prana = prana_service
        self._budget = budget_tracker
        self._prefs_repo = preferences_repo

    def _build_defer(self, proposal: Proposal, reason_code: str) -> OfficerVerdict:
        """Helper to build a DEFER verdict."""
        return OfficerVerdict(
            officer_name=self.name,
            officer_version=self.version,
            verdict=VerdictType.REQUIRE_DEFERRAL,
            confidence=1.0,
            reason_code=reason_code,
            reason_text=f"Deferred due to {reason_code}.",
            evidence={},
            deliberation_ms=0,
        )

    async def deliberate(
        self,
        proposal: Proposal,
        context: DeliberationContext,
    ) -> OfficerVerdict:
        with tracer.start_as_current_span(
            f"copilot.officer.{self.name}.deliberate"
        ) as span:
            span.set_attribute("tenant_id", proposal.tenant_id)
            span.set_attribute("action_type", proposal.action_type)
            verdict = await self._deliberate_inner(proposal, context)
            span.set_attribute("verdict", verdict.verdict.value)
            span.set_attribute("reason_code", verdict.reason_code)
            return verdict

    async def _deliberate_inner(
        self,
        proposal: Proposal,
        context: DeliberationContext,
    ) -> OfficerVerdict:
        try:
            # 1. Rate limit check
            rate_ok = await self._rate_limiter.check(
                tenant_id=proposal.tenant_id,
                user_id=proposal.user_id,
                action_type=proposal.action_type,
            )
            if not rate_ok:
                return self._build_defer(proposal, "RATE_LIMIT_EXCEEDED")

            # 2. Prana mock
            prana_ok = await self._prana.has_budget(proposal.tenant_id, proposal.action_type)
            if not prana_ok:
                return self._build_defer(proposal, "PRANA_BUDGET_EMPTY")

            # 3. Notification budget - alleen voor PROACTIVE_MONITOR trigger
            if (
                proposal.trigger == "proactive_monitor"
            ):  # Assuming ProposalTrigger.PROACTIVE_MONITOR
                prefs = await self._prefs_repo.get_for_user(
                    user_id=proposal.user_id,
                    tenant_id=proposal.tenant_id,
                )

                # Default to "normal" severity if not provided in context snapshot
                severity = (
                    proposal.context_snapshot.get("severity", "normal")
                    if proposal.context_snapshot
                    else "normal"
                )

                result = await self._budget.consume(
                    tenant_id=proposal.tenant_id,
                    user_id=proposal.user_id,
                    prefs=prefs,
                    severity=severity,
                )
                if result.verdict == BudgetVerdict.DEFERRED:
                    return self._build_defer(proposal, result.reason)
                if result.verdict == BudgetVerdict.OVERRIDE:
                    return OfficerVerdict(
                        officer_name=self.name,
                        officer_version=self.version,
                        verdict=VerdictType.OVERRIDE_BUDGET,
                        confidence=1.0,
                        reason_code="CRITICAL_BYPASS",
                        reason_text="Critical severity overrides daily budget.",
                        evidence={"budget_remaining": result.remaining},
                        deliberation_ms=0,
                    )

            # 4. All checks passed
            return OfficerVerdict(
                officer_name=self.name,
                officer_version=self.version,
                verdict=VerdictType.APPROVE,
                confidence=0.95,
                reason_code="ALL_BUDGETS_OK",
                reason_text="Rate limit, Prana en notification budget binnen limiet.",
                evidence={},
                deliberation_ms=0,
            )
        except Exception as e:
            logger.error(
                "ResourceOfficer deliberation failed: %s: %s",
                type(e).__name__,
                e,
                exc_info=True,
                extra={"tenant_id": proposal.tenant_id, "user_id": proposal.user_id},
            )
            # Fail-secure: bij interne fout defer i.p.v. blocking
            return self._build_defer(proposal, "OFFICER_INTERNAL_ERROR")

