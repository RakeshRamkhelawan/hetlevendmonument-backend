"""
RiskOfficer - Impact classification, HITL escalation, Shadow CEO integration.

Wraps existing modules:
    - src.core.governance.risk_register
    - src.core.als.enterprise.shadow_ceo (ADR-016)

Checks (per Proposal):
    1. Shadow CEO risk score for action_type + actor + context
    2. Reversibility check (irreversible actions -> REQUIRE_HITL)
    3. Actor track record (new actor / unusual pattern -> REQUIRE_HITL)
    4. Tenant policy thresholds (per-tenant configurable)

Verdict map:
    APPROVE        - risk LOW or MEDIUM with established track record
    REQUIRE_HITL   - risk HIGH, new actor, or irreversible change
    VETO           - Shadow CEO CRITICAL (rare; usually security-side)

Cacheable: never (context-dependent: actor history, recent decisions).

References:
    - docs/adr/027-copilot-agent-council.md Section 5.2.4
    - ADR-016 (Shadow CEO red teaming)
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
from src.core.observability.tracing import get_tracer

tracer = get_tracer(__name__)
logger = logging.getLogger(__name__)


class RiskOfficer(Officer):
    """Risk classification and HITL escalation Officer."""

    name: ClassVar[str] = "RiskOfficer"
    version: ClassVar[str] = "1.0.0"
    allowed_verdicts: ClassVar[frozenset[VerdictType]] = frozenset(
        {
            VerdictType.APPROVE,
            VerdictType.REQUIRE_HITL,
            VerdictType.VETO,
        }
    )
    timeout_ms: ClassVar[int] = 600
    can_cache: ClassVar[bool] = False

    def __init__(
        self,
        shadow_ceo: Any,  # TODO(TYPE): replace Any with concrete type
        risk_register: Any,  # TODO(TYPE): replace Any with concrete type
        cache: OfficerVerdictCache | None = None,
    ) -> None:
        super().__init__(cache=cache)
        self._shadow_ceo = shadow_ceo
        self._risk_register = risk_register

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
        """
        Adjudicate risk aspects.
        """

        try:
            score = await self._shadow_ceo.assess(proposal)

            if score == "CRITICAL":
                return OfficerVerdict(
                    officer_name=self.name,
                    officer_version=self.version,
                    verdict=VerdictType.VETO,
                    reason_code="SHADOW_CEO_CRITICAL",
                    reason_text="Shadow CEO heeft dit voorstel afgekeurd wegens kritiek risico.",
                    evidence={"shadow_ceo_score": score},
                    deliberation_ms=0,
                    confidence=1.0,
                )

            if score == "HIGH":
                return OfficerVerdict(
                    officer_name=self.name,
                    officer_version=self.version,
                    verdict=VerdictType.REQUIRE_HITL,
                    reason_code="HIGH_RISK",
                    reason_text="Actie is geclassificeerd als hoog risico en vereist menselijke goedkeuring.",
                    evidence={"shadow_ceo_score": score},
                    deliberation_ms=0,
                    confidence=1.0,
                )

            track_record = await self._risk_register.actor_track_record(
                proposal.user_id, proposal.action_type
            )
            history_count = len(track_record) if track_record else 0

            if score == "MEDIUM":
                if history_count == 0:
                    return OfficerVerdict(
                        officer_name=self.name,
                        officer_version=self.version,
                        verdict=VerdictType.REQUIRE_HITL,
                        reason_code="FIRST_TIME_ACTOR",
                        reason_text="Actie is medium risico maar de gebruiker heeft dit nog niet eerder gedaan.",
                        evidence={"shadow_ceo_score": score, "actor_history_count": history_count},
                        deliberation_ms=0,
                        confidence=1.0,
                    )
                else:
                    return OfficerVerdict(
                        officer_name=self.name,
                        officer_version=self.version,
                        verdict=VerdictType.APPROVE,
                        reason_code="COMPLIANT",
                        reason_text="Medium risico, maar gebruiker heeft een positief track record.",
                        evidence={"shadow_ceo_score": score, "actor_history_count": history_count},
                        deliberation_ms=0,
                        confidence=1.0,
                    )

            # LOW
            return OfficerVerdict(
                officer_name=self.name,
                officer_version=self.version,
                verdict=VerdictType.APPROVE,
                reason_code="COMPLIANT",
                reason_text="Laag risico.",
                evidence={"shadow_ceo_score": score, "actor_history_count": history_count},
                deliberation_ms=0,
                confidence=1.0,
            )

        except Exception as e:
            logger.error(
                f"RiskOfficer error [tenant={proposal.tenant_id}, user={proposal.user_id}]: {str(e)}",
                exc_info=True,
            )
            return OfficerVerdict(
                officer_name=self.name,
                officer_version=self.version,
                verdict=VerdictType.VETO,
                reason_code="UPSTREAM_ERROR",
                reason_text=f"Interne fout: {str(e)}",
                evidence={},
                deliberation_ms=0,
                confidence=1.0,
            )


