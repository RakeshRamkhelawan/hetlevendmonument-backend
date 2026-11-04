"""
AI Transparency Service - GDPR Articles 13, 14, 21, 22 compliance.

Implements:
- Art. 13/14: Transparency about AI processing
- Art. 21: Right to object to profiling
- Art. 22: Right to human review for automated decisions

Usage:
    service = AITransparencyService(db)

    # Log AI decision with explanation (Art. 13/14)
    decision = await service.log_ai_decision(
        user_id="user_123",
        tenant_id=1,
        agent_id="agent_456",
        decision_type="workflow_recommendation",
        explanation="Recommended based on user role and experience",
        profiling_involved=True,
        human_review_available=True,
    )

    # Request human review (Art. 22(3))
    review = await service.request_human_review(
        decision_id="dec_123",
        user_id="user_456",
        reason="I disagree with this decision",
    )

    # Check profiling opt-out (Art. 21)
    is_opted_out = await service.check_profiling_opt_out(
        user_id="user_123",
        tenant_id=1,
        profiling_type=ProfilingType.BEHAVIORAL,
    )

    # Set profiling opt-out (Art. 21)
    await service.set_profiling_opt_out(
        user_id="user_123",
        tenant_id=1,
        profiling_type=ProfilingType.BEHAVIORAL,
        opt_out=True,
    )
"""

import inspect
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.governance.models import AIDecision, AuditLog
from src.core.governance.models import HumanReviewRequest as HumanReviewRequestModel
from src.core.governance.models import UserProfilingOptOut
from src.core.utils.best_effort import best_effort
from src.core.governance.ketencontext import ketencontext
from src.core.governance.audit_chain_key import mark_entry

logger = logging.getLogger(__name__)


async def _maybe_await(value: Any) -> Any:  # TODO(TYPE): replace Any with concrete type
    """Await value if it's a coroutine (handles AsyncMock in tests)."""
    if inspect.iscoroutine(value):
        return await value
    return value


class ProfilingType(str, Enum):
    """
    Types of profiling under GDPR Art. 4(4).

    Art. 4(4): "profiling" means any form of automated processing of personal
    data consisting of the use of personal data to evaluate certain personal
    aspects relating to a natural person.
    """

    BEHAVIORAL = "behavioral"  # Analyzing behavior patterns
    PREFERENCE = "preference"  # Preference inference
    PREDICTIVE = "predictive"  # Predicting future behavior
    AUTOMATED_DECISION = "automated_decision"  # Art. 22 decisions


class AITransparencyError(Exception):
    """Base exception for AI transparency errors."""

    pass


class ExplanationRequiredError(AITransparencyError):
    """Raised when AI decision lacks required explanation."""

    pass


@dataclass
class AIDecisionRecord:
    """
    Record of an AI decision for transparency.

    This provides the "meaningful information about the logic involved"
    required by GDPR Art. 13/14.
    """

    id: str
    user_id: str
    tenant_id: int
    agent_id: str
    decision_type: str
    input_data_summary: dict[str, object]  # Minimized for privacy
    output_data: dict[str, object]
    confidence_score: float | None
    explanation: str  # Human-readable explanation (Art. 13/14)
    profiling_involved: bool
    human_review_available: bool  # Art. 22(3)
    human_review_requested: bool
    human_review_decision: str | None
    created_at: datetime


@dataclass
class HumanReviewRequest:
    """Result of human review request."""

    review_id: str
    status: str  # "pending", "in_review", "completed"
    estimated_resolution_days: int
    user_rights: list[str]
    created_at: datetime


