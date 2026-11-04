"""
CouncilAuditWriter Service

Persists CouncilDecision + OfficerVerdicts to the database with a hash chain.
"""

import hashlib
import json
import logging
from dataclasses import asdict, replace
from typing import Any
import contextlib
from collections.abc import Callable
from uuid import UUID

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.copilot.council.metrics import AUDIT_WRITES_TOTAL, HASH_CHAIN_BREAKS_TOTAL
from src.core.copilot.council.models import CouncilDecisionRow, OfficerVerdictRow
from src.core.copilot.council.types import (
    CouncilDecision,
    DecisionVerdict,
    OfficerVerdict,
    Proposal,
)
from src.core.tool_broker.redaction import (
    redact_for_publication,
    safe_digest_result,
    value_digest,
)

logger = logging.getLogger(__name__)


class AuditWriteError(Exception):
    """Raised when writing the audit decision to the database fails."""


class HashChainBreakError(Exception):
    """Raised when the hash chain integrity is violated (tamper detection)."""


class CouncilAuditWriter:
    """Persists CouncilDecision + OfficerVerdicts to DB with hash chain."""

    def __init__(
        self, db_session_factory: Callable[[], contextlib.AbstractAsyncContextManager[AsyncSession]]
    ) -> None:
        self._db_session_factory = db_session_factory

    async def get_previous_hash(self, tenant_id: int) -> str | None:
        """Fetch the decision_hash of the most recent decision for the tenant."""
        async with self._db_session_factory() as session:
            query = (
                select(CouncilDecisionRow.decision_hash)
                .where(CouncilDecisionRow.tenant_id == tenant_id)
                .order_by(CouncilDecisionRow.timestamp.desc())
                .limit(1)
            )
            result = await session.execute(query)
            return result.scalar_one_or_none()

    def compute_officer_verdicts_hash(self, verdicts: tuple[OfficerVerdict, ...]) -> str:
        """
        Compute SHA-256 over concatenation of all officer verdicts.
        We sort them by officer_name for deterministic order.
        """
        sorted_verdicts = sorted(verdicts, key=lambda v: v.officer_name)
        verdicts_list = [asdict(v) for v in sorted_verdicts]
        # Convert UUIDs to strings
        for v in verdicts_list:
            v["verdict_id"] = str(v["verdict_id"])

        canonical = json.dumps(verdicts_list, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def compute_canonical_json(
        self,
        proposal: Proposal,
        officer_verdicts: tuple[OfficerVerdict, ...],
        final_verdict: DecisionVerdict,
        previous_hash: str | None,
        explanation_for_user: str,
    ) -> str:
        """
        Produce a canonical JSON representation of the decision for reproducible hashing.
        Includes action_params, reasoning and message to prevent undetected record tampering.
        Per CLAUDE.md rule 10: ASCII only.
        """
        data = {
            "proposal_id": str(proposal.proposal_id),
            "tenant_id": proposal.tenant_id,
            "user_id": proposal.user_id,
            "action_type": proposal.action_type,
            "action_params": proposal.action_params,
            "message": proposal.message,
            "reasoning": proposal.reasoning,
            "confidence": round(float(proposal.confidence), 4),
            "model_id": proposal.model_id,
            "model_version": proposal.model_version,
            "trigger": proposal.trigger.value,
            "final_verdict": final_verdict.value,
            "explanation_for_user": explanation_for_user,
            "officer_verdicts_hash": self.compute_officer_verdicts_hash(officer_verdicts),
            "previous_hash": previous_hash,
        }
        return json.dumps(data, sort_keys=True, separators=(",", ":"))

    def compute_decision_hash(self, canonical: str) -> str:
        """SHA-256 over canonical JSON."""
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    async def persist(
        self,
        decision: CouncilDecision,
        proposal: Proposal,
        verdicts: tuple[OfficerVerdict, ...],
        final_verdict: DecisionVerdict | None = None,
    ) -> None:
        """
        INSERT council_decisions + officer_verdicts in one transaction.

        Computes the hash chain under ``pg_advisory_xact_lock`` so that
        concurrent writes for the same tenant serialize and cannot fork
        the chain (ADR-019 H-5). The lock is transaction-scoped and is
        automatically released on commit/rollback.

        **`action_params` wordt hier gepseudonimiseerd (ADR-036 OP-33).** Deze dict is dezelfde
        die `copilot/service.py:418-425` als `payload` aan `execute_tool` geeft, en is dus door een
        taalmodel geschreven: elke sleutelnaam en elke waarde is aanvallerbeinvloed. Hij ging
        verbatim naar `council_decisions.action_params` (JSONB, NOT NULL) en verbatim in de
        gehashte canonieke JSON, terwijl voor dezelfde uitvoering in `tool_audit_logs.tool_input`
        een digest stond.

        **`message` wordt hier ook gepseudonimiseerd (ADR-036 D2-002/OP-38, sinds fix-sprint dag
        6, 2026-08-20).** `proposal.message` is vrije, door het taalmodel geschreven babbeltekst
        naar de eindgebruiker (`types.py:104`) -- net zo aanvallerbeinvloed als `action_params`,
        maar met een eigen primitief: `value_digest()` in plaats van `redact_for_publication()`,
        want `message` is een kale string, geen dict met een tool-vocabulaire om tegen te
        toetsen. Bewust NIET meegenomen in deze fix: `reasoning` en `decision.explanation_for_user`
        (zie OP-38 in het ADR-036-register) -- beide worden rechtstreeks aan de eindgebruiker
        geserveerd via `copilot/api/explanation_builder.py` onder AI Act art. 13/14
        (transparantie/menselijk toezicht); digesten zou die wettelijke uitlegbaarheid slopen.
        `message` staat in geen response-schema van die explainability-API en wordt uitsluitend
        gelezen door de drie verifiers hieronder, nooit voor menselijke weergave.

        **De redactie staat HIER, op de aanroepplek, en NOOIT in `compute_canonical_json()`.**
        Drie onafhankelijke verifiers herberekenen de hash uit de opgeslagen rij:
        `audit/chain_verifier.py:92`, `audit/report_generator.py:72-100` en `audit/forensics.py`.
        Zat de redactie in de hashfunctie, dan redigeren zij een AL geredigeerde waarde nog eens,
        komen op een andere hash uit en melden elke historische rij als gemanipuleerd.
        `tests/unit/copilot/test_council_persist_leaks_nothing.py::
        TestAVerifierRecomputingFromTheRowGetsTheStoredHash` legt dat vast, voor zowel
        `action_params` als `message`.

        Voor de sessie en dus voor de advisory lock, met opzet: zonder pseudonimiseringssleutel
        gooit `redact_for_publication`/`value_digest` een `RuntimeError`, en dan is er geen reden
        om eerst een per-tenant lock te nemen en die daarna terug te rollen. Fail-closed is hier
        de bedoeling -- dezelfde keuze als in `tool_broker/service.py`: liever geen auditregel dan
        een auditregel met klaartekst.
        """
        published_params = redact_for_publication(
            proposal.action_type,
            proposal.action_params,
            tenant_id=proposal.tenant_id,
            broker_keys=frozenset(),
        )
        # `broker_keys` is leeg: op dit pad injecteert de broker niets uit een executiecontext.
        # Alles in `action_params` komt uit de NLU-uitvoer.
        #
        # Lege message blijft leeg (net als `redact_for_publication` een `None`-waarde onder een
        # bekende sleutel ongedigest laat, `redaction.py:826-828`): een lege string draagt geen
        # persoonsgegeven, en `message=""` is de meest voorkomende waarde van elke aanroeper die
        # geen boodschap meegeeft (bv. `background_gate.py`'s default).
        published_message = (
            value_digest(proposal.message, tenant_id=proposal.tenant_id) if proposal.message else ""
        )
        #
        # `replace()` en niet muteren: `Proposal` is frozen, en de aanroeper mag zijn eigen dict
        # niet onder zich zien veranderen -- `service.py` geeft dezelfde `proposal` daarna aan
        # `execute_tool`, en DAAR moeten de echte waarden staan. Dit is precies de reden dat de
        # redactie niet in `ProposalBuilder` hoort: dan zou de tool zelf digests uitvoeren.
        redacted_proposal = replace(
            proposal, action_params=published_params, message=published_message
        )

        async with self._db_session_factory() as session:
            try:
                # Serialize per-tenant hash-chain writes (transaction-scoped lock).
                await session.execute(
                    text("SELECT pg_advisory_xact_lock(:tenant_lock)"),
                    {"tenant_lock": decision.tenant_id},
                )

                # Read previous hash INSIDE the lock to prevent TOCTOU race.
                previous_hash = await self._get_previous_hash_in_session(
                    session, decision.tenant_id
                )

                # Hash-chain integrity check (AI Act compliance).
                if decision.previous_decision_hash is not None and previous_hash is None:
                    HASH_CHAIN_BREAKS_TOTAL.labels(tenant_id=str(decision.tenant_id)).inc()
                    err = HashChainBreakError(
                        f"Hash chain break for tenant {decision.tenant_id}: "
                        f"decision claims previous_hash={decision.previous_decision_hash} "
                        f"but chain is empty"
                    )
                    logger.error(
                        "hash chain break detected tenant=%d expected=None got=%s",
                        decision.tenant_id,
                        decision.previous_decision_hash,
                        exc_info=err,
                        extra={
                            "tenant_id": decision.tenant_id,
                            "user_id": decision.user_id,
                        },
                    )
                    AUDIT_WRITES_TOTAL.labels(status="failed").inc()
                    raise err

                if (
                    previous_hash is not None
                    and decision.previous_decision_hash is not None
                    and decision.previous_decision_hash != previous_hash
                ):
                    HASH_CHAIN_BREAKS_TOTAL.labels(tenant_id=str(decision.tenant_id)).inc()
                    err = HashChainBreakError(
                        f"Hash chain break for tenant {decision.tenant_id}: "
                        f"expected={previous_hash} got={decision.previous_decision_hash}"
                    )
                    logger.error(
                        "hash chain break detected tenant=%d expected=%s got=%s",
                        decision.tenant_id,
                        previous_hash,
                        decision.previous_decision_hash,
                        exc_info=err,
                        extra={
                            "tenant_id": decision.tenant_id,
                            "user_id": decision.user_id,
                        },
                    )
                    AUDIT_WRITES_TOTAL.labels(status="failed").inc()
                    raise err

                canonical = self.compute_canonical_json(
                    proposal=redacted_proposal,
                    officer_verdicts=verdicts,
                    final_verdict=final_verdict or decision.verdict,
                    previous_hash=previous_hash,
                    explanation_for_user=decision.explanation_for_user,
                )
                decision_hash = self.compute_decision_hash(canonical)

                # CouncilDecision is frozen; bypass via object.__setattr__.
                object.__setattr__(decision, "previous_decision_hash", previous_hash)
                object.__setattr__(decision, "decision_hash", decision_hash)

                row = CouncilDecisionRow(
                    decision_id=decision.decision_id,
                    proposal_id=decision.proposal_id,
                    tenant_id=decision.tenant_id,
                    user_id=decision.user_id,
                    timestamp=func.clock_timestamp(),
                    verdict=decision.verdict.value,
                    trigger=proposal.trigger.value,
                    confidence=round(float(proposal.confidence), 4),
                    action_type=proposal.action_type,
                    # Geredigeerd, en DEZELFDE dict die in de canonieke JSON zit -- anders is de
                    # hash niet meer na te rekenen uit de rij.
                    action_params=published_params,
                    # Zelfde principe: DEZELFDE geredigeerde waarde als in de canonieke JSON
                    # (ADR-036 D2-002/OP-38, fix-sprint dag 6).
                    message=redacted_proposal.message,
                    data_classification=proposal.data_classification.value,
                    model_id=proposal.model_id,
                    model_version=proposal.model_version,
                    reasoning=proposal.reasoning,
                    explanation_for_user=decision.explanation_for_user,
                    deliberation_ms=decision.deliberation_ms,
                    hitl_request_id=decision.hitl_request_id,
                    modifications=decision.modifications,
                    officer_verdicts_hash=self.compute_officer_verdicts_hash(verdicts),
                    decision_hash=decision_hash,
                    previous_decision_hash=previous_hash,
                    execution_status="pending",
                )
                session.add(row)

                for v in verdicts:
                    v_row = OfficerVerdictRow(
                        verdict_id=v.verdict_id,
                        decision_id=decision.decision_id,
                        tenant_id=decision.tenant_id,
                        officer_name=v.officer_name,
                        officer_version=v.officer_version,
                        verdict=v.verdict.value,
                        reason_code=v.reason_code,
                        reason_text=v.reason_text,
                        evidence=v.evidence,
                        deliberation_ms=v.deliberation_ms,
                        confidence=v.confidence,
                        used_cache=v.used_cache,
                    )
                    session.add(v_row)

                await session.commit()
                AUDIT_WRITES_TOTAL.labels(status="success").inc()
            except HashChainBreakError:
                raise
            except Exception as exc:
                await session.rollback()
                AUDIT_WRITES_TOTAL.labels(status="failed").inc()
                logger.error(
                    "audit write failed tenant=%d: %s: %s",
                    decision.tenant_id,
                    type(exc).__name__,
                    exc,
                    exc_info=True,
                    extra={
                        "tenant_id": decision.tenant_id,
                        "user_id": decision.user_id,
                    },
                )
                raise AuditWriteError(f"Failed to persist council decision: {exc}") from exc

    async def _get_previous_hash_in_session(
        self,
        session: AsyncSession,
        tenant_id: int,
    ) -> str | None:
        """Fetch previous hash using an already-open session."""
        query = (
            select(CouncilDecisionRow.decision_hash)
            .where(CouncilDecisionRow.tenant_id == tenant_id)
            .order_by(CouncilDecisionRow.timestamp.desc())
            .limit(1)
        )
        result = await session.execute(query)
        return result.scalar_one_or_none()

    async def log_user_response(
        self,
        *,
        signal_id: object,
        tenant_id: int,
        user_id: int,
        action_type: str,
        params: dict[str, object],
    ) -> None:
        """Log a user response signal for audit trail completeness.

        Writes to the application log; a dedicated table can be added
        when DSAR response-volume requires indexed retrieval.
        """
        logger.info(
            "audit.user_response signal_id=%s tenant=%d user=%d action=%s",
            signal_id,
            tenant_id,
            user_id,
            action_type,
            extra={
                "tenant_id": tenant_id,
                "user_id": user_id,
                "signal_id": str(signal_id),
                "action_type": action_type,
                "params_keys": list(params.keys()),
            },
        )

    async def bind_execution_result(
        self,
        *,
        decision_id: UUID,
        tenant_id: int,
        result_data: dict[str, object],
        status: str = "success",
    ) -> None:
        """Hash and bind tool execution output to an existing decision record.

        Closes the forensic loop: Decision -> Execution -> Result Hash.

        Keyed HMAC (ADR-036 OP-39), niet kaal SHA-256: `result_data` komt rechtstreeks uit
        `execute_tool` en kan weinig entropie hebben (een boolean, een status, een klein getal).
        Een kale hash is dan een bevestigingsorakel voor wie de rij kan lezen -- hij kan
        kandidaten narekenen zonder de sleutel te kennen. Zelfde primitief als OP-29's
        `digest_result` op het tool_broker-pad.

        `safe_digest_result` en niet de rauwe `digest_result`: deze methode wordt ook aangeroepen
        vanuit een `except`-tak in `service.py` (het FALEN-pad van de aangeroepen tool). Een
        rauwe `digest_result` die daar een RuntimeError gooit bij een ontbrekende sleutel zou de
        ORIGINELE fout van de aanroeper overschaduwen -- exact de OP-29-les. `result_hash` is
        nullable, dus `None` is een geldige, best-effort uitkomst; `forensics.py` markeert een
        ontbrekende hash bij een geslaagde uitvoering al als een te onderzoeken afwijking.
        """
        digest = safe_digest_result(result_data, tenant_id=tenant_id)
        result_hash = digest["hmac"] if digest is not None else None

        async with self._db_session_factory() as session:
            try:
                stmt = (
                    update(CouncilDecisionRow)
                    .where(CouncilDecisionRow.decision_id == decision_id)
                    .where(CouncilDecisionRow.tenant_id == tenant_id)
                    .values(result_hash=result_hash, execution_status=status)
                )
                await session.execute(stmt)
                await session.commit()
                logger.info(
                    "audit.result_bound decision_id=%s status=%s hash=%s",
                    decision_id,
                    status,
                    result_hash[:8] if result_hash is not None else None,
                )
            except Exception as e:
                await session.rollback()
                logger.error(
                    "audit.bind_result_failed decision_id=%s: %s", decision_id, e, exc_info=True
                )
