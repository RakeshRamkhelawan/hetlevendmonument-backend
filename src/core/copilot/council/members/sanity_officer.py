"""
SanityOfficer -- checks for hallucinations, refusals and LLM laziness.

Wraps HallucinationGuard (ADR-025 fundament) and adds confidence thresholding.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any, ClassVar

from src.core.copilot.council.members.base import Officer
from src.core.copilot.council.types import (
    DeliberationContext,
    OfficerVerdict,
    Proposal,
    VerdictType,
)
from src.core.learning.safety.hallucination_guard import HallucinationGuard

logger = logging.getLogger(__name__)

# ASCII-only patterns (Rule 10)
_REFUSAL_PATTERNS = re.compile(
    r"\b(I'm sorry|I cannot|As an AI|Ik kan niet|Helaas|Excuses)\b",
    re.IGNORECASE,
)


class SanityOfficer(Officer):
    """Detects hallucinations and refusals in Co-Pilot output."""

    name: ClassVar[str] = "SanityOfficer"
    version: ClassVar[str] = "1.0.0"
    timeout_ms: ClassVar[int] = 500
    can_veto: ClassVar[bool] = True
    allowed_verdicts: ClassVar[frozenset[VerdictType]] = frozenset(
        {VerdictType.APPROVE, VerdictType.VETO}
    )

    async def deliberate(
        self, proposal: Proposal, context: DeliberationContext
    ) -> OfficerVerdict:
        start_ms = time.perf_counter()
        try:
            # 1. Hallucination Check (wraps HallucinationGuard)
            # We check the message (user-facing) and reasoning (internal context)
            is_safe_msg, hall_reason = HallucinationGuard.check(
                proposal.message, proposal.context_snapshot
            )
            if not is_safe_msg:
                # ADR-036 D2-002/OP-38 (fix-sprint dag 6): `hall_reason` bevat na een
                # "absolute_claim:"/"fabricated_stat:"/"ungrounded_file_ref:"-categorie de
                # daadwerkelijk GEMATCHTE modeltekst (bv. een bestandsnaam die een persoonsnaam
                # kan bevatten). Die tekst mag niet de onuitwisbare hashketen ingaan --
                # `evidence` wordt meegehasht en NIET geredigeerd door `persist()` (dezelfde
                # bewuste keuze als voor de andere officers, zie
                # `TestTheOfficerEvidenceIsTheSideDoorOfTheSameTransaction`). Alleen de
                # CATEGORIE is toezicht-relevant (WELKE regel triggerde), niet de matched tekst
                # zelf -- zelfde principe als `ethics_officer`'s reasoning-fix (OP-95).
                hallucination_category = (hall_reason or "unknown").split(":", 1)[0]
                return self._build_verdict(
                    VerdictType.VETO,
                    "HALLUCINATION_DETECTED",
                    f"Hallucinatie gedetecteerd in AI respons: {hallucination_category}",
                    start_ms,
                    evidence={"hallucination_reason": hallucination_category},
                )

            # 2. Confidence Threshold (Decision 2)
            if proposal.confidence < 0.3:
                return self._build_verdict(
                    VerdictType.VETO,
                    "INSUFFICIENT_CONFIDENCE",
                    f"Confidence {proposal.confidence} onder drempelwaarde 0.3",
                    start_ms,
                )

            # 3. Refusal Pattern Check
            if _REFUSAL_PATTERNS.search(proposal.message):
                return self._build_verdict(
                    VerdictType.VETO,
                    "AI_REFUSAL_DETECTED",
                    "De AI weigert het verzoek uit te voeren.",
                    start_ms,
                )

            # 4. Reasoning Length Check (Decision 3)
            if len(proposal.reasoning.strip()) < 10:
                return self._build_verdict(
                    VerdictType.VETO,
                    "INSUFFICIENT_EXPLANATION",
                    "De AI heeft onvoldoende onderbouwing gegeven voor dit besluit.",
                    start_ms,
                )

            return self._build_verdict(
                VerdictType.APPROVE,
                "SANITY_OK",
                "De respons voldoet aan de integriteitschecks.",
                start_ms,
            )

        except Exception as e:
            logger.error(
                "SanityOfficer error tenant=%d user=%d: %s: %s",
                proposal.tenant_id,
                proposal.user_id,
                type(e).__name__,
                e,
                exc_info=True,
            )
            return self._build_verdict(
                VerdictType.VETO,
                "OFFICER_ERROR",
                "Interne fout bij SanityOfficer",
                start_ms,
            )

    def _build_verdict(
        self,
        verdict: VerdictType,
        reason_code: str,
        reason_text: str,
        start_ms: float,
        evidence: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> OfficerVerdict:
        return OfficerVerdict(
            officer_name=self.name,
            officer_version=self.version,
            verdict=verdict,
            reason_code=reason_code,
            reason_text=reason_text,
            evidence=evidence or {},
            deliberation_ms=int((time.perf_counter() - start_ms) * 1000),
            confidence=1.0,
        )
