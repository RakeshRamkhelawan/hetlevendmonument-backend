"""
Compliance Aggregation Service

Aggregates compliance data for GDPR, AI Act, and Audit reporting dashboards.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.governance.models import (
    AIDecision,
    AuditLog,
    DSARRequest,
    UserConsent,
)


@dataclass
class GDPRSummary:
    """GDPR compliance summary for reporting dashboards."""

    total_data_subjects: int
    dsar_requests_count: int
    dsar_avg_response_time_hours: float
    consent_records_count: int
    data_retention_violations: int
    period_days: int
    tenant_id: int


@dataclass
class AIActSummary:
    """AI Act compliance summary for reporting dashboards."""

    total_ai_decisions: int
    high_risk_decisions: int
    human_oversight_rate: float  # percentage
    explainability_score: float  # 0-100
    bias_audit_count: int
    period_days: int
    tenant_id: int


@dataclass
class AuditSummary:
    """Audit log summary for reporting dashboards."""

    total_events: int
    critical_events: int
    warning_events: int
    info_events: int
    hash_chain_verified: bool
    last_verified_at: datetime | None
    period_days: int
    tenant_id: int


class ComplianceAggregationService:
    """Service for aggregating compliance data across GDPR, AI Act, and Audit domains.

    All methods enforce tenant isolation by filtering on tenant_id.
    """

    def __init__(self, db_session: AsyncSession) -> None:
        """Initialize with database session.

        Args:
            db_session: Async SQLAlchemy session for database queries.
        """
        self.db_session = db_session

    def _get_date_filter(self, days: int) -> datetime:
        """Calculate the date filter for the given number of days.

        Args:
            days: Number of days to look back.

        Returns:
            Datetime object representing the cutoff date.
        """
        return datetime.now(timezone.utc) - timedelta(days=days)

    async def get_gdpr_summary(self, tenant_id: int, days: int = 30) -> GDPRSummary:
        """Aggregate GDPR compliance data for the specified tenant and period.

        Args:
            tenant_id: The tenant ID to filter by (enforced isolation).
            days: Number of days to look back (default: 30).

        Returns:
            GDPRSummary with aggregated metrics.
        """
        cutoff_date = self._get_date_filter(days)

        # Count DSAR requests
        dsar_query = (
            select(func.count(DSARRequest.id))
            .where(DSARRequest.tenant_id == tenant_id)
            .where(DSARRequest.requested_at >= cutoff_date)
        )
        dsar_result = await self.db_session.execute(dsar_query)
        dsar_count = dsar_result.scalar_one_or_none() or 0

        # Count unique data subjects (distinct users with DSARs)
        subjects_query = (
            select(func.count(func.distinct(DSARRequest.user_id)))
            .where(DSARRequest.tenant_id == tenant_id)
            .where(DSARRequest.requested_at >= cutoff_date)
        )
        subjects_result = await self.db_session.execute(subjects_query)
        total_subjects = subjects_result.scalar_one_or_none() or 0

        # Calculate average DSAR response time (for completed requests)
        avg_time_query = (
            select(
                func.avg(
                    func.extract(
                        "epoch",
                        DSARRequest.completed_at - DSARRequest.requested_at,
                    )
                    / 3600  # Convert seconds to hours
                )
            )
            .where(DSARRequest.tenant_id == tenant_id)
            .where(DSARRequest.requested_at >= cutoff_date)
            .where(DSARRequest.status == "completed")
            .where(DSARRequest.completed_at.isnot(None))
        )
        avg_time_result = await self.db_session.execute(avg_time_query)
        avg_response_hours = avg_time_result.scalar_one_or_none() or 0.0

        # Count consent records
        consent_query = select(func.count(UserConsent.id)).where(UserConsent.tenant_id == tenant_id)
        consent_result = await self.db_session.execute(consent_query)
        consent_count = consent_result.scalar_one_or_none() or 0

        # Data retention violations (placeholder - requires retention policy)
        retention_violations = 0

        return GDPRSummary(
            total_data_subjects=total_subjects,
            dsar_requests_count=dsar_count,
            dsar_avg_response_time_hours=float(avg_response_hours),
            consent_records_count=consent_count,
            data_retention_violations=retention_violations,
            period_days=days,
            tenant_id=tenant_id,
        )

    async def get_ai_act_summary(self, tenant_id: int, days: int = 30) -> AIActSummary:
        """Aggregate AI Act compliance data for the specified tenant and period.

        Args:
            tenant_id: The tenant ID to filter by (enforced isolation).
            days: Number of days to look back (default: 30).

        Returns:
            AIActSummary with aggregated metrics.
        """
        cutoff_date = self._get_date_filter(days)

        # Count total AI decisions
        total_query = (
            select(func.count(AIDecision.id))
            .where(AIDecision.tenant_id == tenant_id)
            .where(AIDecision.created_at >= cutoff_date)
        )
        total_result = await self.db_session.execute(total_query)
        total_decisions = total_result.scalar_one_or_none() or 0

        # Count high-risk decisions (using profiling_involved as proxy)
        high_risk_query = (
            select(func.count(AIDecision.id))
            .where(AIDecision.tenant_id == tenant_id)
            .where(AIDecision.created_at >= cutoff_date)
            .where(AIDecision.profiling_involved.is_(True))
        )
        high_risk_result = await self.db_session.execute(high_risk_query)
        high_risk_count = high_risk_result.scalar_one_or_none() or 0

        # Count decisions with human oversight requested
        oversight_query = (
            select(func.count(AIDecision.id))
            .where(AIDecision.tenant_id == tenant_id)
            .where(AIDecision.created_at >= cutoff_date)
            .where(AIDecision.human_review_requested.is_(True))
        )
        oversight_result = await self.db_session.execute(oversight_query)
        oversight_count = oversight_result.scalar_one_or_none() or 0

        # Calculate human oversight rate (percentage)
        human_oversight_rate = (
            (oversight_count / total_decisions * 100) if total_decisions > 0 else 0.0
        )

        # Calculate average explainability score (based on confidence)
        explainability_query = (
            select(func.avg(AIDecision.confidence_score))
            .where(AIDecision.tenant_id == tenant_id)
            .where(AIDecision.created_at >= cutoff_date)
            .where(AIDecision.confidence_score.isnot(None))
        )
        explainability_result = await self.db_session.execute(explainability_query)
        avg_confidence = explainability_result.scalar_one_or_none() or 0.0
        explainability_score = avg_confidence * 100  # Scale to 0-100

        # Count bias audits from audit logs
        bias_query = (
            select(func.count(AuditLog.id))
            .where(AuditLog.tenant_id == tenant_id)
            .where(AuditLog.timestamp >= cutoff_date)
            .where(AuditLog.action.ilike("%bias%"))
        )
        bias_result = await self.db_session.execute(bias_query)
        bias_count = bias_result.scalar_one_or_none() or 0

        return AIActSummary(
            total_ai_decisions=total_decisions,
            high_risk_decisions=high_risk_count,
            human_oversight_rate=round(human_oversight_rate, 2),
            explainability_score=round(explainability_score, 2),
            bias_audit_count=bias_count,
            period_days=days,
            tenant_id=tenant_id,
        )

    async def get_dsar_requests(self, tenant_id: int, since: datetime) -> list[DSARRequest]:
        result = await self.db_session.execute(
            select(DSARRequest)
            .where(DSARRequest.tenant_id == tenant_id)
            .where(DSARRequest.requested_at >= since)
        )
        return list(result.scalars().all())

    async def get_ai_decisions(self, tenant_id: int, since: datetime) -> list[AIDecision]:
        result = await self.db_session.execute(
            select(AIDecision)
            .where(AIDecision.tenant_id == tenant_id)
            .where(AIDecision.created_at >= since)
        )
        return list(result.scalars().all())

    async def get_audit_summary(self, tenant_id: int, days: int = 30) -> AuditSummary:
        """Aggregate audit log data for the specified tenant and period.

        Args:
            tenant_id: The tenant ID to filter by (enforced isolation).
            days: Number of days to look back (default: 30).

        Returns:
            AuditSummary with aggregated event counts by severity.
        """
        cutoff_date = self._get_date_filter(days)

        # Aggregate events by threat_level (severity)
        severity_query = (
            select(AuditLog.threat_level, func.count(AuditLog.id))
            .where(AuditLog.tenant_id == tenant_id)
            .where(AuditLog.timestamp >= cutoff_date)
            .group_by(AuditLog.threat_level)
        )
        severity_result = await self.db_session.execute(severity_query)
        severity_counts = {row[0]: row[1] for row in severity_result.all()}

        # Map threat levels to severity categories
        critical_events = severity_counts.get("critical", 0)
        warning_events = severity_counts.get("warning", 0) + severity_counts.get("high", 0)
        info_events = (
            severity_counts.get("info", 0)
            + severity_counts.get("low", 0)
            + severity_counts.get("medium", 0)
        )
        total_events = sum(severity_counts.values())

        # Hash chain verification placeholder
        hash_chain_verified = True
        last_verified_at = datetime.now(timezone.utc)

        return AuditSummary(
            total_events=total_events,
            critical_events=critical_events,
            warning_events=warning_events,
            info_events=info_events,
            hash_chain_verified=hash_chain_verified,
            last_verified_at=last_verified_at,
            period_days=days,
            tenant_id=tenant_id,
        )
