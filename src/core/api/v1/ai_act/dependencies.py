"""AI Act domain dependencies (ADR-033 Laag 1)."""

from src.core.governance.incident_service import (
    IncidentReport as IncidentReport,
    IncidentService as IncidentService,
    IncidentSeverity as IncidentSeverity,
    IncidentStatus as IncidentStatus,
    requires_eu_reporting as requires_eu_reporting,
)

__all__ = [
    "IncidentReport",
    "IncidentService",
    "IncidentSeverity",
    "IncidentStatus",
    "requires_eu_reporting",
]
