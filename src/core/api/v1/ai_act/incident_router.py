"""Incident Reporting API Router.

EU AI Act Compliance - Article 62 Incident Reporting
Endpoints for reporting and managing AI system incidents.

Routes:
    POST /api/v1/ai-act/incidents               - Report new incident
    GET  /api/v1/ai-act/incidents               - List incidents
    GET  /api/v1/ai-act/incidents/eu-reporting/pending - EU reporting queue
    GET  /api/v1/ai-act/incidents/{incident_id} - Get specific incident
"""

import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.dependencies import get_db
from src.core.api.v1.ai_act.dependencies import (
    IncidentReport,
    IncidentService,
    IncidentSeverity,
    IncidentStatus,
    requires_eu_reporting,
)
from src.core.auth.api_deps import UserResponse, get_current_user
import logging
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/ai-act", tags=["AI Act Compliance"])


class IncidentCreateRequest(BaseModel):
    severity: str = Field(..., examples=["high"])
    agent_id: str = Field(..., examples=["agent-001"])
    agent_name: str = Field(default="Unknown Agent", examples=["Recruitment Bot"])
    description: str = Field(..., examples=["Generated biased output"])
    details: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type
    incident_type: str | None = Field(default=None, examples=["bias_detected"])

    @field_validator("severity")
    @classmethod
    def validate_severity(cls, v: str) -> str:
        allowed = {"low", "medium", "high", "critical"}
        if v.lower() not in allowed:
            raise ValueError(f"severity must be one of: {allowed}")
        return v.lower()


def _db_row_to_dict(row: Any) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Serialize IncidentReportDB ORM row to response dict."""
    return {
        "incident_id": str(row.id),
        "severity": row.severity,
        "status": row.resolution_status,
        "incident_type": row.incident_type,
        "agent_id": row.agent_id,
        "agent_name": row.agent_name,
        "description": row.description,
        "timestamp": row.created_at.isoformat() if row.created_at else None,
        "eu_reporting_required": row.eu_reporting_required,
        "eu_reported_at": row.eu_reported_at.isoformat() if row.eu_reported_at else None,
    }


@router.post(
    "/incidents",
    status_code=status.HTTP_201_CREATED,
    summary="Report AI Incident",
)
async def report_incident(
    request: IncidentCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Report a new AI incident (Article 62)."""
    try:
        svc = IncidentService(db=db, tenant_id=current_user.tenant_id)
        incident = IncidentReport(
            id=str(uuid.uuid4()),
            severity=IncidentSeverity(request.severity),
            status=IncidentStatus.REPORTED,
            agent_id=request.agent_id,
            agent_name=request.agent_name,
            description=request.description,
            details=request.details,
            eu_reporting_required=requires_eu_reporting(request.severity),
        )
        row = await svc.create_incident(incident, incident_type=request.incident_type)
        return _db_row_to_dict(row)
    except ValueError as e:
        logger.error("report_incident mislukt: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Ongeldig verzoek.")


@router.get("/incidents", summary="List AI Incidents")
async def get_incidents(
    incident_status: str | None = Query(default=None, alias="status"),
    severity: str | None = Query(default=None),
    agent_id: str | None = Query(default=None),
    limit: int = Query(default=50, le=500),
    offset: int = Query(default=0, ge=0),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """List all reported AI incidents."""
    svc = IncidentService(db=db, tenant_id=current_user.tenant_id)
    rows = await svc.list_incidents(
        status=incident_status,
        severity=severity,
        agent_id=agent_id,
        limit=limit,
        offset=offset,
    )
    return {"incidents": [_db_row_to_dict(r) for r in rows], "total": len(rows)}


@router.get("/incidents/eu-reporting/pending", summary="Get EU Reporting Queue")
async def get_eu_reporting_queue(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get incidents pending EU AI Office reporting (Article 62)."""
    svc = IncidentService(db=db, tenant_id=current_user.tenant_id)
    rows = await svc.get_eu_reporting_queue()
    return {"incidents": [_db_row_to_dict(r) for r in rows], "total": len(rows)}


@router.get("/incidents/{incident_id}", summary="Get Incident Details")
async def get_incident_details(
    incident_id: str,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get specific incident by ID."""
    svc = IncidentService(db=db, tenant_id=current_user.tenant_id)
    row = await svc.get_incident(incident_id)
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Incident {incident_id} not found",
        )
    return _db_row_to_dict(row)
