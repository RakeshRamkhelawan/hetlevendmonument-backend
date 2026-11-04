"""
PrivacyOfficer - GDPR, PII handling, consent enforcement.

Wraps existing modules:
    - src.core.governance.gdpr_enforcer
    - src.core.governance.cookie_consent
    - src.core.als.twin.practical_twin_service (consent gate per ADR-026)

Checks (per Proposal):
    1. PII detection in action_params (regex + ML classifier)
    2. Cross-tenant access attempt -> VETO (ADR-003 tenant isolation)
    3. Cross-session memory consent (ADR-026) for twin-derived suggestions
    4. Bulk PII export -> REQUIRE_HITL (always needs explicit user approval)
    5. DSAR-related actions -> verify user has rights activated

Verdict map:
    APPROVE        - no privacy objections
    REQUIRE_HITL   - user must explicitly confirm (bulk export, etc.)
    VETO           - cross-tenant attempt, missing mandatory consent

Cacheable: never (consent state can change anytime).

References:
    - docs/adr/027-copilot-agent-council.md Section 5.2.2
    - GDPR Regulation (EU) 2016/679 articles 6, 9, 13-15, 22
    - ADR-003 (tenant boundary), ADR-026 (twin hardening + consent)
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar, Protocol

from src.core.copilot.council.cache import OfficerVerdictCache
from src.core.copilot.council.members.base import Officer
from src.core.copilot.council.types import (
    DataClassification,
    DeliberationContext,
    OfficerVerdict,
    Proposal,
    VerdictType,
)
from src.core.observability.tracing import get_tracer

tracer = get_tracer(__name__)
logger = logging.getLogger(__name__)


class GDPREnforcer(Protocol):
    def detect_pii(
        self,
        data: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
    ) -> list[str]: ...  # TODO(TYPE): replace Any with concrete type


class ConsentGate(Protocol):
    async def has_consent(self, user_id: int, tenant_id: int) -> bool: ...


class PracticalTwinService(Protocol):
    pass


class PrivacyOfficer(Officer):
    """GDPR, PII, and consent Officer."""

    name: ClassVar[str] = "PrivacyOfficer"
    version: ClassVar[str] = "1.0.0"
    allowed_verdicts: ClassVar[frozenset[VerdictType]] = frozenset(
        {
            VerdictType.APPROVE,
            VerdictType.REQUIRE_HITL,
            VerdictType.VETO,
        }
    )
    timeout_ms: ClassVar[int] = 500
    can_cache: ClassVar[bool] = False

    def __init__(
        self,
        gdpr_enforcer: GDPREnforcer,
        consent_gate: ConsentGate,
        twin_service: PracticalTwinService,
        cache: OfficerVerdictCache | None = None,
    ) -> None:
        super().__init__(cache=cache)
        self._gdpr_enforcer = gdpr_enforcer
        self._consent_gate = consent_gate
        self._twin_service = twin_service

    async def deliberate(
        self,
        proposal: Proposal,
        context: DeliberationContext,
    ) -> OfficerVerdict:
        with tracer.start_as_current_span(f"copilot.officer.{self.name}.deliberate") as span:
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
            # 1. Cross-tenant detection
            params_tenant_id = proposal.action_params.get("tenant_id")
            if params_tenant_id is not None and str(params_tenant_id) != str(proposal.tenant_id):
                return OfficerVerdict(
                    officer_name=self.name,
                    officer_version=self.version,
                    verdict=VerdictType.VETO,
                    reason_code="CROSS_TENANT_ATTEMPT",
                    reason_text="Beveiligingsschending: cross-tenant data benaderd.",
                    # De UITKOMST van de vergelijking, niet de waarde (ADR-036 OP-33).
                    # `params_tenant_id` komt rechtstreeks uit `proposal.action_params` en is dus
                    # modeloutput: het kan elke string zijn, inclusief een persoonsgegeven. Deze
                    # evidence gaat via `audit_writer.persist()` onbewerkt naar
                    # `OfficerVerdictRow.evidence` en wordt meegehasht -- in dezelfde transactie
                    # waarin `action_params` sinds OP-33 juist WEL gepseudonimiseerd wordt. De
                    # waarde hier laten staan zou die redactie langs de zijdeur ongedaan maken.
                    #
                    # Wat het bewijs moet dragen is DAT de tenant niet klopte, plus genoeg om de
                    # bevinding te kunnen naspelen. Het type volstaat daarvoor; de waarde zelf is
                    # het persoonsgegeven.
                    evidence={
                        "proposal_tenant": proposal.tenant_id,
                        "params_tenant_differs": True,
                        "params_tenant_type": type(params_tenant_id).__name__,
                    },
                    deliberation_ms=0,
                    confidence=1.0,
                )

            # 2. PII detection
            pii_detected = self._gdpr_enforcer.detect_pii(proposal.action_params)

            # 3. PII + export/share/send
            action = proposal.action_type.lower()
            if pii_detected and any(
                action.startswith(prefix) for prefix in ["export_", "share_", "send_"]
            ):
                return OfficerVerdict(
                    officer_name=self.name,
                    officer_version=self.version,
                    verdict=VerdictType.REQUIRE_HITL,
                    reason_code="PII_BULK_ACTION",
                    reason_text="Menselijke goedkeuring vereist voor export van PII.",
                    evidence={"pii_types": pii_detected},
                    deliberation_ms=0,
                    confidence=1.0,
                )

            # 4. Consent check for Twin
            if context.twin_profile is not None:
                if not await self._consent_gate.has_consent(proposal.user_id, proposal.tenant_id):
                    return OfficerVerdict(
                        officer_name=self.name,
                        officer_version=self.version,
                        verdict=VerdictType.VETO,
                        reason_code="MISSING_TWIN_CONSENT",
                        reason_text="Gebruiker heeft geen toestemming gegeven voor cross-session memory.",
                        evidence={},
                        deliberation_ms=0,
                        confidence=1.0,
                    )

            # 5. DSAR actions
            if action.startswith("dsar_"):
                if not proposal.action_params.get("dsar_activated", False):
                    return OfficerVerdict(
                        officer_name=self.name,
                        officer_version=self.version,
                        verdict=VerdictType.VETO,
                        reason_code="DSAR_NOT_ACTIVATED",
                        reason_text="DSAR rechten niet geactiveerd voor deze gebruiker.",
                        evidence={},
                        deliberation_ms=0,
                        confidence=1.0,
                    )

            return OfficerVerdict(
                officer_name=self.name,
                officer_version=self.version,
                verdict=VerdictType.APPROVE,
                reason_code="COMPLIANT",
                reason_text="Voldoet aan privacy eisen.",
                evidence={"pii_types": pii_detected},
                deliberation_ms=0,
                confidence=1.0,
            )

        except Exception as e:
            logger.error(
                "PrivacyOfficer error",
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
