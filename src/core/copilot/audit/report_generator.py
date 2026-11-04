import hashlib
import json
import logging
from datetime import datetime
from uuid import UUID
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.copilot.api.schemas import AuditReportSummary
from src.core.copilot.council.models import CouncilDecisionRow
from src.core.copilot.council.types import (
    DataClassification,
    DecisionVerdict,
    OfficerVerdict,
    Proposal,
    ProposalTrigger,
    VerdictType,
)
from src.core.copilot.audit.pdf_renderer import render_report_pdf
from src.core.copilot.audit.json_signer import sign_json
from src.core.copilot.api.report_renderer import _percentile

logger = logging.getLogger(__name__)


class AuditReportGenerator:
    """Generates verifiable audit reports in PDF and signed JSON formats."""

    def __init__(self, db: AsyncSession):
        self.db = db

    def _reconstruct_verdicts(self, row: CouncilDecisionRow) -> tuple[OfficerVerdict, ...]:
        """Convert DB rows back to OfficerVerdict objects for hash verification."""
        return tuple(
            OfficerVerdict(
                officer_name=v.officer_name,
                officer_version=v.officer_version,
                verdict=VerdictType(v.verdict),
                reason_code=v.reason_code,
                reason_text=v.reason_text,
                evidence=v.evidence,
                deliberation_ms=v.deliberation_ms,
                confidence=v.confidence,
                used_cache=v.used_cache,
                verdict_id=v.verdict_id,
            )
            for v in row.officer_verdicts
        )

    def _reconstruct_proposal(self, row: CouncilDecisionRow) -> Proposal:
        """Convert DB row back to Proposal object for hash verification."""
        return Proposal(
            tenant_id=row.tenant_id,
            user_id=row.user_id,
            trigger=ProposalTrigger(row.trigger),
            action_type=row.action_type,
            action_params=row.action_params,
            message=row.message,
            reasoning=row.reasoning,
            data_classification=DataClassification(row.data_classification),
            confidence=row.confidence,
            model_id=row.model_id,
            model_version=row.model_version,
            context_snapshot={},  # Not stored in DB row, and not part of the hash
            proposal_id=row.proposal_id,
            timestamp=row.timestamp,
        )

    def _verify_record(self, row: CouncilDecisionRow, previous_hash: str | None) -> bool:
        """Re-calculate and verify the decision hash of a single record."""
        from src.core.copilot.council.audit_writer import CouncilAuditWriter

        # We instantiate a minimal writer just for the hashing logic
        writer = CouncilAuditWriter(db_session_factory=lambda: None)  # type: ignore[arg-type, return-value]

        proposal = self._reconstruct_proposal(row)
        verdicts = self._reconstruct_verdicts(row)

        # 1. Verify officer_verdicts_hash
        actual_ov_hash = writer.compute_officer_verdicts_hash(verdicts)
        if actual_ov_hash != row.officer_verdicts_hash:
            logger.warning(
                "audit_integrity.record_verdict_tampered",
                extra={"decision_id": str(row.decision_id)},
            )
            return False

        # 2. Verify decision_hash
        canonical = writer.compute_canonical_json(
            proposal=proposal,
            officer_verdicts=verdicts,
            final_verdict=DecisionVerdict(row.verdict),
            previous_hash=previous_hash,
            explanation_for_user=row.explanation_for_user,
        )
        actual_decision_hash = writer.compute_decision_hash(canonical)

        if actual_decision_hash != row.decision_hash:
            logger.warning(
                "audit_integrity.record_content_tampered",
                extra={"decision_id": str(row.decision_id)},
            )
            return False

        return True

    async def _build_summary(
        self, tenant_id: int, from_date: datetime, to_date: datetime
    ) -> tuple[
        AuditReportSummary, list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    ]:  # TODO(TYPE): replace Any with concrete type
        """Build summary using memory-safe streaming and integrity verification."""
        stmt = (
            select(CouncilDecisionRow)
            .options(selectinload(CouncilDecisionRow.officer_verdicts))
            .where(
                CouncilDecisionRow.tenant_id == tenant_id,
                CouncilDecisionRow.timestamp >= from_date,
                CouncilDecisionRow.timestamp <= to_date,
            )
            .order_by(CouncilDecisionRow.timestamp.asc())
        )

        total = 0
        by_verdict: dict[str, int] = {}
        by_action_type: dict[str, int] = {}
        latencies: list[int] = []
        hash_chain_valid = True
        previous_hash: str | None = None
        raw_data = []

        result = await self.db.stream(stmt.execution_options(yield_per=1000))
        async for row in result.scalars():
            total += 1
            by_verdict[row.verdict] = by_verdict.get(row.verdict, 0) + 1
            by_action_type[row.action_type] = by_action_type.get(row.action_type, 0) + 1
            latencies.append(row.deliberation_ms)

            # Record-level and Chain-level verification (EU AI Act Art. 12)
            is_valid = self._verify_record(row, previous_hash)
            if not is_valid:
                hash_chain_valid = False

            if previous_hash is not None and row.previous_decision_hash != previous_hash:
                hash_chain_valid = False

            previous_hash = row.decision_hash

            raw_data.append(
                {
                    "decision_id": str(row.decision_id),
                    "timestamp": row.timestamp.isoformat(),
                    "verdict": row.verdict,
                    "action_type": row.action_type,
                    "deliberation_ms": row.deliberation_ms,
                    "decision_hash": row.decision_hash,
                    "previous_decision_hash": row.previous_decision_hash,
                    "integrity_valid": is_valid,
                }
            )

        latencies_sorted = sorted(latencies) if latencies else [0]
        p50 = _percentile(latencies_sorted, 0.5)
        p95 = _percentile(latencies_sorted, 0.95)
        p99 = _percentile(latencies_sorted, 0.99)

        summary = AuditReportSummary(
            total_decisions=total,
            by_verdict=by_verdict,
            by_action_type=by_action_type,
            latency_p50_ms=p50,
            latency_p95_ms=p95,
            latency_p99_ms=p99,
            hash_chain_valid=hash_chain_valid,
        )
        return summary, raw_data

    async def generate_pdf(
        self, job_id: UUID, tenant_id: int, from_date: datetime, to_date: datetime
    ) -> bytes:
        summary, _ = await self._build_summary(tenant_id, from_date, to_date)
        import asyncio

        return await asyncio.to_thread(render_report_pdf, summary, tenant_id, from_date, to_date)

    async def generate_json(
        self, job_id: UUID, tenant_id: int, from_date: datetime, to_date: datetime
    ) -> str:
        summary, raw_data = await self._build_summary(tenant_id, from_date, to_date)

        data = {
            "tenant_id": tenant_id,
            "job_id": str(job_id),
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
            "summary": summary.model_dump(),
            "decisions": raw_data,
        }

        signed_payload = sign_json(data)
        return json.dumps(signed_payload, sort_keys=True, separators=(",", ":"))
