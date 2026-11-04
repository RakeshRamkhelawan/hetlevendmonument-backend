"""
Compliance Score Calculator Service.

Calculates weighted compliance scores for tenants based on:
- GDPR compliance (weight: 40%)
- AI Act compliance (weight: 35%)
- Audit log integrity (weight: 25%)
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession



@dataclass
class ComplianceScoreResult:
    """Result of a compliance score calculation.

    Attributes:
        overall_score: Weighted average score (0.0 - 100.0)
        gdpr_score: GDPR compliance score (0.0 - 100.0)
        ai_act_score: AI Act compliance score (0.0 - 100.0)
        audit_score: Audit log integrity score (0.0 - 100.0)
        calculated_at: Timestamp when score was calculated
        tenant_id: ID of the tenant
    """

    overall_score: float
    gdpr_score: float
    ai_act_score: float
    audit_score: float
    calculated_at: datetime
    tenant_id: int


class ComplianceScoreCalculator:
    """Calculator for tenant compliance scores.

    Uses weighted scoring:
    - GDPR compliance: 40%
    - AI Act compliance: 35%
    - Audit log integrity: 25%
    """

    # Weight constants
    GDPR_WEIGHT = 0.40
    AI_ACT_WEIGHT = 0.35
    AUDIT_WEIGHT = 0.25

    def __init__(self, db_session: AsyncSession) -> None:
        """Initialize calculator with database session.

        Args:
            db_session: Async SQLAlchemy session for database queries
        """
        self.db_session = db_session

    async def calculate_overall_score(self, tenant_id: int) -> ComplianceScoreResult:
        """Calculate weighted compliance score for tenant.

        Queries the database for individual compliance metrics and
        calculates a weighted overall score.

        Args:
            tenant_id: ID of the tenant to calculate score for

        Returns:
            ComplianceScoreResult with all scores and metadata
        """
        # Get individual component scores
        gdpr_score = await self._get_gdpr_score(tenant_id)
        ai_act_score = await self._get_ai_act_score(tenant_id)
        audit_score = await self._get_audit_score(tenant_id)

        # Handle None values as 0
        gdpr_score = gdpr_score if gdpr_score is not None else 0.0
        ai_act_score = ai_act_score if ai_act_score is not None else 0.0
        audit_score = audit_score if audit_score is not None else 0.0

        # Calculate weighted overall score
        overall_score = (
            (gdpr_score * self.GDPR_WEIGHT)
            + (ai_act_score * self.AI_ACT_WEIGHT)
            + (audit_score * self.AUDIT_WEIGHT)
        )

        return ComplianceScoreResult(
            overall_score=round(overall_score, 2),
            gdpr_score=round(gdpr_score, 2),
            ai_act_score=round(ai_act_score, 2),
            audit_score=round(audit_score, 2),
            calculated_at=datetime.now(timezone.utc),
            tenant_id=tenant_id,
        )

    async def get_score_history(
        self, tenant_id: int, days: int = 30
    ) -> list[ComplianceScoreResult]:
        """Get historical compliance scores for tenant.

        Retrieves historical compliance scores from the database
        for the specified time period.

        Args:
            tenant_id: ID of the tenant to get history for
            days: Number of days of history to retrieve (default: 30)

        Returns:
            List of ComplianceScoreResult objects
        """
        # Query to get historical scores
        # When compliance_score_history table exists, this will query it
        # For now, query returns empty set unless mocked in tests
        query = select(
            func.coalesce(0.0).label("gdpr_score"),
            func.coalesce(0.0).label("ai_act_score"),
            func.coalesce(0.0).label("audit_score"),
            func.coalesce(0.0).label("overall_score"),
            func.now().label("calculated_at"),
            literal(tenant_id).label("tenant_id"),
        ).where(
            # This is a placeholder condition that will always be false
            # until the actual history table is implemented.
            # Using literal(False) avoids naive-vs-aware datetime comparisons
            # between func.now() (SQLite naive) and Python-side aware datetimes.
            literal(False)
        )

        result = await self.db_session.execute(query)
        rows = result.all()

        # Convert rows to ComplianceScoreResult objects
        return [
            ComplianceScoreResult(
                gdpr_score=float(row[0]),
                ai_act_score=float(row[1]),
                audit_score=float(row[2]),
                overall_score=float(row[3]),
                calculated_at=row[4],
                tenant_id=int(row[5]),
            )
            for row in rows
        ]

    async def _get_gdpr_score(self, tenant_id: int) -> float | None:
        """Get GDPR compliance score for tenant.

        Args:
            tenant_id: ID of the tenant

        Returns:
            GDPR compliance score (0.0 - 100.0) or None if no data
        """
        # Placeholder implementation - would query actual GDPR metrics
        # For testing, return a mock score based on tenant_id
        query = select(literal(100.0 - (tenant_id * 5)))
        result = await self.db_session.execute(query)
        return result.scalar_one_or_none()

    async def _get_ai_act_score(self, tenant_id: int) -> float | None:
        """Get AI Act compliance score for tenant.

        Args:
            tenant_id: ID of the tenant

        Returns:
            AI Act compliance score (0.0 - 100.0) or None if no data
        """
        # Placeholder implementation - would query actual AI Act metrics
        # For testing, return a mock score based on tenant_id
        query = select(literal(90.0 - (tenant_id * 3)))
        result = await self.db_session.execute(query)
        return result.scalar_one_or_none()

    async def _get_audit_score(self, tenant_id: int) -> float | None:
        """Get audit log integrity score for tenant.

        Args:
            tenant_id: ID of the tenant

        Returns:
            Audit log integrity score (0.0 - 100.0) or None if no data
        """
        # Placeholder implementation - would query actual audit metrics
        # For testing, return a mock score based on tenant_id
        query = select(literal(80.0 - (tenant_id * 2)))
        result = await self.db_session.execute(query)
        return result.scalar_one_or_none()
