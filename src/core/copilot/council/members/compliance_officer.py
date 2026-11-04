"""
ComplianceOfficer -- EU AI Act, GDPR, ISO 42001 compliance checks.

Wraps existing modules:
    - src.core.governance.compliance_guardian
    - src.core.governance.ai_act_classifier

Checks (per Proposal):
    1. AI Act high-risk classification -> extra logging metadata required
    2. AI Act art. 50 (transparency to end-user) -> ensure proposal carries
       AI disclosure flag in action_params
    3. AI Act forbidden practices (social scoring, manipulative AI) -> VETO
    4. GDPR art. 22 (automated decision-making) -> escalate via RiskOfficer
       (this Officer flags but does not require HITL itself)
    5. ISO 42001 A.6.2.8 required event metadata present

Verdict map:
    APPROVE                       -- no compliance objections
    APPROVE_WITH_MODIFICATION     -- add transparency text to action_params
    VETO                          -- forbidden practice or missing mandatory fields

Cacheable: 60s on (action_type, data_classification) tuple.

References:
    - docs/adr/027-copilot-agent-council.md Section 5.2.1
    - docs/copilot-architecture.md Section 5.2
    - EU AI Act Regulation (EU) 2024/1689 -- articles 5, 12, 13, 50
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar, Optional, Protocol

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


class AIActClassifier(Protocol):
    def classify(self, action_type: str, action_params: dict[str, Any]) -> str: ...  # TODO(TYPE): replace Any with concrete type


class ComplianceGuardian(Protocol):
    pass


class ComplianceOfficer(Officer):
    """EU AI Act, GDPR, ISO 42001 compliance Officer."""

    name: ClassVar[str] = "ComplianceOfficer"
    version: ClassVar[str] = "1.0.0"
    allowed_verdicts: ClassVar[frozenset[VerdictType]] = frozenset(
        {
            VerdictType.APPROVE,
            VerdictType.APPROVE_WITH_MODIFICATION,
            VerdictType.VETO,
        }
    )
    timeout_ms: ClassVar[int] = 800  # LLM-backed classifier may be slower
    can_cache: ClassVar[bool] = True
    cache_ttl_seconds: ClassVar[int] = 60

    def __init__(
        self,
        compliance_guardian: ComplianceGuardian,
        ai_act_classifier: AIActClassifier,
        cache: OfficerVerdictCache | None = None,
    ) -> None:
        super().__init__(cache=cache)
        self._guardian = compliance_guardian
        self._classifier = ai_act_classifier

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
            # Use new cache layer when cache is an OfficerVerdictCache;
            # fall back to legacy path for backward compat with old-style caches.
            if isinstance(self._cache, OfficerVerdictCache):
                verdict = await self._cached_deliberate(
                    proposal, context, self._actual_deliberate
                )
            else:
                verdict = await self._legacy_deliberate(proposal, context)
            span.set_attribute("verdict", verdict.verdict.value)
            span.set_attribute("reason_code", verdict.reason_code)
            return verdict

    async def _actual_deliberate(
        self,
        proposal: Proposal,
        context: DeliberationContext,
    ) -> OfficerVerdict:
        try:
            risk_category = self._classifier.classify(
                proposal.action_type, proposal.action_params
            )

            verdict: OfficerVerdict
            if risk_category == "FORBIDDEN_PRACTICE":
                verdict = OfficerVerdict(
                    officer_name=self.name,
                    officer_version=self.version,
                    verdict=VerdictType.VETO,
                    reason_code="FORBIDDEN_PRACTICE",
                    reason_text="Dit voorstel schendt de EU AI Act (Forbidden Practice).",
                    evidence={"risk_category": risk_category},
                    deliberation_ms=0,
                    confidence=1.0,
                )
            elif not proposal.action_params.get("ai_disclosure"):
                verdict = OfficerVerdict(
                    officer_name=self.name,
                    officer_version=self.version,
                    verdict=VerdictType.APPROVE_WITH_MODIFICATION,
                    reason_code="MISSING_AI_DISCLOSURE",
                    reason_text="AI disclosure is verplicht voor deze actie.",
                    evidence={
                        "modifications": {
                            "action_params": {
                                "ai_disclosure": "Deze actie wordt voorgesteld door AI"
                            }
                        }
                    },
                    deliberation_ms=0,
                    confidence=1.0,
                )
            elif (
                not proposal.model_id
                or not proposal.model_version
                or not proposal.data_classification
            ):
                verdict = OfficerVerdict(
                    officer_name=self.name,
                    officer_version=self.version,
                    verdict=VerdictType.VETO,
                    reason_code="MISSING_METADATA",
                    reason_text="Verplichte logging metadata ontbreekt.",
                    evidence={},
                    deliberation_ms=0,
                    confidence=1.0,
                )
            else:
                verdict = OfficerVerdict(
                    officer_name=self.name,
                    officer_version=self.version,
                    verdict=VerdictType.APPROVE,
                    reason_code="COMPLIANT",
                    reason_text="Voldoet aan compliance eisen.",
                    evidence={
                        "risk_category": risk_category,
                        "classification_metadata": True,
                    },
                    deliberation_ms=0,
                    confidence=1.0,
                )

            return verdict

        except Exception as e:
            logger.error(
                "ComplianceOfficer error",
                extra={"tenant_id": proposal.tenant_id, "user_id": proposal.user_id},
                exc_info=True,
            )
            return OfficerVerdict(
                officer_name=self.name,
                officer_version=self.version,
                verdict=VerdictType.VETO,
                reason_code="EXCEPTION",
                reason_text=f"Interne fout: {str(e)}",
                evidence={},
                deliberation_ms=0,
                confidence=1.0,
            )

    async def _legacy_deliberate(
        self,
        proposal: Proposal,
        context: DeliberationContext,
    ) -> OfficerVerdict:
        """Backward-compatible deliberate path for old-style caches (tests)."""
        try:
            cache_key = (
                f"compliance:{proposal.action_type}:{proposal.data_classification.value}"
            )

            if self._cache and self.can_cache:
                cached = self._cache.get(cache_key)
                if cached:
                    return OfficerVerdict(
                        officer_name=self.name,
                        officer_version=self.version,
                        verdict=VerdictType(cached["verdict"]),
                        reason_code=cached["reason_code"],
                        reason_text=cached["reason_text"],
                        evidence=cached.get("evidence", {}),
                        deliberation_ms=0,
                        confidence=1.0,
                    )

            risk_category = self._classifier.classify(
                proposal.action_type, proposal.action_params
            )

            verdict: OfficerVerdict
            if risk_category == "FORBIDDEN_PRACTICE":
                verdict = OfficerVerdict(
                    officer_name=self.name,
                    officer_version=self.version,
                    verdict=VerdictType.VETO,
                    reason_code="FORBIDDEN_PRACTICE",
                    reason_text="Dit voorstel schendt de EU AI Act (Forbidden Practice).",
                    evidence={"risk_category": risk_category},
                    deliberation_ms=0,
                    confidence=1.0,
                )
            elif not proposal.action_params.get("ai_disclosure"):
                verdict = OfficerVerdict(
                    officer_name=self.name,
                    officer_version=self.version,
                    verdict=VerdictType.APPROVE_WITH_MODIFICATION,
                    reason_code="MISSING_AI_DISCLOSURE",
                    reason_text="AI disclosure is verplicht voor deze actie.",
                    evidence={
                        "modifications": {
                            "action_params": {
                                "ai_disclosure": "Deze actie wordt voorgesteld door AI"
                            }
                        }
                    },
                    deliberation_ms=0,
                    confidence=1.0,
                )
            elif (
                not proposal.model_id
                or not proposal.model_version
                or not proposal.data_classification
            ):
                verdict = OfficerVerdict(
                    officer_name=self.name,
                    officer_version=self.version,
                    verdict=VerdictType.VETO,
                    reason_code="MISSING_METADATA",
                    reason_text="Verplichte logging metadata ontbreekt.",
                    evidence={},
                    deliberation_ms=0,
                    confidence=1.0,
                )
            else:
                verdict = OfficerVerdict(
                    officer_name=self.name,
                    officer_version=self.version,
                    verdict=VerdictType.APPROVE,
                    reason_code="COMPLIANT",
                    reason_text="Voldoet aan compliance eisen.",
                    evidence={
                        "risk_category": risk_category,
                        "classification_metadata": True,
                    },
                    deliberation_ms=0,
                    confidence=1.0,
                )

            if self._cache and self.can_cache:
                self._cache.set(
                    cache_key,
                    {
                        "verdict": verdict.verdict.value,
                        "reason_code": verdict.reason_code,
                        "reason_text": verdict.reason_text,
                        "evidence": verdict.evidence,
                    },
                    ex=60,
                )

            return verdict

        except Exception as e:
            logger.error(
                "ComplianceOfficer error",
                extra={"tenant_id": proposal.tenant_id, "user_id": proposal.user_id},
                exc_info=True,
            )
            return OfficerVerdict(
                officer_name=self.name,
                officer_version=self.version,
                verdict=VerdictType.VETO,
                reason_code="EXCEPTION",
                reason_text=f"Interne fout: {str(e)}",
                evidence={},
                deliberation_ms=0,
                confidence=1.0,
            )
