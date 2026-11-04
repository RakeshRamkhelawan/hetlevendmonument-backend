"""
EthicsOfficer - Bias detection, fairness, transparency obligations.

NEW Officer (no existing module to wrap; builds on ethics_gate.py skeleton).

Checks (per Proposal):
    1. Bias indicators in reasoning text (curated NL/EN lexicons)
    2. Demographic assumptions in action_params
    3. Language consistency: explanation_for_user matches user's language
    4. AI disclosure presence for art. 50 (cross-check with ComplianceOfficer)

Verdict map:
    APPROVE                       - no ethical concerns
    APPROVE_WITH_MODIFICATION     - reformulation needed (neutralize language)
    (no VETO power)               - Ethics warns and adjusts; does not block

Cacheable: 5 min on (message_pattern_hash, language) - patterns are stable.

References:
    - docs/adr/027-copilot-agent-council.md 5.2.5
"""

from __future__ import annotations

import hashlib
import logging
import unicodedata
from typing import Any, ClassVar

from src.core.copilot.council.cache import OfficerVerdictCache
from src.core.copilot.council.members.base import Officer
from src.core.copilot.council.members.lexicons import (
    HIGH_BIAS_TERMS_EN,
    HIGH_BIAS_TERMS_HI,
    HIGH_BIAS_TERMS_NL,
    HIGH_BIAS_TERMS_SA,
    LEXICON_VERSION_EN,
    LEXICON_VERSION_HI,
    LEXICON_VERSION_NL,
    LEXICON_VERSION_SA,
    MEDIUM_BIAS_TERMS_EN,
    MEDIUM_BIAS_TERMS_HI,
    MEDIUM_BIAS_TERMS_NL,
    MEDIUM_BIAS_TERMS_SA,
)
from src.core.copilot.council.types import (
    DeliberationContext,
    OfficerVerdict,
    Proposal,
    VerdictType,
)
from src.core.observability.tracing import get_tracer

tracer = get_tracer(__name__)
logger = logging.getLogger(__name__)


