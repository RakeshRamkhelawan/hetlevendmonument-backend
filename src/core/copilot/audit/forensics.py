"""
HashChainVerifier - Forensic integrity check for the Agent Council audit chain.

Reconstructs the cryptographic chain from database records to detect
unauthorized tampering or data corruption.
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict
from typing import Any, Optional
from collections.abc import Callable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.copilot.council.models import CouncilDecisionRow, OfficerVerdictRow

logger = logging.getLogger(__name__)


class IntegrityReport:
    """Detailed report of a hash chain verification."""

    def __init__(self, tenant_id: int) -> None:
        self.tenant_id = tenant_id
        self.is_valid = True
        self.total_records = 0
        self.broken_indices: list[int] = []
        self.tampered_decision_ids: list[UUID] = []
        self.errors: list[str] = []

    def add_error(self, message: str, decision_id: Optional[UUID] = None) -> None:
        self.is_valid = False
        self.errors.append(message)
        if decision_id:
            self.tampered_decision_ids.append(decision_id)


class HashChainVerifier:
    """Forensic tool to verify audit integrity."""

    def __init__(self, db_session_factory: Callable[..., AsyncSession]) -> None:
        self._db_session_factory = db_session_factory

    async def verify_tenant_chain(self, tenant_id: int) -> IntegrityReport:
        """Verify the entire hash chain for a specific tenant."""
        report = IntegrityReport(tenant_id)
        
        async with self._db_session_factory() as session:
            # Fetch all decisions for this tenant, ordered by timestamp
            query = (
                select(CouncilDecisionRow)
                .where(CouncilDecisionRow.tenant_id == tenant_id)
                .order_by(CouncilDecisionRow.timestamp.asc())
            )
            result = await session.execute(query)
            rows = result.scalars().all()
            
            report.total_records = len(rows)
            previous_hash: Optional[str] = None
            
            for i, row in enumerate(rows):
                # 1. Verify link to previous record
                if row.previous_decision_hash != previous_hash:
                    report.add_error(
                        f"Chain break at record {i}: expected prev_hash={previous_hash}, "
                        f"got {row.previous_decision_hash}",
                        row.decision_id
                    )
                
                # 2. Verify record content (reconstruct hash)
                # Note: we need the officer verdicts for this
                v_query = (
                    select(OfficerVerdictRow)
                    .where(OfficerVerdictRow.decision_id == row.decision_id)
                    .order_by(OfficerVerdictRow.officer_name.asc())
                )
                v_result = await session.execute(v_query)
                v_rows = v_result.scalars().all()
                
                # Recompute officer verdicts hash
                v_data_list = []
                for v in v_rows:
                    v_dict = {
                        "officer_name": v.officer_name,
                        "officer_version": v.officer_version,
                        "verdict": v.verdict,
                        "reason_code": v.reason_code,
                        "reason_text": v.reason_text,
                        "evidence": v.evidence,
                        "deliberation_ms": v.deliberation_ms,
                        "confidence": v.confidence,
                        "used_cache": v.used_cache,
                        "verdict_id": str(v.verdict_id)
                    }
                    v_data_list.append(v_dict)
                
                v_canonical = json.dumps(v_data_list, sort_keys=True, separators=(",", ":"))
                v_hash = hashlib.sha256(v_canonical.encode("utf-8")).hexdigest()
                
                if row.officer_verdicts_hash != v_hash:
                    report.add_error(
                        f"Officer verdicts tampering detected at record {i}",
                        row.decision_id
                    )

                # Recompute decision hash
                decision_data = {
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
                    "trigger": row.trigger,
                    "final_verdict": row.verdict,
                    "explanation_for_user": row.explanation_for_user,
                    "officer_verdicts_hash": v_hash,
                    "previous_hash": previous_hash,
                }
                canonical = json.dumps(decision_data, sort_keys=True, separators=(",", ":"))
                expected_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
                
                if row.decision_hash != expected_hash:
                    report.add_error(
                        f"Content tampering detected at record {i}: expected hash={expected_hash}, "
                        f"got {row.decision_hash}",
                        row.decision_id
                    )
                
                # 3. Verify execution result hash (if success)
                if row.execution_status == "success" and row.result_hash is None:
                    report.add_error(
                        f"Missing result hash for successful execution at record {i}",
                        row.decision_id
                    )

                previous_hash = row.decision_hash
                
        return report