class AITransparencyService:
    """
    GDPR-compliant AI transparency and profiling management.

    Addresses:
    - Art. 13/14: Transparency about AI processing (explanation, logic)
    - Art. 21: Right to object to profiling (opt-out mechanism)
    - Art. 22: Right to human review for automated decisions

    Example:
        service = AITransparencyService(db)

        # Log AI decision
        decision = await service.log_ai_decision(
            user_id="user_123",
            tenant_id=1,
            agent_id="agent_456",
            decision_type="workflow_recommendation",
            explanation="User profile matches HR onboarding criteria",
            profiling_involved=True,
            human_review_available=True,
        )

        # User requests human review
        review = await service.request_human_review(
            decision_id=decision.id,
            user_id="user_123",
            reason="I believe this recommendation is incorrect",
        )
    """

    def __init__(self, db: AsyncSession) -> None:
        """
        Initialize AI Transparency Service.

        Args:
            db: SQLAlchemy async session
        """
        self._db = db

    async def _populate_hash_chain(self, audit_entry: AuditLog, tenant_id_int: int) -> None:
        """Populeer audit_hash + previous_hash + timestamp in-place (ADR-019). Fail-safe: nooit raising.

        De tijdstempel wordt HIER gezet en niet door de aanroeper, omdat hij na het slot moet
        (ADR-036 OP-110, zie het commentaar bij de toekenning).
        """
        try:
            # Advisory lock serializes chain writes per tenant -- prevents forked chain.
            await self._db.execute(
                text("SELECT pg_advisory_xact_lock(:key)"), {"key": tenant_id_int}
            )
            # DE TIJDSTEMPEL NA HET SLOT (ADR-036 OP-110). De schrijvers ketenen aan de laatste rij
            # ORDER BY timestamp DESC, id DESC en de verifier loopt de keten op diezelfde volgorde. Een
            # tijdstempel die VOOR het slot wordt gekozen, kan na die van een latere schrijver worden
            # geketend: op tijd VOOR hem, in de keten ACHTER hem, en dan meldt verify_chain manipulatie
            # op een gave keten. Binnen het slot is elke tijdstempel later dan die van de vorige
            # schrijver. De tijdstempel zit in de hash en staat er hier VOOR het hashen; wat er
            # gehasht wordt is niet veranderd. Zelfde vorm als AuditService.log_event. De drie
            # aanroepers in dit bestand zetten hem NIET meer zelf: dat deden ze voor het slot.
            audit_entry.timestamp = datetime.now(timezone.utc)
            async with self._db.begin_nested():
                from src.core.governance.hash_chain import HashChainVerifier  # noqa: PLC0415

                async with ketencontext(self._db, tenant_id_int):
                    prev_result = await self._db.execute(
                        select(AuditLog.audit_hash)
                        .where(
                            AuditLog.tenant_id == tenant_id_int,
                            AuditLog.audit_hash.isnot(None),
                        )
                        .order_by(AuditLog.timestamp.desc(), AuditLog.id.desc())
                        .limit(1)
                    )
                    _previous_hash: str | None = prev_result.scalar_one_or_none()
                _verifier = HashChainVerifier(db_session=self._db)
                audit_entry.previous_hash = _previous_hash
                # Markeer WELK algoritme deze rij gebruikt, VOOR het hashen (ADR-036 OP-120).
                # `mark_entry` schakelt alleen om als er een echte sleutel is; zonder sleutel blijft
                # de rij op legacy SHA-256 in plaats van hard te falen en stil ongehasht te landen.
                mark_entry(audit_entry)
                audit_entry.audit_hash = _verifier._compute_hash(audit_entry, _previous_hash)
        except Exception as _e:
            logger.error(
                "ai_transparency: hash chain populatie mislukt tenant %s: %s: %s",
                tenant_id_int,
                type(_e).__name__,
                _e,
                exc_info=True,
            )
            # audit_entry wordt alsnog weggeschreven zonder hash (degraded mode)
        # Een regel ZONDER keten (het slot of de ketenlookup faalde) heeft hier nog geen
        # tijdstempel. Die hoort niet in een keten en hoeft dus niet na een slot.
        if audit_entry.timestamp is None:
            audit_entry.timestamp = datetime.now(timezone.utc)

    def _minimize_input_data(self, input_data: dict[str, object]) -> dict[str, object]:
        """
        Minimize input data for privacy (GDPR data minimization).

        Removes PII and keeps only decision-relevant fields.

        Args:
            input_data: Raw input data

        Returns:
            Minimized data dictionary
        """
        minimized = {}

        # Decision-relevant fields (safe to log)
        allowed_keys = [
            "context",
            "preferences",
            "history_summary",
            "category",
            "role",
            "department",
            "skill_level",
            "usage_pattern",
        ]

        for key in allowed_keys:
            if key in input_data:
                minimized[key] = input_data[key]

        return minimized

    async def log_ai_decision(
        self,
        user_id: str,
        tenant_id: int,
        agent_id: str,
        decision_type: str,
        explanation: str,
        input_data: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
        output_data: dict[str, object] | None = None,
        confidence_score: float | None = None,
        profiling_involved: bool = True,
        human_review_available: bool = True,
    ) -> AIDecisionRecord:
        """
        Log an AI decision for transparency (Art. 13/14).

        GDPR requires "meaningful information about the logic involved" in
        automated decision-making. This method ensures all AI decisions are
        logged with human-readable explanations.

        Args:
            user_id: Data subject ID
            tenant_id: Tenant context
            agent_id: AI agent that made the decision
            decision_type: Type of decision (e.g., "workflow_recommendation")
            input_data: Input data used for decision
            output_data: Decision output
            confidence_score: AI confidence (0.0 - 1.0)
            explanation: Human-readable explanation (REQUIRED)
            profiling_involved: Whether this involves profiling (Art. 4(4))
            human_review_available: Whether user can request review (Art. 22(3))

        Returns:
            AIDecisionRecord with decision details

        Raises:
            ExplanationRequiredError: If explanation is empty
        """
        # Validate explanation (Art. 13/14 requirement)
        if not explanation or len(explanation.strip()) < 10:
            raise ExplanationRequiredError(
                "GDPR Art. 13/14 requires meaningful explanation of AI decisions. "
                "Please provide a human-readable explanation of the logic involved "
                "(minimum 10 characters)."
            )

        # Minimize input data for privacy
        input_summary = self._minimize_input_data(input_data or {})

        # Check profiling opt-out before persisting (GDPR Art. 21)
        if profiling_involved:
            opted_out = await self.check_profiling_opt_out(
                user_id=user_id, tenant_id=tenant_id, profiling_type=ProfilingType.BEHAVIORAL
            )
            if opted_out:
                profiling_involved = False

        # Create database record
        db_record = AIDecision(
            user_id=user_id,
            tenant_id=tenant_id,
            agent_id=agent_id,
            decision_type=decision_type,
            input_data=input_summary,
            output_data=output_data or {},
            confidence_score=confidence_score,
            explanation=explanation,
            profiling_involved=profiling_involved,
            human_review_available=human_review_available,
            human_review_requested=False,
        )
        self._db.add(db_record)
        await self._db.commit()
        await self._db.refresh(db_record)

        # Create decision record for return
        record = AIDecisionRecord(
            id=str(db_record.id),
            user_id=user_id,
            tenant_id=tenant_id,
            agent_id=agent_id,
            decision_type=decision_type,
            input_data_summary=input_summary,
            output_data=output_data or {},
            confidence_score=confidence_score,
            explanation=explanation,
            profiling_involved=profiling_involved,
            human_review_available=human_review_available,
            human_review_requested=False,
            human_review_decision=None,
            created_at=db_record.created_at,
        )

        # Log to audit trail
        user_id_int = int(user_id) if user_id and user_id.isdigit() else None
        async with best_effort("ai_transparency audit log (ai.decision_made)", db_session=self._db):
            audit_entry = AuditLog(
                tenant_id=tenant_id,
                user_id=user_id_int,
                action="ai.decision_made",
                resource=f"ai_decision:{record.id}",
                details={
                    "agent_id": agent_id,
                    "decision_type": decision_type,
                    "profiling_involved": profiling_involved,
                    "human_review_available": human_review_available,
                    "excerpt": explanation[:100],  # Truncated for log
                },
                event_type="ai_decision",
                threat_level="info",
                client_ip="unknown",
                endpoint="/api/agents/execute",
                description=f"AI decision made by {agent_id}",
                event_metadata={
                    "profiling": profiling_involved,
                    "automated_decision": True,
                },
            )
            # De tijdstempel wordt in `_populate_hash_chain` gezet, NA het slot (OP-110).
            await self._populate_hash_chain(audit_entry, tenant_id)
            self._db.add(audit_entry)
            await self._db.commit()

        return record

    async def request_human_review(
        self,
        decision_id: str,
        user_id: str,
        reason: str,
    ) -> HumanReviewRequest:
        """
        Request human review of an AI decision (Art. 22(3)).

        GDPR Art. 22(3): "the data controller shall implement suitable measures
        to safeguard the data subject's rights and freedoms and legitimate
        interests, at least the right to obtain human intervention on the part
        of the controller, to express his or her point of view and to contest
        the decision."

        Args:
            decision_id: ID of the AI decision to review
            user_id: Data subject ID
            reason: User's reason for requesting review

        Returns:
            HumanReviewRequest with review status and user rights
        """
        # Convert decision_id to int
        try:
            decision_id_int = int(decision_id)
        except (ValueError, TypeError):
            decision_id_int = 0

        # Create database record
        db_record = HumanReviewRequestModel(
            decision_id=decision_id_int,
            user_id=user_id,
            reason=reason,
            status="pending",
        )
        self._db.add(db_record)
        await self._db.commit()
        await self._db.refresh(db_record)

        review_id = str(db_record.id)

        # Log the request
        user_id_int = int(user_id) if user_id and user_id.isdigit() else None
        async with best_effort(
            "ai_transparency audit log (ai.human_review_requested)", db_session=self._db
        ):
            # Resolve real tenant_id from AIDecision -- required for ADR-019 hash chain.
            _tid_result = await self._db.execute(
                select(AIDecision.tenant_id).where(AIDecision.id == decision_id_int)
            )
            _raw_tid = await _maybe_await(_tid_result.scalar_one_or_none())
            _decision_tenant_id: int = _raw_tid if isinstance(_raw_tid, int) else 0
            if _decision_tenant_id == 0:
                logger.warning(
                    "request_human_review: AIDecision %s niet gevonden -- audit tenant_id=0 (degraded)",
                    decision_id_int,
                )
            audit_entry = AuditLog(
                tenant_id=_decision_tenant_id,
                user_id=user_id_int,
                action="ai.human_review_requested",
                resource=f"ai_decision:{decision_id}",
                details={
                    "decision_id": decision_id,
                    "reason": reason,
                    "requested_by": user_id,
                },
                event_type="ai_human_review",
                threat_level="info",
                client_ip="unknown",
                endpoint="/api/gdpr/ai-review-request",
                description=f"Human review requested for AI decision {decision_id}",
                event_metadata={
                    "gdpr_article": "22(3)",
                    "right": "human_review",
                },
            )
            # De tijdstempel wordt in `_populate_hash_chain` gezet, NA het slot (OP-110).
            if _decision_tenant_id > 0:
                await self._populate_hash_chain(audit_entry, _decision_tenant_id)
            self._db.add(audit_entry)
            await self._db.commit()

        return HumanReviewRequest(
            review_id=review_id,
            status="pending",
            estimated_resolution_days=14,
            user_rights=[
                "Right to human review under Art. 22(3)",
                "Right to contest the decision",
                "Right to obtain human intervention",
                "Right to express your point of view",
            ],
            created_at=db_record.created_at,
        )

    async def check_profiling_opt_out(
        self,
        user_id: str,
        tenant_id: int,
        profiling_type: ProfilingType,
    ) -> bool:
        """
        Check if user has opted out of profiling (Art. 21).

        GDPR Art. 21: "The data subject shall have the right to object, on
        grounds relating to his or her particular situation, at any time to
        processing of personal data concerning him or her which is based on
        point (e) or (f) of Article 6(1), including profiling based on those
        provisions."

        Args:
            user_id: Data subject ID
            tenant_id: Tenant context
            profiling_type: Type of profiling to check

        Returns:
            True if user has opted out, False otherwise
        """
        # Weiger te antwoorden als de sessie in een ANDERE tenant staat (ADR-036 OP-155).
        #
        # Deze functie faalt open: geen rij betekent "geen bezwaar". Dat is juist zolang de
        # query alle rijen kan zien. Onder Row Level Security ziet een sessie alleen rijen van
        # de tenant in `app.current_tenant`; staat die op iets anders dan de `tenant_id` die
        # hier wordt meegegeven, dan komt er GEEN rij terug -- ongeacht of de betrokkene
        # bezwaar heeft gemaakt. Het antwoord "geen bezwaar" is dan geen meting maar een
        # gevolg van de verkeerde context, en profilering gaat door tegen een uitdrukkelijke
        # wens in (AVG art. 21).
        #
        # **Sinds 2026-09-16 OOK bij een LEGE context, op PostgreSQL.** Hier stond dat een
        # lege context onschuldig was omdat een worker of script er per definitie geen heeft.
        # Die redenering gold zolang `user_profiling_opt_outs` GEEN policy had. Sinds
        # `20260915_rls_resterende_tabellen.py` heeft die tabel er wel een, en dan betekent
        # een lege context precies hetzelfde als een botsende: nul rijen, dus "geen bezwaar",
        # terwijl het juiste antwoord "niet zichtbaar" is. De AVG-art.21-omkering zat dus nog
        # steeds open op exact de paden waarvoor het gat bewust was gelaten.
        #
        # Gevonden door BEIDE Gate 2-reviews van 2026-09-15, onafhankelijk van elkaar, en
        # terecht: deze migratie IS de voorbereiding waar het oude commentaar naar verwees.
        #
        # ALLEEN op PostgreSQL. SQLite kent geen RLS, dus daar is een lege context echt
        # onschuldig en zouden de unit-tests anders massaal omvallen op iets wat daar niet
        # kan gebeuren. Zelfde afweging als `adopt_tenant` in `bypass_session.py`.
        #
        # Wat een aanroeper zonder verzoekcontext moet doen: de tenant AANNEMEN met
        # `adopt_tenant(db, tenant_id)` voor hij dit vraagt. Dat is wat de retentietaken en
        # de opstartlus sinds vandaag ook doen.
        try:
            from src.core.middleware.tenant_context import get_tenant_id

            context_tenant = get_tenant_id()
        except ImportError:  # pragma: no cover - alleen tijdens het opstarten van de module
            context_tenant = None

        bind = getattr(self._db, "bind", None)
        dialect = getattr(bind, "dialect", None)
        is_postgres = getattr(dialect, "name", None) == "postgresql"

        if context_tenant is not None and int(context_tenant) != int(tenant_id):
            raise ValueError(
                f"Bezwaar tegen profilering is niet vast te stellen: de sessie draait in tenant "
                f"{context_tenant} en er wordt gevraagd naar tenant {tenant_id}. Een leeg "
                "resultaat zou hier 'geen bezwaar' betekenen terwijl het 'niet zichtbaar' is "
                "(ADR-036 OP-155, AVG art. 21)."
            )
        if context_tenant is None and is_postgres:
            raise ValueError(
                "Bezwaar tegen profilering is niet vast te stellen: er is GEEN tenantcontext "
                f"gezet en `user_profiling_opt_outs` heeft een RLS-policy. De opzoeking voor "
                f"tenant {tenant_id} zou dan nul rijen geven, en dat leest als 'geen bezwaar' "
                "terwijl het 'niet zichtbaar' betekent. Neem de tenant aan met "
                "`adopt_tenant(db, tenant_id)` voor je dit vraagt (ADR-036 OP-155, AVG art. 21)."
            )

        result = await self._db.execute(
            select(UserProfilingOptOut).where(
                UserProfilingOptOut.user_id == user_id,
                UserProfilingOptOut.tenant_id == tenant_id,
                UserProfilingOptOut.profiling_type == profiling_type.value,
            )
        )
        opt_out = await _maybe_await(result.scalar_one_or_none())

        return bool(opt_out is not None and opt_out.opted_out)

    async def set_profiling_opt_out(
        self,
        user_id: str,
        tenant_id: int,
        profiling_type: ProfilingType,
        opt_out: bool,
    ) -> None:
        """
        Set user's profiling opt-out preference (Art. 21).

        Users have the right to object to profiling at any time.
        This method records their preference.

        Args:
            user_id: Data subject ID
            tenant_id: Tenant context
            profiling_type: Type of profiling
            opt_out: True to opt out, False to opt back in
        """
        # Check for existing record
        result = await self._db.execute(
            select(UserProfilingOptOut).where(
                UserProfilingOptOut.user_id == user_id,
                UserProfilingOptOut.tenant_id == tenant_id,
                UserProfilingOptOut.profiling_type == profiling_type.value,
            )
        )
        existing = await _maybe_await(result.scalar_one_or_none())
        if inspect.iscoroutine(existing):
            existing = await existing

        if existing:
            # Update existing record
            existing.opted_out = opt_out
        else:
            # Create new record
            new_record = UserProfilingOptOut(
                user_id=user_id,
                tenant_id=tenant_id,
                profiling_type=profiling_type.value,
                opted_out=opt_out,
            )
            self._db.add(new_record)

        await self._db.commit()

        # Log to audit
        user_id_int = int(user_id) if user_id and user_id.isdigit() else None
        async with best_effort(
            "ai_transparency audit log (ai.profiling_opt_out_changed)", db_session=self._db
        ):
            audit_entry = AuditLog(
                tenant_id=tenant_id,
                user_id=user_id_int,
                action="ai.profiling_opt_out_changed",
                resource=f"user:{user_id}",
                details={
                    "profiling_type": profiling_type.value,
                    "opted_out": opt_out,
                },
                event_type="gdpr_profiling_opt_out",
                threat_level="info",
                client_ip="unknown",
                endpoint="/api/gdpr/profiling-opt-out",
                description=(
                    f"User {'opted out of' if opt_out else 'opted in to'} "
                    f"{profiling_type.value} profiling"
                ),
                event_metadata={
                    "gdpr_article": "21",
                    "right": "object_to_profiling",
                },
            )
            # De tijdstempel wordt in `_populate_hash_chain` gezet, NA het slot (OP-110).
            await self._populate_hash_chain(audit_entry, tenant_id)
            self._db.add(audit_entry)
            await self._db.commit()


# Module exports
__all__ = [
    "AITransparencyService",
    "AIDecisionRecord",
    "HumanReviewRequest",
    "ProfilingType",
    "AITransparencyError",
    "ExplanationRequiredError",
]
