"""Compliance domain dependencies (ADR-033).

Router-bestanden importeren hieruit in plaats van direct uit src.core.governance / src.core.database.
"""

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.auth.api_deps import get_current_user
from src.core.database.database import get_db
from src.core.governance.audit import AuditService
from src.core.governance.compliance_aggregation import ComplianceAggregationService
from src.core.governance.compliance_score import ComplianceScoreCalculator, ComplianceScoreResult
from src.core.governance.hash_chain import HashChainVerifier
from src.core.governance.models import AIDecision, AuditLog, DSARRequest
from src.core.governance.rate_limiter import (
    ai_transparency_limit,
    governance_read_limit,
    governance_write_limit,
)


async def get_score_service(
    db: AsyncSession = Depends(get_db),
) -> ComplianceScoreCalculator:
    return ComplianceScoreCalculator(db_session=db)


async def get_aggregation_service(
    db: AsyncSession = Depends(get_db),
) -> ComplianceAggregationService:
    return ComplianceAggregationService(db_session=db)


async def get_hash_chain_verifier(
    db: AsyncSession = Depends(get_db),
) -> HashChainVerifier:
    return HashChainVerifier(db_session=db)


__all__ = [
    "get_db",
    "get_current_user",
    "get_score_service",
    "get_aggregation_service",
    "get_hash_chain_verifier",
    "ai_transparency_limit",
    "governance_read_limit",
    "governance_write_limit",
    "ComplianceAggregationService",
    "ComplianceScoreCalculator",
    "ComplianceScoreResult",
    "HashChainVerifier",
    "AIDecision",
    "AuditLog",
    "AuditService",
    "DSARRequest",
]
