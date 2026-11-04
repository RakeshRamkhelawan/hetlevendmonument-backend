"""
SecurityOfficer -- Tool allowlist, prompt injection, and scope validation.

Wraps existing modules:
    - src.core.als.tool_broker (ADR-015)
    - src.core.copilot.security.prompt_guard (ADR-015 P0-6)
    - src.core.auth.rbac (scope/role validation)

Checks (per Proposal):
    1. action_type must be in ToolBroker allowlist for this user+tenant
    2. proposal.reasoning + action_params screened by PromptGuard
       (Unicode normalization, homoglyph stripping, injection patterns)
    3. User has required scopes for action_type (RBAC)
    4. High-risk tools (DELETE_*, ADMIN_*) -> REQUIRE_HITL

Verdict map:
    APPROVE        -- all checks pass
    REQUIRE_HITL   -- high-risk tool detected
    VETO           -- tool not in allowlist, injection detected, missing scope

Cacheable: 60s on (action_type, user_role) -- invalidated on scope changes.

References:
    - docs/adr/027-copilot-agent-council.md Section 5.2.3
    - ADR-015 (ToolBroker allowlist + audit)
"""

from __future__ import annotations

import json
import logging
import unicodedata
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


# High-risk action patterns. Always escalate to HITL.
HIGH_RISK_ACTION_PREFIXES: frozenset[str] = frozenset(
    {
        "delete_",
        "purge_",
        "admin_",
        "grant_role",
        "revoke_role",
        "export_all",
        "bulk_",
    }
)

# Homoglyph mapping: Cyrillic + Greek lookalikes that evade naive pattern matching.
# Per P0-6 (ADR-015): NFD + combining-mark strip + homoglyph map BEFORE PromptGuard.
_HOMOGLYPH_MAP: dict[int, str] = {
    0x0430: "a",  # Cyrillic \u0430 (U+0430)
    0x0435: "e",  # Cyrillic \u0435 (U+0435)
    0x043E: "o",  # Cyrillic \u043e (U+043E)
    0x0440: "p",  # Cyrillic \u0440 (U+0440)
    0x0441: "c",  # Cyrillic \u0441 (U+0441)
    0x0445: "x",  # Cyrillic \u0445 (U+0445)
    0x0456: "i",  # Cyrillic \u0456 (U+0456)
    0x0458: "j",  # Cyrillic \u0458 (U+0458)
    0x03B1: "a",  # Greek \u03b1 (U+03B1)
    0x03BF: "o",  # Greek \u03bf (U+03BF)
    0x03C1: "p",  # Greek \u03c1 (U+03C1)
    0x03B5: "e",  # Greek \u03b5 (U+03B5)
}


def _normalize_for_guard(text: str) -> str:
    """Normalize text BEFORE PromptGuard scan.

    Steps (per P0-6 / CLAUDE.md):
    1. NFKC compatibility decomposition.
    2. NFD + strip combining marks (Mn) to prevent homoglyph bypass.
    3. Replace known Cyrillic/Greek lookalikes with ASCII equivalents.
    """
    text = unicodedata.normalize("NFKC", text)
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return text.translate(_HOMOGLYPH_MAP)


