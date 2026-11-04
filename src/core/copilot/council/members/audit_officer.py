"""
AuditOfficer - Tamper-evident logging per EU AI Act art. 12.

ALWAYS RUNS LAST. Never blocks deliberation; instead persists the final
decision to the hash chain. Failure to write = fail-secure (Council BLOCKS).

Wraps existing modules:
    - src.core.governance.hash_chain (ADR-019 SHA-256 chain)
    - src.core.governance.audit (audit log writer)
    - src.core.copilot.council.audit_writer (new, council-specific schema)

Responsibilities:
    1. Build CouncilDecision with all 7 OfficerVerdicts
    2. Compute decision_hash = SHA-256 over canonical JSON + previous_hash
    3. Persist to council_decisions table (RLS isolated per tenant)
    4. Persist all 7 OfficerVerdicts to officer_verdicts table
    5. Generate explanation_for_user text (GDPR art. 13-15)
    6. Emit Prometheus metric copilot_audit_writes_total

Verdict map:
    APPROVE        - write succeeded, hash chain intact
    VETO (rare)    - audit write failed -> Council aggregates as BLOCKED

Cacheable: never (every decision is unique).

References:
    - docs/adr/027-copilot-agent-council.md Section 5.2.7 + Section 7
    - ADR-019 (audit logging + hash chain)
    - EU AI Act art. 12 (automatic logging requirement)
"""

from __future__ import annotations

import logging
import time
from typing import Any, ClassVar
from uuid import UUID

from src.core.copilot.council.audit_writer import AuditWriteError, CouncilAuditWriter
from src.core.copilot.council.cache import OfficerVerdictCache
from src.core.copilot.council.technische_blokkade import (
    KLANTTEKST_NIET_BEOORDEELD,
    is_technisch_niet_beoordeeld,
)
from src.core.copilot.council.members.base import Officer
from src.core.copilot.council.metrics import AUDIT_WRITES_TOTAL
from src.core.copilot.council.types import (
    CouncilDecision,
    DecisionVerdict,
    DeliberationContext,
    OfficerVerdict,
    Proposal,
    VerdictType,
)
from src.core.observability.tracing import get_tracer

tracer = get_tracer(__name__)
logger = logging.getLogger(__name__)