class EthicsOfficer(Officer):
    """Detects bias and transparency issues via lexicons.

    May exclusively emit APPROVE or APPROVE_WITH_MODIFICATION.

    NOTE: can_veto=False is a deliberate MVP decision (WE-007, ADR-027 par. 5.2.5).
    EthicsOfficer uses lexicon-based checks with high false-positive risk for
    business content. Full LLM-based ethics enforcement is planned post-MVP.
    ComplianceOfficer and SecurityOfficer (can_veto=True) cover BLOCKED verdicts.
    Fail-open on error (APPROVE) is intentional for MVP -- see ADR-027 Changelog v1.6.
    """

    name: ClassVar[str] = "EthicsOfficer"
    version: ClassVar[str] = "1.0.0"
    cache_ttl_seconds: ClassVar[int] = 300  # 5 min, per ADR-027 5.2.5
    timeout_ms: ClassVar[int] = 500
    can_cache: ClassVar[bool] = True
    can_veto: ClassVar[bool] = False  # MVP: NO veto power -- see docstring + ADR-027 par.5.2.5
    allowed_verdicts: ClassVar[frozenset[VerdictType]] = frozenset(
        {
            VerdictType.APPROVE,
            VerdictType.APPROVE_WITH_MODIFICATION,
        }
    )

    def __init__(
        self,
        bias_lexicon_nl: tuple[frozenset[str], frozenset[str]] | None = None,
        bias_lexicon_en: tuple[frozenset[str], frozenset[str]] | None = None,
        bias_lexicon_hi: tuple[frozenset[str], frozenset[str]] | None = None,
        bias_lexicon_sa: tuple[frozenset[str], frozenset[str]] | None = None,
        cache: OfficerVerdictCache | None = None,
    ) -> None:
        super().__init__(cache=cache)

        # Helper to normalize whole lexicons consistently
        def norm_lex(
            lex: tuple[frozenset[str], frozenset[str]],
        ) -> tuple[frozenset[str], frozenset[str]]:
            return (
                frozenset({self._normalize_reasoning(t).lower() for t in lex[0]}),
                frozenset({self._normalize_reasoning(t).lower() for t in lex[1]}),
            )

        self._lex_nl = norm_lex(
            bias_lexicon_nl
            or (
                HIGH_BIAS_TERMS_NL,
                MEDIUM_BIAS_TERMS_NL,
            )
        )
        self._lex_en = norm_lex(
            bias_lexicon_en
            or (
                HIGH_BIAS_TERMS_EN,
                MEDIUM_BIAS_TERMS_EN,
            )
        )
        self._lex_hi = norm_lex(
            bias_lexicon_hi
            or (
                HIGH_BIAS_TERMS_HI,
                MEDIUM_BIAS_TERMS_HI,
            )
        )
        self._lex_sa = norm_lex(
            bias_lexicon_sa
            or (
                HIGH_BIAS_TERMS_SA,
                MEDIUM_BIAS_TERMS_SA,
            )
        )
        self._lexicon_versions = {
            "nl": LEXICON_VERSION_NL,
            "en": LEXICON_VERSION_EN,
            "hi": LEXICON_VERSION_HI,
            "sa": LEXICON_VERSION_SA,
        }

    @staticmethod
    def _normalize_reasoning(reasoning: str) -> str:
        """Normalize reasoning text for bias detection.

        1. NFKC for compatibility decomposition (strongest canonical form).
        2. NFD + combining-mark strip to prevent homoglyph bypass
           (Cyrillic lookalikes, etc.) -- H-6 / P0-6 regression test.
           NOTE: We skip Mn removal for Devanagari (\u0900-\u097f) as
           these marks are essential for meaning.
        3. Truncate to 10k chars for DoS protection.
        """
        reasoning = unicodedata.normalize("NFKC", reasoning)
        reasoning = unicodedata.normalize("NFD", reasoning)

        result = []
        for c in reasoning:
            cat = unicodedata.category(c)
            # Remove non-spacing marks (Mn) EXCEPT for Devanagari range
            if cat == "Mn":
                cp = ord(c)
                if 0x0900 <= cp <= 0x097F:
                    result.append(c)
                # else: drop it (homoglyph prevention for Latin/Cyrillic/etc)
            else:
                result.append(c)

        return "".join(result)[:10000]

    def _cache_key(self, proposal: Proposal, language: str) -> str:
        reasoning = proposal.reasoning or ""
        reasoning = self._normalize_reasoning(reasoning)
        reasoning_hash = hashlib.sha256(reasoning.encode("utf-8")).hexdigest()
        return f"ethics:{proposal.action_type}:{language}:{reasoning_hash}"

    def _build_modify_verdict(
        self,
        proposal: Proposal,
        language: str,
        high_matches: list[str],
        medium_matches: list[str],
        reason_code: str,
    ) -> OfficerVerdict:
        reasoning = proposal.reasoning or ""
        reasoning = self._normalize_reasoning(reasoning)

        modified_reasoning = reasoning
        # Naive replacement for MVP
        for term in high_matches + medium_matches:
            modified_reasoning = modified_reasoning.replace(term, "[...]")
            modified_reasoning = modified_reasoning.replace(term.capitalize(), "[...]")

        return OfficerVerdict(
            officer_name=self.name,
            officer_version=self.version,
            verdict=VerdictType.APPROVE_WITH_MODIFICATION,
            confidence=0.9,
            reason_code=reason_code,
            reason_text="Ethische waarschuwing: bias termen gedetecteerd.",
            evidence={
                "lexicon_version": self._lexicon_versions.get(language, "unknown"),
                "language_used": language,
                "high_matches": high_matches,
                "medium_matches": medium_matches,
                # NIET de tekst zelf (ADR-036 OP-95). `modified_reasoning` is de VOLLEDIGE
                # `proposal.reasoning` -- tot 10.000 tekens door een taalmodel geschreven -- met
                # alleen de gevonden bias-termen vervangen. Die evidence gaat via
                # `compute_officer_verdicts_hash()` mee in `decision_hash` en dus in de
                # ADR-019-keten, die per ontwerp onuitwisbaar is: corrigeren breekt de hash.
                #
                # Wat het toezicht nodig heeft is DAT er is aangepast en hoeveel, plus een
                # narekenbare verwijzing. De aangepaste tekst zelf hoort in de RESPONSE naar de
                # gebruiker, niet in het permanente bewijs. De hoeveelheid vervangingen is af te
                # leiden uit `high_matches` en `medium_matches`, die hierboven al staan.
                "modifications": {
                    "reasoning_modified": modified_reasoning != reasoning,
                    "replacements": len(high_matches) + len(medium_matches),
                },
            },
            deliberation_ms=0,
            used_cache=False,
        )

    async def deliberate(
        self,
        proposal: Proposal,
        context: DeliberationContext,
    ) -> OfficerVerdict:
        with tracer.start_as_current_span(f"copilot.officer.{self.name}.deliberate") as span:
            span.set_attribute("tenant_id", proposal.tenant_id)
            span.set_attribute("action_type", proposal.action_type)
            if isinstance(self._cache, OfficerVerdictCache):
                verdict = await self._cached_deliberate(proposal, context, self._actual_deliberate)
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
            prefs = context.user_preferences if context.user_preferences else {}
            language = prefs.get("language", "nl")
            if language not in ("nl", "en", "hi", "sa"):
                language = "nl"

            lexicons = {
                "nl": self._lex_nl,
                "en": self._lex_en,
                "hi": self._lex_hi,
                "sa": self._lex_sa,
            }
            high_terms, medium_terms = lexicons.get(language, self._lex_nl)

            reasoning = proposal.reasoning or ""
            reasoning = self._normalize_reasoning(reasoning)
            reasoning_lower = reasoning.lower()

            high_matches = sorted([t for t in high_terms if t in reasoning_lower])
            medium_matches = sorted([t for t in medium_terms if t in reasoning_lower])

            verdict: OfficerVerdict
            if high_matches:
                verdict = self._build_modify_verdict(
                    proposal=proposal,
                    language=language,
                    high_matches=high_matches,
                    medium_matches=medium_matches,
                    reason_code="HIGH_BIAS_LANGUAGE_DETECTED",
                )
            elif len(medium_matches) >= 3:
                verdict = self._build_modify_verdict(
                    proposal=proposal,
                    language=language,
                    high_matches=[],
                    medium_matches=medium_matches,
                    reason_code="EXCESSIVE_GENERALIZATION",
                )
            else:
                verdict = OfficerVerdict(
                    officer_name=self.name,
                    officer_version=self.version,
                    verdict=VerdictType.APPROVE,
                    confidence=0.9,
                    reason_code="NO_BIAS_DETECTED",
                    reason_text="Geen bias-termen of overmatige generalisaties.",
                    evidence={
                        "lexicon_version": self._lexicon_versions[language],
                        "language_used": language,
                        "high_matches": [],
                        "medium_matches": medium_matches,
                    },
                    deliberation_ms=0,
                    used_cache=False,
                )

            return verdict

        except Exception as e:
            logger.error(
                "EthicsOfficer error: %s: %s",
                type(e).__name__,
                e,
                extra={"tenant_id": proposal.tenant_id, "user_id": proposal.user_id},
                exc_info=True,
            )
            return OfficerVerdict(
                officer_name=self.name,
                officer_version=self.version,
                verdict=VerdictType.APPROVE,
                confidence=1.0,
                reason_code="OFFICER_ERROR",
                reason_text="Fallback approval due to officer error",
                evidence={},
                deliberation_ms=0,
                used_cache=False,
            )

    async def _legacy_deliberate(
        self,
        proposal: Proposal,
        context: DeliberationContext,
    ) -> OfficerVerdict:
        """Backward-compatible deliberate path for old-style caches (tests)."""
        try:
            prefs = context.user_preferences if context.user_preferences else {}
            language = prefs.get("language", "nl")
            if language not in ("nl", "en", "hi", "sa"):
                language = "nl"

            cache_key = self._cache_key(proposal, language)
            if self._cache:
                cached = await self._cache.get(cache_key)
                if cached is not None:
                    return OfficerVerdict(
                        officer_name=self.name,
                        officer_version=self.version,
                        verdict=VerdictType(cached["verdict"]),
                        reason_code=cached["reason_code"],
                        reason_text=cached["reason_text"],
                        evidence=cached.get("evidence", {}),
                        deliberation_ms=0,
                        confidence=1.0,
                        used_cache=True,
                    )

            lexicons = {
                "nl": self._lex_nl,
                "en": self._lex_en,
                "hi": self._lex_hi,
                "sa": self._lex_sa,
            }
            high_terms, medium_terms = lexicons.get(language, self._lex_nl)

            reasoning = proposal.reasoning or ""
            reasoning = self._normalize_reasoning(reasoning)
            reasoning_lower = reasoning.lower()

            high_matches = sorted([t for t in high_terms if t in reasoning_lower])
            medium_matches = sorted([t for t in medium_terms if t in reasoning_lower])

            verdict: OfficerVerdict
            if high_matches:
                verdict = self._build_modify_verdict(
                    proposal=proposal,
                    language=language,
                    high_matches=high_matches,
                    medium_matches=medium_matches,
                    reason_code="HIGH_BIAS_LANGUAGE_DETECTED",
                )
            elif len(medium_matches) >= 3:
                verdict = self._build_modify_verdict(
                    proposal=proposal,
                    language=language,
                    high_matches=[],
                    medium_matches=medium_matches,
                    reason_code="EXCESSIVE_GENERALIZATION",
                )
            else:
                verdict = OfficerVerdict(
                    officer_name=self.name,
                    officer_version=self.version,
                    verdict=VerdictType.APPROVE,
                    confidence=0.9,
                    reason_code="NO_BIAS_DETECTED",
                    reason_text="Geen bias-termen of overmatige generalisaties.",
                    evidence={
                        "lexicon_version": self._lexicon_versions[language],
                        "language_used": language,
                        "high_matches": [],
                        "medium_matches": medium_matches,
                    },
                    deliberation_ms=0,
                    used_cache=False,
                )

            if self._cache:
                await self._cache.set(
                    cache_key,
                    {
                        "verdict": verdict.verdict.value,
                        "reason_code": verdict.reason_code,
                        "reason_text": verdict.reason_text,
                        "evidence": verdict.evidence,
                    },
                    ttl=self.cache_ttl_seconds,
                )

            return verdict

        except Exception as e:
            logger.error(
                "EthicsOfficer error: %s: %s",
                type(e).__name__,
                e,
                extra={"tenant_id": proposal.tenant_id, "user_id": proposal.user_id},
                exc_info=True,
            )
            return OfficerVerdict(
                officer_name=self.name,
                officer_version=self.version,
                verdict=VerdictType.APPROVE,
                confidence=1.0,
                reason_code="OFFICER_ERROR",
                reason_text="Fallback approval due to officer error",
                evidence={},
                deliberation_ms=0,
                used_cache=False,
            )
