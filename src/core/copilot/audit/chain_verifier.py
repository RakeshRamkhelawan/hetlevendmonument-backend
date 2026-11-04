"""
ChainVerifier Service

Verifies the integrity of the AI Copilot audit log hash chain (SHA-256).
Each CouncilDecisionRow contains:
- decision_hash: SHA-256 over canonical JSON
- previous_decision_hash: Hash of the previous decision in the chain

Sprint 7, Task H1
"""

import hashlib
import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.core.copilot.council.models import CouncilDecisionRow, OfficerVerdictRow
from src.core.copilot.council.types import ProposalTrigger


@dataclass
class BrokenLink:
    """Represents a break in the hash chain."""

    decision_id: str
    expected_hash: str | None
    actual_hash: str | None
    reason: str


@dataclass
class ChainVerificationResult:
    """Result of verifying the hash chain for a tenant."""

    is_valid: bool
    total_entries: int
    verified_entries: int
    broken_links: list[BrokenLink]
    verification_time_ms: float
    tenant_id: int
    checked_at: datetime


class ChainVerifier:
    """
    Verifies SHA-256 hash chain integrity for copilot council decisions.

    Streams decisions in chunks to prevent OOM errors (Beslissing 1).
    """

    def __init__(self, db_session: AsyncSession) -> None:
        self.db = db_session

    def _compute_officer_verdicts_hash(self, verdicts: list[OfficerVerdictRow]) -> str:
        """Compute hash over officer verdicts (must match audit_writer.py)."""
        sorted_verdicts = sorted(verdicts, key=lambda v: v.officer_name)
        verdicts_list = []
        for v in sorted_verdicts:
            verdicts_list.append(
                {
                    "officer_name": v.officer_name,
                    "officer_version": v.officer_version,
                    "verdict": v.verdict,
                    "reason_code": v.reason_code,
                    "reason_text": v.reason_text,
                    "evidence": v.evidence,
                    "deliberation_ms": v.deliberation_ms,
                    "confidence": v.confidence,
                    "used_cache": v.used_cache,
                    "verdict_id": str(v.verdict_id),
                }
            )

        canonical = json.dumps(verdicts_list, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _compute_canonical_json(
        self, row: CouncilDecisionRow, previous_hash: str | None, trigger: str
    ) -> str:
        """Produce canonical JSON representation of the decision (must match audit_writer.py)."""
        data = {
            "proposal_id": str(row.proposal_id),
            "tenant_id": row.tenant_id,
            "user_id": row.user_id,
            "action_type": row.action_type,
            "action_params": row.action_params,
            "message": row.message,
            "reasoning": row.reasoning,
            "confidence": round(float(row.confidence), 4),
            "model_id": row.model_id,
            "model_version": row.model_version,
            "trigger": trigger,
            "final_verdict": row.verdict,
            "explanation_for_user": row.explanation_for_user,
            "officer_verdicts_hash": self._compute_officer_verdicts_hash(row.officer_verdicts),
            "previous_hash": previous_hash,
        }
        return json.dumps(data, sort_keys=True, separators=(",", ":"))

    def _compute_decision_hash(self, canonical: str) -> str:
        """SHA-256 over canonical JSON."""
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    # OOM guard: refuse to load more than this many rows into memory at once.
    # For larger chains, callers must paginate via from_dt/to_dt range slices.
    CHAIN_VERIFY_MAX_ROWS = 50_000

    async def verify_tenant_chain(
        self,
        tenant_id: int,
        from_dt: datetime | None = None,
        to_dt: datetime | None = None,
    ) -> ChainVerificationResult:
        """Verifies the chain for a specific tenant using hash-link traversal.

        Traversal follows previous_decision_hash links (linked-list), NOT
        timestamp ordering. Concurrent writes can produce identical timestamps,
        making ORDER BY timestamp non-deterministic and causing false broken-link
        reports (B-004, CLAUDE.md sec 11.5).

        When from_dt/to_dt are supplied, the verifier treats the earliest record
        in the window (whose previous_decision_hash is absent from the fetched
        set) as the window-start and skips inter-record link checking only for
        that first boundary record.
        """
        start_time = time.perf_counter()

        stmt = (
            select(CouncilDecisionRow)
            .where(CouncilDecisionRow.tenant_id == tenant_id)
            .options(selectinload(CouncilDecisionRow.officer_verdicts))
        )
        if from_dt:
            stmt = stmt.where(CouncilDecisionRow.timestamp >= from_dt)
        if to_dt:
            stmt = stmt.where(CouncilDecisionRow.timestamp <= to_dt)

        result = await self.db.execute(stmt)
        all_rows = result.scalars().all()

        if len(all_rows) > self.CHAIN_VERIFY_MAX_ROWS:
            return ChainVerificationResult(
                is_valid=False,
                total_entries=len(all_rows),
                verified_entries=0,
                broken_links=[
                    BrokenLink(
                        decision_id="N/A",
                        expected_hash=None,
                        actual_hash=None,
                        reason=(
                            f"Chain too large to verify in one pass "
                            f"({len(all_rows)} > {self.CHAIN_VERIFY_MAX_ROWS}). "
                            "Use from_dt/to_dt to narrow the range."
                        ),
                    )
                ],
                verification_time_ms=(time.perf_counter() - start_time) * 1000,
                tenant_id=tenant_id,
                checked_at=datetime.now(timezone.utc),
            )

        # Build lookup dicts for O(1) traversal.
        by_hash: dict[str, CouncilDecisionRow] = {r.decision_hash: r for r in all_rows}
        # Maps previous_decision_hash -> the row that has that value as its predecessor.
        next_by_prev: dict[str | None, CouncilDecisionRow] = {
            r.previous_decision_hash: r for r in all_rows
        }
        all_hashes: set[str] = {r.decision_hash for r in all_rows}

        # Find the start of the chain in this window:
        # - Full chain: the genesis record (previous_decision_hash is None).
        # - Range window: the record whose previous_decision_hash is absent from the window.
        start_record = next(
            (r for r in all_rows if r.previous_decision_hash is None),
            None,
        )
        if start_record is None:
            # Range query: find the record whose predecessor is outside the window.
            start_record = next(
                (r for r in all_rows if r.previous_decision_hash not in all_hashes),
                None,
            )

        if start_record is None and all_rows:
            # Every record's predecessor is present in the set -> circular chain.
            return ChainVerificationResult(
                is_valid=False,
                total_entries=len(all_rows),
                verified_entries=0,
                broken_links=[
                    BrokenLink(
                        decision_id="N/A",
                        expected_hash=None,
                        actual_hash=None,
                        reason="Circular chain detected: no genesis or window-start record found",
                    )
                ],
                verification_time_ms=(time.perf_counter() - start_time) * 1000,
                tenant_id=tenant_id,
                checked_at=datetime.now(timezone.utc),
            )

        # Walk the linked list in order.
        ordered: list[CouncilDecisionRow] = []
        seen: set[str] = set()
        current: CouncilDecisionRow | None = start_record
        while current is not None:
            if current.decision_hash in seen:
                # Cycle detected mid-traversal.
                break
            seen.add(current.decision_hash)
            ordered.append(current)
            current = next_by_prev.get(current.decision_hash)

        # We brute-force the trigger because it is not stored in the DB schema.
        possible_triggers = [t.value for t in ProposalTrigger]

        total = len(ordered)
        verified = 0
        broken_links: list[BrokenLink] = []
        is_window_start = True

        for row in ordered:
            # 1. Verify previous hash link.
            # Skip for the window-start record when using a date range filter,
            # because its predecessor may be outside the fetched window.
            link_check_required = not (
                is_window_start
                and row.previous_decision_hash is not None
                and row.previous_decision_hash not in all_hashes
            )
            is_window_start = False

            if link_check_required and row.previous_decision_hash is not None:
                predecessor = by_hash.get(row.previous_decision_hash)
                if predecessor is None:
                    broken_links.append(
                        BrokenLink(
                            decision_id=str(row.decision_id),
                            expected_hash=row.previous_decision_hash,
                            actual_hash=None,
                            reason="Predecessor record missing from chain",
                        )
                    )

            # 2. Verify current decision hash by recomputing.
            hash_matched = False
            for trigger in possible_triggers:
                canonical = self._compute_canonical_json(row, row.previous_decision_hash, trigger)
                computed = self._compute_decision_hash(canonical)
                if computed == row.decision_hash:
                    hash_matched = True
                    break

            if not hash_matched:
                broken_links.append(
                    BrokenLink(
                        decision_id=str(row.decision_id),
                        expected_hash=None,
                        actual_hash=row.decision_hash,
                        reason="Decision hash recomputation mismatch (tampering detected)",
                    )
                )
            else:
                verified += 1

        # Detect rows unreachable from genesis (predecessor was deleted, creating a gap)
        visited_hashes = {r.decision_hash for r in ordered}
        for row in all_rows:
            if row.decision_hash not in visited_hashes:
                broken_links.append(
                    BrokenLink(
                        decision_id=str(row.decision_id),
                        expected_hash=row.previous_decision_hash,
                        actual_hash=row.decision_hash,
                        reason="Previous hash link mismatch: predecessor record not found in chain",
                    )
                )

        return ChainVerificationResult(
            is_valid=len(broken_links) == 0,
            total_entries=total,
            verified_entries=verified,
            broken_links=broken_links,
            verification_time_ms=(time.perf_counter() - start_time) * 1000,
            tenant_id=tenant_id,
            checked_at=datetime.now(timezone.utc),
        )
