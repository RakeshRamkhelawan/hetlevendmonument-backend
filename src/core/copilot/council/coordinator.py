"""
AgentCouncil coordinator - orchestrates the seven Officers per ADR-027.

Responsibilities:
    1. Parallel deliberation across 7 voting Officers (asyncio.gather)
    2. Per-tenant dynamic policies (YAML) for timeouts and veto power
    3. Per-Officer circuit breaker
    4. Aggregation per strict-highest-bar rule (respecting overrides)
    5. AuditOfficer finalization (persists to hash chain)
    6. Return single CouncilDecision

Aggregation rules (in order):
    1. ANY Officer VETO         -> BLOCKED (if policy allows VETO)
    2. ANY Officer REQUIRE_HITL -> HITL_REQUIRED
    3. ANY Officer DEFER        -> DEFERRED
    4. ANY Officer MODIFY       -> MODIFIED
    5. Otherwise                -> APPROVED

Post-aggregation override (ADR-036 D4-003 / OP-166): an APPROVED or MODIFIED result is
upgraded to HITL_REQUIRED if proposal.action_type is on ALWAYS_HITL_ACTIONS (see that
constant for the OP-167/OP-168 prerequisites before it may ever be non-empty; OP-168 --
sprint dag 3 -- extended this from APPROVED-only to also cover MODIFIED, since
APPROVE_WITH_MODIFICATION is a routine officer vote, not an edge case). Never touches
BLOCKED/DEFERRED/an already-HITL_REQUIRED verdict -- see ALWAYS_HITL_ACTIONS below.

References:
    - docs/adr/027-copilot-agent-council.md
    - docs/copilot-architecture.md
"""

from __future__ import annotations

import asyncio
import logging
import time
from asyncio import wait_for
from typing import Any

from src.core.copilot.council.audit_writer import AuditWriteError
from src.core.copilot.council.members.audit_officer import AuditOfficer
from src.core.copilot.council.members.base import Officer
from src.core.copilot.council.members.compliance_officer import ComplianceOfficer
from src.core.copilot.council.members.ethics_officer import EthicsOfficer
from src.core.copilot.council.members.privacy_officer import PrivacyOfficer
from src.core.copilot.council.members.resource_officer import ResourceOfficer
from src.core.copilot.council.members.risk_officer import RiskOfficer
from src.core.copilot.council.members.sanity_officer import SanityOfficer
from src.core.copilot.council.members.security_officer import SecurityOfficer
from src.core.copilot.council.metrics import (
    COUNCIL_DELIBERATION_SECONDS,
    COUNCIL_TURNS_TOTAL,
    COUNCIL_VERDICT_TOTAL,
)
from src.core.copilot.council.policies.loader import load_policy
from src.core.copilot.council.technische_blokkade import (
    OFFICIEREN_MET_VETO_BIJ_TIJDOVERSCHRIJDING,
    REDEN_TIJDOVERSCHRIJDING,
)
from src.core.copilot.council.types import (
    CouncilDecision,
    DecisionVerdict,
    DeliberationContext,
    OfficerVerdict,
    Proposal,
    VerdictType,
)
from src.core.observability.tracing import get_tracer
from src.core.services.noodstop_toegang import NOODSTOP_GEWEIGERD, KlantStilgezet, eis_klant_actief

tracer = get_tracer(__name__)
logger = logging.getLogger(__name__)

# ADR-036 D4-003 (GDPR art. 22 / OP-166 / OP-164): actie-types die ALTIJD menselijke tussenkomst
# vereisen in `deliberate()`, ongeacht hoe de Officers stemmen. Gevuld conform Rakesh's beleidsbesluit
# (2026-08-25, OP-164) voor onomkeerbare hoog-risico acties.
ALWAYS_HITL_ACTIONS: frozenset[str] = frozenset(
    {
        "terminate_employee",
        "hire_candidate",
        "adjust_compensation",
        "disciplinary_action",
        "sign_external_contract",
        "execute_high_value_payout",
        "delete_tenant_data",
    }
)


class ConfigurationError(Exception):
    """Raised when council components are misconfigured."""

    pass