class AuditOfficer(Officer):
    """Tamper-evident logging Officer."""

    name: ClassVar[str] = "AuditOfficer"
    version: ClassVar[str] = "1.0.0"
    allowed_verdicts: ClassVar[frozenset[VerdictType]] = frozenset(
        {
            VerdictType.APPROVE,
            VerdictType.VETO,  # Only on audit-write failure (fail-secure)
        }
    )
    timeout_ms: ClassVar[int] = 400
    can_cache: ClassVar[bool] = False

    def __init__(
        self,
        audit_writer: CouncilAuditWriter,
        cache: OfficerVerdictCache | None = None,
    ) -> None:
        super().__init__(cache=cache)
        self._writer = audit_writer

    async def deliberate(
        self,
        proposal: Proposal,
        context: DeliberationContext,
    ) -> OfficerVerdict:
        """
        AuditOfficer's deliberate() is a no-op for the verdict itself.

        The Coordinator calls finalize_and_persist() *after* aggregating
        the other six Officer verdicts, passing the aggregated result so
        the audit record contains the full deliberation history.

        Returns APPROVE if everything else works; this verdict is only
        included for symmetry with other Officers and to allow circuit
        breaker integration.
        """
        with tracer.start_as_current_span(
            f"copilot.officer.{self.name}.deliberate"
        ) as span:
            span.set_attribute("tenant_id", proposal.tenant_id)
            span.set_attribute("action_type", proposal.action_type)
            verdict = OfficerVerdict(
                officer_name=self.name,
                officer_version=self.version,
                verdict=VerdictType.APPROVE,
                reason_code="AUDIT_ACK",
                reason_text="Audit log pending finalization",
                evidence={},
                deliberation_ms=1,
                confidence=1.0,
                used_cache=False,
            )
            span.set_attribute("verdict", verdict.verdict.value)
            span.set_attribute("reason_code", verdict.reason_code)
            return verdict

    def _generate_explanation(
        self, officer_verdicts: tuple[OfficerVerdict, ...], final_verdict: str
    ) -> str:
        if final_verdict == DecisionVerdict.APPROVED:
            return "De Co-Pilot is akkoord en voert de actie uit."
        elif final_verdict == DecisionVerdict.MODIFIED:
            reasons = [
                v.reason_text
                for v in officer_verdicts
                if v.verdict == VerdictType.APPROVE_WITH_MODIFICATION
            ]
            return f"De Co-Pilot heeft de actie aangepast vanwege: {', '.join(reasons)}."
        elif final_verdict == DecisionVerdict.HITL_REQUIRED:
            reasons = [
                v.reason_text for v in officer_verdicts if v.verdict == VerdictType.REQUIRE_HITL
            ]
            if not reasons:
                # ADR-036 D4-003 (OP-166): kan hier leeg zijn als de coordinator een
                # APPROVED- OF MODIFIED-verdict optilde via ALWAYS_HITL_ACTIONS (GDPR art.
                # 22, sinds OP-168 dekt de upgrade ook MODIFIED) -- geen enkele officer
                # stemde REQUIRE_HITL, dus er is geen officer-reden om te citeren. Zonder
                # deze tak zou de string hieronder eindigen op "vanwege: ." (een lege
                # join), een kapotte, niet-informatieve uitleg in precies het pad dat
                # GDPR art. 22 uitlegbaarheid vereist.
                return (
                    "Deze actie vereist je expliciete goedkeuring vanwege een "
                    "platformbeleidsregel die menselijk toezicht verplicht voor dit "
                    "type actie."
                )
            return f"Deze actie vereist je expliciete goedkeuring vanwege: {', '.join(reasons)}."
        elif final_verdict == DecisionVerdict.DEFERRED:
            reasons = [
                v.reason_text for v in officer_verdicts if v.verdict == VerdictType.REQUIRE_DEFERRAL
            ]
            return f"Deze actie wordt later opnieuw beoordeeld vanwege: {', '.join(reasons)}."
        else:
            # Een veto dat alleen uit een TIMEOUT, open circuit of interne fout bestaat zegt niets over het
            # voorstel zelf; de klant hoort dat het opnieuw kan (de blokkade blijft: fail-secure).
            if final_verdict == DecisionVerdict.BLOCKED and is_technisch_niet_beoordeeld(
                officer_verdicts
            ):
                return KLANTTEKST_NIET_BEOORDEELD
            return "De Co-Pilot kan deze actie niet uitvoeren."

    async def finalize_and_persist(
        self,
        proposal: Proposal,
        officer_verdicts: tuple[OfficerVerdict, ...],
        final_verdict: DecisionVerdict,
        modifications: dict[str, Any] | None,  # TODO(TYPE): replace Any with concrete type
        hitl_request_id: UUID | None,
        start_ms: float,
        context: DeliberationContext,
    ) -> CouncilDecision:
        """
        Persist the Council decision to the hash chain.

        Hash computation happens inside ``persist()`` under ``pg_advisory_xact_lock``
        so that concurrent deliberations for the same tenant cannot fork the chain.

        Returns the CouncilDecision with the decision_id that was written to the
        database so callers can query the audit trail using the same ID.
        """
        try:
            explanation = self._generate_explanation(officer_verdicts, final_verdict)

            # Query previous hash so persist() can validate chain integrity
            # under pg_advisory_xact_lock. The value may be stale due to
            # concurrent writes, but the lock + validation inside persist()
            # catches any race (fail-secure).
            previous_hash = await self._writer.get_previous_hash(proposal.tenant_id)

            decision = CouncilDecision(
                proposal_id=proposal.proposal_id,
                tenant_id=proposal.tenant_id,
                user_id=proposal.user_id,
                verdict=final_verdict,
                officer_verdicts=officer_verdicts,
                explanation_for_user=explanation,
                decision_hash="PENDING",
                previous_decision_hash=previous_hash,
                deliberation_ms=int((time.perf_counter() - start_ms) * 1000),
                modifications=modifications,
                hitl_request_id=hitl_request_id,
            )

            await self._writer.persist(
                decision, proposal, officer_verdicts, final_verdict
            )

            # Prometheus metric is now emitted inside audit_writer.persist()
            # to guarantee success/failure counting at the persistence layer.
            return decision

        except Exception as exc:
            # audit_writer.persist() already increments AUDIT_WRITES_TOTAL
            # on failure; we only re-raise here.
            logger.error(
                "AuditOfficer.finalize_and_persist failed: %s: %s",
                type(exc).__name__,
                exc,
                exc_info=True,
                extra={"tenant_id": proposal.tenant_id, "proposal_id": str(proposal.proposal_id)},
            )
            raise AuditWriteError("Audit write failed") from exc

