"""Incident Service for EU AI Act Article 62 compliance.

Task 5: Serious Incident Reporting
Manages incident classification, storage, and EU reporting determination.

Reference: Regulation (EU) 2024/1689 Article 62
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

if TYPE_CHECKING:
    from src.core.governance.models import IncidentReportDB


class IncidentSeverity(str, Enum):
    """Incident severity levels per EU AI Act."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentStatus(str, Enum):
    """Incident status workflow."""

    REPORTED = "reported"
    UNDER_INVESTIGATION = "under_investigation"
    RESOLVED = "resolved"
    CLOSED = "closed"


@dataclass
class IncidentReport:
    """AI Act incident report.

    Attributes:
        id: Unique incident identifier
        severity: Incident severity level
        status: Current status in workflow
        agent_id: ID of agent involved
        agent_name: Name of agent involved
        description: Human-readable description
        details: Additional structured data (may include 'incident_type' key)
        timestamp: When incident was reported
        eu_reporting_required: Whether EU AI Office must be notified
        eu_reported_at: When EU notification was sent (if applicable)
    """

    id: str
    severity: IncidentSeverity
    status: IncidentStatus
    agent_id: str
    agent_name: str
    description: str
    details: dict[str, Any] = field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    eu_reporting_required: bool = False
    eu_reported_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Convert to dictionary for API serialization."""
        return {
            "incident_id": self.id,
            "severity": self.severity.value,
            "status": self.status.value,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "description": self.description,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
            "eu_reporting_required": self.eu_reporting_required,
            "eu_reported_at": self.eu_reported_at.isoformat() if self.eu_reported_at else None,
        }


def classify_severity(
    impact: str,
    scope: str,
    reversibility: bool,
) -> str:
    """Classify incident severity based on impact criteria.

    Per EU AI Act Article 62, considers:
    - Impact: death, serious injury, material harm, minor harm, none
    - Scope: widespread, multiple users, single user
    - Reversibility: can the harm be undone
    """
    if impact in ("death", "serious_injury") and scope in (
        "widespread",
        "multiple_users",
    ):
        return IncidentSeverity.CRITICAL.value

    if impact == "death":
        return IncidentSeverity.CRITICAL.value

    if impact == "serious_injury":
        return IncidentSeverity.HIGH.value

    if scope == "widespread" and not reversibility:
        return IncidentSeverity.HIGH.value

    if impact == "material_harm" and scope in ("widespread", "multiple_users"):
        return IncidentSeverity.HIGH.value

    if impact == "material_harm":
        return IncidentSeverity.MEDIUM.value

    if impact == "minor_harm" and scope in ("multiple_users", "widespread"):
        return IncidentSeverity.MEDIUM.value

    return IncidentSeverity.LOW.value


def requires_eu_reporting(severity: str) -> bool:
    """Determine if incident requires EU AI Office reporting.

    Per Article 62: Serious incidents must be reported to market
    surveillance authorities and EU AI Office immediately.
    """
    return severity in (IncidentSeverity.CRITICAL.value, IncidentSeverity.HIGH.value)


class IncidentService:
    """Async DB-backed incident service (replaces _incident_store singleton).

    Always inject tenant_id from JWT context -- never from request body.
    EU AI Act 10-year retention: use soft-delete only (deleted_at column),
    NEVER call hard delete on ai_act_incident_reports.
    """

    def __init__(self, db: AsyncSession, tenant_id: int) -> None:
        self._db = db
        self._tenant_id = tenant_id

    async def create_incident(
        self,
        incident: IncidentReport,
        incident_type: str | None = None,
    ) -> "IncidentReportDB":
        """Persist incident report to DB.

        Args:
            incident: Incident dataclass with severity, description, etc.
            incident_type: Category (e.g. 'governance_violation', 'bias_detected').
                           Falls back to details['incident_type'] or 'unclassified'.
        """
        from src.core.governance.models import IncidentReportDB

        resolved_type = incident_type or incident.details.get("incident_type") or "unclassified"
        db_row = IncidentReportDB(
            tenant_id=self._tenant_id,
            incident_type=resolved_type,
            severity=incident.severity.value,
            description=incident.description,
            agent_id=incident.agent_id,
            agent_name=incident.agent_name,
            eu_reporting_required=incident.eu_reporting_required,
            resolution_status=incident.status.value,
            incident_data=incident.details or None,
        )
        self._db.add(db_row)
        await self._db.commit()
        await self._db.refresh(db_row)
        return db_row

    async def list_incidents(
        self,
        status: str | None = None,
        severity: str | None = None,
        agent_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list["IncidentReportDB"]:
        """List non-deleted incidents for this tenant with optional filters."""
        from src.core.governance.models import IncidentReportDB

        q = (
            select(IncidentReportDB)
            .where(
                IncidentReportDB.tenant_id == self._tenant_id,
                IncidentReportDB.deleted_at.is_(None),
            )
            .order_by(IncidentReportDB.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        if status:
            q = q.where(IncidentReportDB.resolution_status == status)
        if severity:
            q = q.where(IncidentReportDB.severity == severity)
        if agent_id:
            q = q.where(IncidentReportDB.agent_id == agent_id)
        result = await self._db.execute(q)
        return list(result.scalars().all())

    async def get_incident(self, incident_id: str) -> "IncidentReportDB | None":
        """Retrieve non-deleted incident by UUID string."""
        from uuid import UUID as _UUID

        from src.core.governance.models import IncidentReportDB

        try:
            uid = _UUID(incident_id)
        except ValueError:
            return None
        result = await self._db.execute(
            select(IncidentReportDB).where(
                IncidentReportDB.id == uid,
                IncidentReportDB.tenant_id == self._tenant_id,
                IncidentReportDB.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def update_status(self, incident_id: str, new_status: str) -> "IncidentReportDB | None":
        """Update resolution_status of an incident."""
        row = await self.get_incident(incident_id)
        if not row:
            return None
        row.resolution_status = new_status
        if new_status == IncidentStatus.RESOLVED.value:
            row.resolved_at = datetime.now(timezone.utc)
        else:
            row.resolved_at = None
        await self._db.commit()
        await self._db.refresh(row)
        return row

    async def mark_eu_reported(self, incident_id: str) -> "IncidentReportDB | None":
        """Mark incident as reported to EU AI Office."""
        row = await self.get_incident(incident_id)
        if not row:
            return None
        row.eu_reported_at = datetime.now(timezone.utc)
        await self._db.commit()
        await self._db.refresh(row)
        return row

    async def get_eu_reporting_queue(self) -> list["IncidentReportDB"]:
        """Get incidents pending EU reporting (HIGH/CRITICAL, not yet reported)."""
        from src.core.governance.models import IncidentReportDB

        result = await self._db.execute(
            select(IncidentReportDB)
            .where(
                IncidentReportDB.tenant_id == self._tenant_id,
                IncidentReportDB.eu_reporting_required.is_(True),
                IncidentReportDB.eu_reported_at.is_(None),
                IncidentReportDB.deleted_at.is_(None),
            )
            .order_by(IncidentReportDB.created_at.desc())
        )
        return list(result.scalars().all())
