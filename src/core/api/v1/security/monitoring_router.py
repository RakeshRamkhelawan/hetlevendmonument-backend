"""Security monitoring router -- GET /health, /audit-logs, /verify-integrity (ADR-033 Laag 1)."""

from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
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

monitoring_router = APIRouter()


class AuditLogResponse(BaseModel):
    """Audit log entry response model."""

    id: int
    event_type: str
    threat_level: str
    user_id: int | None
    client_ip: str
    endpoint: str
    description: str
    resource: str | None
    action: str | None
    timestamp: datetime
    details: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type


class AuditLogQueryParams(BaseModel):
    """Query parameters for audit log searches."""

    event_types: list[str] | None = None
    severity: str | None = None
    hours: int = Field(default=24, ge=1, le=720)
    limit: int = Field(default=100, ge=1, le=1000)


class LogIntegrityResponse(BaseModel):
    """Log integrity verification response."""

    verified: bool
    # Een GAT is iets anders dan MANIPULATIE (ADR-036 OP-108). Zonder dit onderscheid geeft dit
    # endpoint `verified: false` met een LEEG `tampered_entries` aan elke omgeving met
    # legacy-auditrijen -- een negatief oordeel zonder enige aanwijzing waarom. Een alarm dat
    # altijd afgaat en niets uitlegt, is een alarm dat men uitzet.
    tampering_detected: bool = False
    unhashed_entries: int = 0
    entries_checked: int
    tampered_entries: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
    verified_at: str
    error: str | None = None


@monitoring_router.get("/health", response_model=dict[str, Any])  # TODO(TYPE): replace Any
async def security_health(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Security system health check.
    Requires: READ permission (USER level)
    """
    try:
        logger.info("User %s requesting security health", current_user.id)

        security_manager = get_security_manager()
        now = datetime.now(timezone.utc)
        last_hour = now - timedelta(hours=1)

        recent_events = [e for e in security_manager.security_events if e.timestamp > last_hour]

        critical_events = [
            e
            for e in recent_events
            if hasattr(e.severity, "name") and e.severity.name == "CRITICAL"
        ]

        high_events = [
            e for e in recent_events if hasattr(e.severity, "name") and e.severity.name == "HIGH"
        ]

        health_status = "healthy"
        if len(critical_events) > 0:
            health_status = "critical"
        elif len(high_events) > 5:
            health_status = "warning"

        return {
            "status": health_status,
            "timestamp": now.isoformat(),
            "blocked_ips": len(security_manager.blocked_ips),
            "recent_events": len(recent_events),
            "critical_events": len(critical_events),
            "security_features": {
                "authentication": True,
                "rate_limiting": True,
                "threat_detection": True,
                "ip_blocking": True,
            },
        }

    except Exception as e:
        logger.error("Security health check failed: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Health check failed",
        )


@monitoring_router.get("/audit-logs", response_model=list[AuditLogResponse])
async def get_audit_logs(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
    db: AsyncSession = Depends(get_db),
    event_type: str | None = None,
    severity: str | None = None,
    hours: int = Query(default=24, ge=1, le=720),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
) -> list[AuditLogResponse]:
    """
    Get audit logs from database (persistent storage).
    Requires: ADMIN permission

    OWASP A09: Provides access to comprehensive security audit trail.
    """
    try:
        from src.core.security.security_audit_service import get_security_audit_service
        from src.core.security.types import SecurityEventType
        from src.core.security.types import ThreatLevel as TL

        logger.info("User %s querying audit logs", current_user.id)

        event_types_filter = None
        if event_type:
            try:
                event_types_filter = [SecurityEventType(event_type)]
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid event_type: %s" % event_type,
                )

        severity_filter = None
        if severity:
            try:
                severity_filter = TL(severity.lower())
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid severity: %s" % severity,
                )

        service = get_security_audit_service()
        logs = await service.get_recent_events(
            db=db,
            tenant_id=current_user.tenant_id,
            event_types=event_types_filter,
            severity=severity_filter,
            hours=hours,
            limit=limit,
            offset=offset,
        )

        return [
            AuditLogResponse(
                id=log.id,
                event_type=log.event_type,
                threat_level=log.threat_level,
                user_id=log.user_id,
                client_ip=log.client_ip,
                endpoint=log.endpoint,
                description=log.description,
                resource=log.resource,
                action=log.action,
                timestamp=log.timestamp,
                details=log.details,
            )
            for log in logs
        ]

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get audit logs: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve audit logs",
        )


@monitoring_router.get("/verify-integrity", response_model=LogIntegrityResponse)
async def verify_log_integrity(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=1000, ge=1, le=10000),
) -> LogIntegrityResponse:
    """
    Verify audit log integrity via hash chain.
    Requires: ADMIN permission

    OWASP A09: Detects log tampering attempts.
    """
    try:
        from src.core.security.security_audit_service import get_security_audit_service

        logger.info("User %s verifying log integrity", current_user.id)

        service = get_security_audit_service()
        result = await service.verify_log_integrity(
            db=db, tenant_id=current_user.tenant_id, limit=limit
        )

        return LogIntegrityResponse(
            verified=result.get("verified", False),
            tampering_detected=result.get("tampering_detected", False),
            unhashed_entries=result.get("unhashed_entries", 0),
            entries_checked=result.get("entries_checked", 0),
            tampered_entries=result.get("tampered_entries", []),
            verified_at=result.get("verified_at", datetime.now(timezone.utc).isoformat()),
            error=result.get("error"),
        )

    except Exception as e:
        logger.error("Failed to verify log integrity: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to verify log integrity",
        )
