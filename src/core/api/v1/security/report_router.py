"""Security report router -- GET /report, /events, /summary (ADR-033 Laag 1)."""

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.shared.production_logging import SafeLogger

from .dependencies import (
    OAuth2Scope,
    UserResponse,
    get_current_user,
    get_db,
    get_security_manager,
    require_scopes,
)

logger = SafeLogger(__name__)

report_router = APIRouter()


class SecurityEventResponse(BaseModel):
    """Security event response model."""

    event_id: str
    event_type: str
    severity: str
    source_ip: str
    user_id: str | None
    endpoint: str
    description: str
    timestamp: datetime


class SecurityReportResponse(BaseModel):
    """Security report response."""

    total_events: int
    recent_events_24h: int
    blocked_ips: int
    threat_distribution: dict[str, int]
    top_threat_sources: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    security_status: str
    last_updated: str


class SecuritySummaryResponse(BaseModel):
    """Security summary response model."""

    period_hours: int
    total_events: int
    events_by_severity: dict[str, int]
    events_by_type: dict[str, int]
    open_alerts: int
    security_status: str
    generated_at: str


@report_router.get("/report", response_model=SecurityReportResponse)
async def get_security_report(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
) -> SecurityReportResponse:
    """
    Get comprehensive security report.
    Requires: ADMIN permission
    """
    try:
        logger.info("User %s requesting security report", current_user.id)

        security_manager = get_security_manager()

        now = datetime.now(timezone.utc)
        last_24h = now - timedelta(hours=24)

        events_24h = [e for e in security_manager.security_events if e.timestamp > last_24h]

        threat_dist: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for event in security_manager.security_events:
            threat_type = (
                event.severity.name if hasattr(event.severity, "name") else str(event.severity)
            )
            threat_dist[threat_type] = threat_dist.get(threat_type, 0) + 1

        top_sources = sorted(
            [
                (
                    ip,
                    len([e for e in security_manager.security_events if e.source_ip == ip]),
                )
                for ip in {e.source_ip for e in security_manager.security_events}
            ],
            key=lambda x: x[1],
            reverse=True,
        )[:5]

        report = SecurityReportResponse(
            total_events=len(security_manager.security_events),
            recent_events_24h=len(events_24h),
            blocked_ips=len(security_manager.blocked_ips),
            threat_distribution=threat_dist,
            top_threat_sources=[{"ip": ip, "count": count} for ip, count in top_sources],
            security_status="healthy" if len(security_manager.blocked_ips) < 20 else "warning",
            last_updated=now.isoformat(),
        )

        logger.info("Security report generated for user %s", current_user.id)
        return report

    except Exception as e:
        logger.error("Failed to generate security report: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate report",
        )


@report_router.get("/events", response_model=list[SecurityEventResponse])
async def get_security_events(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
    limit: int = 50,
    # TODO(SP-VOLGENDE): offset parameter toevoegen (overgenomen zonder paginering uit security_endpoints.py)
    severity: str | None = None,
    event_type: str | None = None,
    hours: int = 24,
) -> list[SecurityEventResponse]:
    """
    Get recent security events.
    Requires: ADMIN permission
    """
    from src.core.security.security_manager import ThreatLevel

    try:
        logger.info("User %s requesting security events (limit=%s)", current_user.id, limit)

        if limit < 1 or limit > 1000:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Limit must be between 1 and 1000",
            )

        if hours < 1 or hours > 30 * 24:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Hours must be between 1 and 720",
            )

        security_manager = get_security_manager()
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)

        events = [e for e in security_manager.security_events if e.timestamp > cutoff]

        if severity:
            try:
                severity_level = ThreatLevel[severity.upper()]
                events = [e for e in events if e.severity == severity_level]
            except KeyError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid severity: %s" % severity,
                )

        if event_type:
            events = [e for e in events if e.event_type == event_type]

        events.sort(key=lambda x: x.timestamp, reverse=True)
        events = events[:limit]

        return [
            SecurityEventResponse(
                event_id=e.event_id,
                event_type=e.event_type,
                severity=e.severity.name if hasattr(e.severity, "name") else str(e.severity),
                source_ip=e.source_ip,
                user_id=e.user_id,
                endpoint=e.endpoint,
                description=e.description,
                timestamp=e.timestamp,
            )
            for e in events
        ]

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get security events: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve events",
        )


@report_router.get("/summary", response_model=SecuritySummaryResponse)
async def get_security_summary(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
    db: AsyncSession = Depends(get_db),
    hours: int = 24,
) -> SecuritySummaryResponse:
    """
    Get security summary with statistics.
    Requires: ADMIN permission
    """
    try:
        from src.core.security.security_audit_service import get_security_audit_service

        logger.info("User %s requesting security summary", current_user.id)

        service = get_security_audit_service()
        summary = await service.get_security_summary(db=db, hours=hours)

        return SecuritySummaryResponse(
            period_hours=summary.get("period_hours", hours),
            total_events=summary.get("total_events", 0),
            events_by_severity=summary.get("events_by_severity", {}),
            events_by_type=summary.get("events_by_type", {}),
            open_alerts=summary.get("open_alerts", 0),
            security_status=summary.get("security_status", "unknown"),
            generated_at=summary.get("generated_at", datetime.now(timezone.utc).isoformat()),
        )

    except Exception as e:
        logger.error("Failed to get security summary: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate security summary",
        )