class AgentCouncil:
    """The Agent Council coordinator.

    Constructed with all Officers. Now supports dynamic per-tenant policies.
    """

    def __init__(
        self,
        compliance: ComplianceOfficer,
        privacy: PrivacyOfficer,
        security: SecurityOfficer,
        risk: RiskOfficer,
        ethics: EthicsOfficer,
        resource: ResourceOfficer,
        sanity: SanityOfficer,
        audit: AuditOfficer,
    ) -> None:
        self._voting_officers: tuple[Officer, ...] = (
            compliance,
            privacy,
            security,
            risk,
            ethics,
            resource,
            sanity,
        )
        self._audit_officer = audit

        all_officers = self._voting_officers + (self._audit_officer,)
        for o in all_officers:
            if not getattr(o, "version", None):
                raise ConfigurationError(f"officer {o.name} is missing a version string")
        names = [o.name for o in all_officers]
        if len(names) != len(set(names)):
            dupes = {n for n in names if names.count(n) > 1}
            raise ConfigurationError(f"duplicate officer name detected: {dupes}")

    async def deliberate(self, proposal: Proposal) -> CouncilDecision:
        """
        Run the full deliberation flow and return a CouncilDecision.
        """
        start_ms = time.perf_counter()
        # NOODSTOP PER KLANT (ADR-036 OP-03): DE deur van de Council. Alle vijf de aanroepers
        # (governance_gate, background_gate, de focus-builder-uitvoerroute en de twee plekken in de
        # copilot-service) komen hier langs, en elk vertaalt BLOCKED al naar zijn eigen weigering.
        # Voor de beraadslaging: een stilgezette klant krijgt geen besluit, geen ticket en geen
        # regel in de hashketen. Fail-closed, ook als de stand niet te lezen is.
        try:
            await eis_klant_actief(proposal.tenant_id)
        except KlantStilgezet as stop:
            # Geteld en gelogd (Gate 2 ronde 2 punt 6); geen regel in de hashketen, want er is
            # geen beraadslaging geweest.
            NOODSTOP_GEWEIGERD.labels(deur="council").inc()
            logger.warning(
                "council: voorstel geweigerd door de noodstop",
                extra={
                    "tenant_id": proposal.tenant_id,
                    "action_type": proposal.action_type,
                    "proposal_id": str(proposal.proposal_id),
                    "onbekend": stop.onbekend,
                },
            )
            return self._noodstop_decision(proposal, stop, start_ms)
        with tracer.start_as_current_span("copilot.council.deliberate") as span:
            span.set_attribute("tenant_id", proposal.tenant_id)
            span.set_attribute("user_id", proposal.user_id)
            span.set_attribute("action_type", proposal.action_type)
            span.set_attribute("proposal_id", str(proposal.proposal_id))

            logger.info(
                "council.deliberate started",
                extra={
                    "tenant_id": proposal.tenant_id,
                    "user_id": proposal.user_id,
                    "proposal_id": str(proposal.proposal_id),
                    "action_type": proposal.action_type,
                },
            )

            try:
                # 1. Load dynamic policy for this tenant
                policy = load_policy(proposal.tenant_id)

                # 2. Build context with policy
                context = await self._build_context(proposal, policy)

                # 3. Parallel gather verdicts (respecting policy timeouts)
                with COUNCIL_DELIBERATION_SECONDS.labels(officer="council_total").time():
                    verdicts = await self._gather_verdicts(proposal, context)

                # 4. Aggregate (respecting policy veto power)
                final_verdict, modifications = self._aggregate(verdicts, context)

                # 4b. ADR-036 D4-003 (GDPR art. 22 / OP-166): always-HITL action-type
                # override. Upgrade vanaf APPROVED **of** MODIFIED -- nooit een downgrade
                # van BLOCKED/DEFERRED/een reeds bestaand HITL_REQUIRED (die blijven wat
                # ze waren). Zie ALWAYS_HITL_ACTIONS hierboven voor de voorwaarde voordat
                # deze lijst ooit gevuld wordt.
                #
                # ADR-036 OP-168 (HITL-ticket-volledigheid sprint dag 3): tot deze fix
                # vuurde de upgrade UITSLUITEND vanaf APPROVED. `APPROVE_WITH_MODIFICATION`
                # is geen zeldzaam pad -- ComplianceOfficer geeft dit bij elke ontbrekende
                # `ai_disclosure`, EthicsOfficer bij elke bias-lexicon-treffer, beide
                # routinematig -- dus een gelijste actie kon een menselijke tussenkomst
                # omzeilen zolang minstens een Officer `APPROVE_WITH_MODIFICATION` gaf i.p.v.
                # unaniem APPROVE. Dat was het spiegelbeeld van de eigen belofte hierboven:
                # "ALTIJD menselijke tussenkomst ... ongeacht hoe de Officers stemmen" --
                # MODIFIED is ook een manier waarop Officers stemmen. Geen apart, kleiner
                # subset van MODIFIED-gevallen: de curatie zit al in `ALWAYS_HITL_ACTIONS`
                # zelf (een bewust, mens-samengestelde lijst van hoog-risico acties, nooit
                # gevuld zonder Rakesh's aparte beleidsbesluit, OP-164) -- voor een actie die
                # daar bewust op staat, verdient ELKE uitkomst behalve een reeds-blokkerende
                # menselijke tussenkomst, niet alleen de unaniem-goedgekeurde variant.
                #
                # `modifications` (de officier-voorgestelde aanpassingen) blijven ONGEWIJZIGD
                # meegegeven aan `_finalize()` hieronder, ook na deze upgrade -- ze zijn
                # relevante context voor de mens die straks goedkeurt/afwijst (WAAROM een
                # Officer een aanpassing wilde), niet iets dat deze upgrade zelf toepast of
                # weggooit. Wat er met die aanpassingen gebeurt ALS de mens goedkeurt (de
                # oorspronkelijke parameters uitvoeren, de aangepaste, of de mens laten
                # kiezen) is een eigen, latere ontwerpbeslissing over het
                # HITL-goedkeuringspad zelf (hitl_router.py), niet iets dat deze
                # verdict-aggregatie kan of moet oplossen.
                if (
                    final_verdict in (DecisionVerdict.APPROVED, DecisionVerdict.MODIFIED)
                    and proposal.action_type in ALWAYS_HITL_ACTIONS
                ):
                    final_verdict = DecisionVerdict.HITL_REQUIRED

                # 5. Audit finalization
                decision = await self._finalize(
                    proposal=proposal,
                    officer_verdicts=verdicts,
                    final_verdict=final_verdict,
                    modifications=modifications,
                    context=context,
                    start_ms=start_ms,
                )

                COUNCIL_TURNS_TOTAL.labels(
                    tenant_id=str(proposal.tenant_id),
                    verdict=decision.verdict.value,
                ).inc()

                span.set_attribute("verdict", decision.verdict.value)
                span.set_attribute("deliberation_ms", decision.deliberation_ms)
                return decision

            except Exception as exc:
                logger.error(
                    "council.deliberate failed: %s: %s",
                    type(exc).__name__,
                    exc,
                    exc_info=True,
                    extra={
                        "tenant_id": proposal.tenant_id,
                        "proposal_id": str(proposal.proposal_id),
                    },
                )
                span.record_exception(exc)
                return self._fail_secure_decision(proposal, exc, start_ms)

    async def _build_context(self, proposal: Proposal, policy: Any = None) -> DeliberationContext:
        """Construct DeliberationContext with the effective policy."""
        if policy is None:
            from src.core.copilot.council.policies.loader import load_policy

            try:
                policy = load_policy(proposal.tenant_id)
            except Exception:

                class DummyPolicy:
                    tenant_id = proposal.tenant_id
                    officers: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type

                policy = DummyPolicy()

        # Hard deadline is the max of all officer timeouts in policy
        deadline_ms = max((p.timeout_ms for p in policy.officers.values()), default=500)
        capabilities = proposal.capabilities or {}
        raw_profile = proposal.context_snapshot.get("twin_profile")
        twin_profile = raw_profile if raw_profile else None
        return DeliberationContext(
            tenant_settings={},
            user_preferences={},
            twin_profile=twin_profile,
            recent_decisions=(),
            deadline_ms=deadline_ms,
            request_id=proposal.proposal_id,
            policy=policy,
            registered_tools=capabilities.get("registered_tools", []),
            agent_health=capabilities.get("agent_health", {}),
            domain_packs=capabilities.get("domain_packs", []),
        )

    def _synthetic_verdict(
        self, officer: Officer, reason_code: str, policy: Any = None
    ) -> OfficerVerdict:
        """Produce a fail-secure synthetic verdict for timeouts/crashes.

        Een TIJDOVERSCHRIJDING is uitstel naar een mens en geen veto (brief 2026-10-27). Gemeten 2026-10-27 met 20
        rekenprocessen als last: 21 en 24 van 53 integratietests rood, allemaal door een TIMEOUT van de
        SecurityOfficer (46 van 46; 0x CIRCUIT_BREAKER_OPEN). Zonder last duurt die officier ~70 ms, onder last ~480
        ms (p95 628): op een drukke server blokkeerde een goede actie stil. Een tijdoverschrijding zegt niets over het
        voorstel; zij keurt NOOIT goed (`HITL_REQUIRED` is geen goedkeuring) en een echte veto van een andere
        officier blijft winnen (`_aggregate`: veto eerst). Een crash en een open circuit blijven een veto.

        Twee uitzonderingen (Gate 2 security-review 2026-10-28): de SecurityOfficer is de enige die de rechten van de
        aanvrager toetst en houdt bij een tijdoverschrijding zijn veto (`OFFICIEREN_MET_VETO_BIJ_TIJDOVERSCHRIJDING`);
        een officier zonder vetorecht blijft uitgesteld (REQUIRE_DEFERRAL) zodat een waarschuwer die tikt geen
        stroom mensentickets maakt.
        """
        can_veto = getattr(officer, "can_veto", True)
        if policy and officer.name in policy.officers:
            can_veto = policy.officers[officer.name].can_veto

        if (
            reason_code == "TIMEOUT"
            and can_veto
            and officer.name not in OFFICIEREN_MET_VETO_BIJ_TIJDOVERSCHRIJDING
        ):
            return OfficerVerdict(
                officer_name=officer.name,
                officer_version=officer.version,
                verdict=VerdictType.REQUIRE_HITL,
                reason_code=reason_code,
                reason_text=f"{officer.name}: {REDEN_TIJDOVERSCHRIJDING}",
                evidence={"error": reason_code},
                deliberation_ms=getattr(officer, "timeout_ms", 500),
                confidence=1.0,
                used_cache=False,
            )

        if can_veto:
            verdict = VerdictType.VETO
            reason_text = f"Fail-secure blocked due to {reason_code}"
        else:
            verdict = VerdictType.REQUIRE_DEFERRAL
            reason_text = f"Fail-secure deferred due to {reason_code}"

        return OfficerVerdict(
            officer_name=officer.name,
            officer_version=officer.version,
            verdict=verdict,
            reason_code=reason_code,
            reason_text=reason_text,
            evidence={"error": reason_code},
            deliberation_ms=getattr(officer, "timeout_ms", 500),
            confidence=1.0,
            used_cache=False,
        )

    async def _gather_verdicts(
        self,
        proposal: Proposal,
        context: DeliberationContext,
    ) -> tuple[OfficerVerdict, ...]:
        """
        Run all voting Officers in parallel with per-Officer timeout from policy.
        """
        policy = context.policy

        async def _deliberate_with_timeout(officer: Officer) -> OfficerVerdict:
            timeout_ms = officer.timeout_ms
            if policy and officer.name in policy.officers:
                timeout_ms = policy.officers[officer.name].timeout_ms

            with tracer.start_as_current_span(f"copilot.council.officer.{officer.name}") as ospan:
                if not officer.health_check():
                    return self._synthetic_verdict(officer, "CIRCUIT_BREAKER_OPEN", policy)

                with COUNCIL_DELIBERATION_SECONDS.labels(officer=officer.name).time():
                    try:
                        v = await wait_for(
                            officer.deliberate(proposal, context),
                            timeout=timeout_ms / 1000.0,
                        )
                    except asyncio.TimeoutError as exc:
                        ospan.record_exception(exc)
                        v = self._synthetic_verdict(officer, "TIMEOUT", policy)
                    except Exception as exc:
                        ospan.record_exception(exc)
                        v = self._synthetic_verdict(officer, "INTERNAL_ERROR", policy)

                ospan.set_attribute("verdict", v.verdict.value)
                return v

        tasks = [_deliberate_with_timeout(o) for o in self._voting_officers]
        return tuple(await asyncio.gather(*tasks))

    def _aggregate(
        self,
        verdicts: tuple[OfficerVerdict, ...],
        context: DeliberationContext | None = None,
    ) -> tuple[
        DecisionVerdict, dict[str, Any] | None  # TODO(TYPE): replace Any with concrete type
    ]:  # TODO(TYPE): replace Any with concrete type
        """
        Apply aggregation rules, respecting per-officer veto policies.
        """
        policy = context.policy if context else None
        has_downgraded_veto = False

        # 1. Check for VETOs, but only if the officer is ALLOWED to veto in this policy
        for v in verdicts:
            if v.verdict == VerdictType.VETO:
                can_veto = True
                if policy and v.officer_name in policy.officers:
                    can_veto = policy.officers[v.officer_name].can_veto

                if can_veto:
                    return DecisionVerdict.BLOCKED, None
                else:
                    logger.warning(
                        "Officer %s attempted VETO but policy denies veto power. Downgrading to DEFERRED.",
                        v.officer_name,
                        extra={
                            "tenant_id": getattr(context.policy, "tenant_id", 0)
                            if context and context.policy is not None
                            else 0
                        },
                    )
                    has_downgraded_veto = True

        if any(v.verdict == VerdictType.REQUIRE_HITL for v in verdicts):
            return DecisionVerdict.HITL_REQUIRED, None

        if has_downgraded_veto or any(v.verdict == VerdictType.REQUIRE_DEFERRAL for v in verdicts):
            return DecisionVerdict.DEFERRED, None

        if any(v.verdict == VerdictType.APPROVE_WITH_MODIFICATION for v in verdicts):
            mods: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
            for v in verdicts:
                if v.verdict == VerdictType.APPROVE_WITH_MODIFICATION:
                    mods[v.officer_name] = v.evidence.get("modifications", {})
            return DecisionVerdict.MODIFIED, mods

        return DecisionVerdict.APPROVED, None

    async def _finalize(
        self,
        proposal: Proposal,
        officer_verdicts: tuple[OfficerVerdict, ...],
        final_verdict: DecisionVerdict,
        modifications: dict[str, Any] | None,  # TODO(TYPE): replace Any with concrete type
        context: DeliberationContext,
        start_ms: float,
    ) -> CouncilDecision:
        """Invoke AuditOfficer to persist and build the final CouncilDecision."""
        try:
            return await self._audit_officer.finalize_and_persist(
                proposal=proposal,
                officer_verdicts=officer_verdicts,
                final_verdict=final_verdict,
                modifications=modifications,
                hitl_request_id=None,
                start_ms=start_ms,
                context=context,
            )
        except AuditWriteError as exc:
            audit_verdict = OfficerVerdict(
                officer_name=self._audit_officer.name,
                officer_version=self._audit_officer.version,
                verdict=VerdictType.VETO,
                reason_code="AUDIT_WRITE_FAILED",
                reason_text="Fail-secure blocked due to AUDIT_WRITE_FAILED",
                evidence={"error": str(exc)},
                deliberation_ms=0,
                confidence=1.0,
                used_cache=False,
            )
            return self._fail_secure_decision(
                proposal, exc, start_ms, officer_verdicts=officer_verdicts + (audit_verdict,)
            )

    def _noodstop_decision(
        self, proposal: Proposal, stop: KlantStilgezet, start_ms: float
    ) -> CouncilDecision:
        """Een BLOCKED-besluit zonder beraadslaging: de klant staat stil (of dat is onbekend)."""
        return CouncilDecision(
            proposal_id=proposal.proposal_id,
            tenant_id=proposal.tenant_id,
            user_id=proposal.user_id,
            verdict=DecisionVerdict.BLOCKED,
            officer_verdicts=(),
            explanation_for_user=stop.bericht,
            decision_hash="NOODSTOP",
            previous_decision_hash=None,
            deliberation_ms=int((time.perf_counter() - start_ms) * 1000),
        )

    def _fail_secure_decision(
        self,
        proposal: Proposal,
        exc: Exception,
        start_ms: float,
        officer_verdicts: tuple[OfficerVerdict, ...] = (),
    ) -> CouncilDecision:
        """Build a synthetic BLOCKED decision when the Council itself errors out."""
        return CouncilDecision(
            proposal_id=proposal.proposal_id,
            tenant_id=proposal.tenant_id,
            user_id=proposal.user_id,
            verdict=DecisionVerdict.BLOCKED,
            officer_verdicts=officer_verdicts,
            explanation_for_user="Een interne fout verhinderde de Co-Pilot om je verzoek te verwerken.",
            decision_hash="FAILED",
            previous_decision_hash=None,
            deliberation_ms=int((time.perf_counter() - start_ms) * 1000),
        )