class SecurityOfficer(Officer):
    """Tool allowlist, prompt injection, and scope Officer."""

    name: ClassVar[str] = "SecurityOfficer"
    version: ClassVar[str] = "1.0.0"
    allowed_verdicts: ClassVar[frozenset[VerdictType]] = frozenset(
        {
            VerdictType.APPROVE,
            VerdictType.REQUIRE_HITL,
            VerdictType.VETO,
        }
    )
    timeout_ms: ClassVar[int] = 300
    can_cache: ClassVar[bool] = True
    cache_ttl_seconds: ClassVar[int] = 60

    def __init__(
        self,
        tool_broker: Any,  # TODO(TYPE): replace Any with concrete type
        prompt_guard: Any,  # TODO(TYPE): replace Any with concrete type
        rbac_checker: Any,  # TODO(TYPE): replace Any with concrete type
        cache: OfficerVerdictCache | None = None,
    ) -> None:
        super().__init__(cache=cache)
        self._tool_broker = tool_broker
        self._prompt_guard = prompt_guard
        self._rbac_checker = rbac_checker

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
        """
        Adjudicate security aspects.
        """
        try:
            # 1. PromptGuard scan
            input_text = proposal.reasoning + " " + json.dumps(proposal.action_params)

            # Normalize and strip homoglyphs before scanning per CLAUDE.md
            normalized_text = _normalize_for_guard(input_text)

            guard_result = self._prompt_guard.scan(normalized_text)
            if guard_result.get("injection_detected"):
                return OfficerVerdict(
                    officer_name=self.name,
                    officer_version=self.version,
                    verdict=VerdictType.VETO,
                    reason_code="PROMPT_INJECTION",
                    reason_text="Mogelijke prompt injection of onveilige input gedetecteerd.",
                    evidence={"patterns": guard_result.get("patterns", [])},
                    deliberation_ms=0,
                    confidence=1.0,
                )

            # 2. Tool allowlist check
            if not await self._tool_broker.is_allowed(
                proposal.action_type, proposal.tenant_id, proposal.user_id
            ):
                return OfficerVerdict(
                    officer_name=self.name,
                    officer_version=self.version,
                    verdict=VerdictType.VETO,
                    reason_code="TOOL_NOT_ALLOWLISTED",
                    reason_text=f"Actie '{proposal.action_type}' is niet toegestaan voor deze gebruiker.",
                    evidence={},
                    deliberation_ms=0,
                    confidence=1.0,
                )

            # 3. RBAC scope check
            # `tenant_id` expliciet uit het VOORSTEL en niet uit de tenant-ContextVar: die is
            # ambient en hoort in een Dramatiq-worker of een geneste aanroep niet gegarandeerd
            # bij dit voorstel. Een autorisatie-antwoord mag daar niet van afhangen
            # (SP-COUNCIL-GATE-001, Gate 2-review H2).
            if not await self._rbac_checker.user_has_scope_for(
                proposal.user_id, proposal.action_type, tenant_id=proposal.tenant_id
            ):
                return OfficerVerdict(
                    officer_name=self.name,
                    officer_version=self.version,
                    verdict=VerdictType.VETO,
                    reason_code="MISSING_SCOPE",
                    reason_text="Onvoldoende RBAC rechten voor deze actie.",
                    evidence={},
                    deliberation_ms=0,
                    confidence=1.0,
                )

            # 4. High-risk prefix check
            if any(
                proposal.action_type.startswith(prefix)
                for prefix in HIGH_RISK_ACTION_PREFIXES
            ):
                return OfficerVerdict(
                    officer_name=self.name,
                    officer_version=self.version,
                    verdict=VerdictType.REQUIRE_HITL,
                    reason_code="HIGH_RISK_TOOL",
                    reason_text="Actie is geclassificeerd als hoog risico en vereist menselijke goedkeuring.",
                    evidence={},
                    deliberation_ms=0,
                    confidence=1.0,
                )

            # 5. Anders: APPROVE
            return OfficerVerdict(
                officer_name=self.name,
                officer_version=self.version,
                verdict=VerdictType.APPROVE,
                reason_code="COMPLIANT",
                reason_text="Veiligheidscontroles gepasseerd.",
                evidence={},
                deliberation_ms=0,
                confidence=1.0,
            )

        except Exception as e:
            logger.error(
                "SecurityOfficer error [tenant=%d, user=%d]: %s: %s",
                proposal.tenant_id,
                proposal.user_id,
                type(e).__name__,
                e,
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

    async def _legacy_deliberate(
        self,
        proposal: Proposal,
        context: DeliberationContext,
    ) -> OfficerVerdict:
        """Backward-compatible deliberate path for old-style caches (tests)."""
        try:
            # 1. PromptGuard scan
            input_text = proposal.reasoning + " " + json.dumps(proposal.action_params)

            normalized_text = _normalize_for_guard(input_text)

            guard_result = self._prompt_guard.scan(normalized_text)
            if guard_result.get("injection_detected"):
                return OfficerVerdict(
                    officer_name=self.name,
                    officer_version=self.version,
                    verdict=VerdictType.VETO,
                    reason_code="PROMPT_INJECTION",
                    reason_text="Mogelijke prompt injection of onveilige input gedetecteerd.",
                    evidence={"patterns": guard_result.get("patterns", [])},
                    deliberation_ms=0,
                    confidence=1.0,
                )

            # 2. Tool allowlist check
            if not await self._tool_broker.is_allowed(
                proposal.action_type, proposal.tenant_id, proposal.user_id
            ):
                return OfficerVerdict(
                    officer_name=self.name,
                    officer_version=self.version,
                    verdict=VerdictType.VETO,
                    reason_code="TOOL_NOT_ALLOWLISTED",
                    reason_text=f"Actie '{proposal.action_type}' is niet toegestaan voor deze gebruiker.",
                    evidence={},
                    deliberation_ms=0,
                    confidence=1.0,
                )

            # 3. RBAC scope check
            # `tenant_id` expliciet uit het VOORSTEL en niet uit de tenant-ContextVar: die is
            # ambient en hoort in een Dramatiq-worker of een geneste aanroep niet gegarandeerd
            # bij dit voorstel. Een autorisatie-antwoord mag daar niet van afhangen
            # (SP-COUNCIL-GATE-001, Gate 2-review H2).
            if not await self._rbac_checker.user_has_scope_for(
                proposal.user_id, proposal.action_type, tenant_id=proposal.tenant_id
            ):
                return OfficerVerdict(
                    officer_name=self.name,
                    officer_version=self.version,
                    verdict=VerdictType.VETO,
                    reason_code="MISSING_SCOPE",
                    reason_text="Onvoldoende RBAC rechten voor deze actie.",
                    evidence={},
                    deliberation_ms=0,
                    confidence=1.0,
                )

            # 4. High-risk prefix check
            if any(
                proposal.action_type.startswith(prefix)
                for prefix in HIGH_RISK_ACTION_PREFIXES
            ):
                return OfficerVerdict(
                    officer_name=self.name,
                    officer_version=self.version,
                    verdict=VerdictType.REQUIRE_HITL,
                    reason_code="HIGH_RISK_TOOL",
                    reason_text="Actie is geclassificeerd als hoog risico en vereist menselijke goedkeuring.",
                    evidence={},
                    deliberation_ms=0,
                    confidence=1.0,
                )

            # 5. Anders: APPROVE
            return OfficerVerdict(
                officer_name=self.name,
                officer_version=self.version,
                verdict=VerdictType.APPROVE,
                reason_code="COMPLIANT",
                reason_text="Veiligheidscontroles gepasseerd.",
                evidence={},
                deliberation_ms=0,
                confidence=1.0,
            )

        except Exception as e:
            logger.error(
                "SecurityOfficer error [tenant=%d, user=%d]: %s: %s",
                proposal.tenant_id,
                proposal.user_id,
                type(e).__name__,
                e,
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
