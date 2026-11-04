"""Art. 72 Authority Reporting.

EU AI Act Compliance - Article 72: Market surveillance authority reporting.
Generates incident and periodic reports for national market surveillance authorities.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database.database import Base


class AuthorityReportType(str, Enum):
    INCIDENT = "incident"  # Art. 62: Serious incidents
    PERIODIC = "periodic"  # Art. 72: Regular reporting
    CONFORMITY_ASSESSMENT = "conformity"  # Art. 43: Conformity assessment


class AuthorityReport(Base):
    """Art. 72: Report to market surveillance authority per tenant."""

    __tablename__ = "governance_authority_reports"

    id = Column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    # GEEN vreemde sleutel naar `tenants` (migratie 20261012_audit_geen_tenant_fk, AVG C): rapporten aan
    # een toezichthouder blijven bewaard en worden bij het opheffen van een tenant geanonimiseerd.
    tenant_id = Column(Integer, nullable=False, index=True)
    report_type = Column(String(50), nullable=False)
    authority_name = Column(String(200), nullable=False)
    content = Column(JSONB, nullable=False)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)


class AuthorityReporter:
    """Generates and stores reports for Dutch market surveillance authorities.

    Integrates with existing IncidentService (Art. 62) for incident reports.
    """

    # Dutch authorities
    AUTHORITY_AP = "Autoriteit Persoonsgegevens"
    AUTHORITY_ACM = "Autoriteit Consument & Markt"

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def report_incident(
        self,
        tenant_id: int,
        incident_type: str,
        agent_name: str,
        details: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        user_id: int | None = None,
    ) -> AuthorityReport:
        """Art. 72: Create an incident report for the authority.

        Args:
            tenant_id: Tenant context.
            incident_type: Type of incident (e.g. 'serious_incident').
            agent_name: Agent that caused the incident.
            details: Full incident payload.
            user_id: User creating the report (optional).

        Returns:
            The persisted AuthorityReport record.
        """
        requires_eu = details.get("eu_reporting_required", False)
        authority = self.AUTHORITY_AP if requires_eu else "internal"

        report = AuthorityReport(
            tenant_id=tenant_id,
            report_type=AuthorityReportType.INCIDENT,
            authority_name=authority,
            content={
                "incident_type": incident_type,
                "agent_name": agent_name,
                "severity": details.get("severity"),
                "description": details.get("description"),
                "eu_reporting_required": requires_eu,
                **{
                    k: v
                    for k, v in details.items()
                    if k not in ("severity", "description", "eu_reporting_required")
                },
            },
            created_by_user_id=user_id,
        )
        self._db.add(report)
        await self._db.flush()
        return report

    async def generate_periodic_report(
        self,
        tenant_id: int,
        period_start: datetime,
        period_end: datetime,
        summary: dict[str, Any],  # TODO(TYPE): replace Any with concrete type
        user_id: int | None = None,
    ) -> AuthorityReport:
        """Art. 72: Generate periodic compliance report."""
        report = AuthorityReport(
            tenant_id=tenant_id,
            report_type=AuthorityReportType.PERIODIC,
            authority_name=self.AUTHORITY_ACM,
            content={
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                **summary,
            },
            created_by_user_id=user_id,
        )
        self._db.add(report)
        await self._db.flush()
        return report
