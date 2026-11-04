"""Security alerts router -- GET /alerts, POST /acknowledge, /resolve (ADR-033 Laag 1)."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.shared.production_logging import SafeLogger

from .dependencies import (
    OAuth2Scope,
    UserResponse,
    get_current_user,
    get_db,
    require_scopes,
)

logger = SafeLogger(__name__)

alerts_router = APIRouter()


class SecurityAlertResponse(BaseModel):
    """Security alert response model."""

    id: int
    alert_id: str
    alert_type: str
    severity: str
    title: str
    description: str
    status: str
    source_ip: str | None
    user_id: int | None
    event_count: int
    first_event_at: datetime
    last_event_at: datetime
    created_at: datetime
    acknowledged_at: datetime | None = None
    resolved_at: datetime | None = None


class AlertActionRequest(BaseModel):
    """Request model for alert actions."""

    notes: str | None = Field(default=None, max_length=1000)
    false_positive: bool = False


@alerts_router.get("/alerts", response_model=list[SecurityAlertResponse])
async def get_security_alerts(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
    db: AsyncSession = Depends(get_db),
    status_filter: str | None = None,
    severity: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> list[SecurityAlertResponse]:
    """
    Get security alerts.
    Requires: ADMIN permission

    OWASP A09: Provides access to aggregated security incidents.
    """
    try:
        from src.core.security.security_audit_service import get_security_audit_service
        from src.core.security.types import AlertStatus as AS
        from src.core.security.types import ThreatLevel as TL

        logger.info("User %s querying security alerts", current_user.id)

        status_enum = None
        if status_filter:
            try:
                status_enum = AS(status_filter.lower())
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid status: %s" % status_filter,
                )

        severity_enum = None
        if severity:
            try:
                severity_enum = TL(severity.lower())
            except ValueError:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Invalid severity: %s" % severity,
                )

        service = get_security_audit_service()
        alerts = await service.get_alerts(
            db=db,
            tenant_id=current_user.tenant_id,
            status=status_enum,
            severity=severity_enum,
            limit=limit,
            offset=offset,
        )

        return [
            SecurityAlertResponse(
                id=alert.id,
                alert_id=alert.alert_id,
                alert_type=alert.alert_type,
                severity=alert.severity,
                title=alert.title,
                description=alert.description,
                status=alert.status,
                source_ip=alert.source_ip,
                user_id=alert.user_id,
                event_count=alert.event_count or 0,
                first_event_at=alert.first_event_at,
                last_event_at=alert.last_event_at,
                created_at=alert.created_at or datetime.now(timezone.utc),
                acknowledged_at=alert.acknowledged_at,
                resolved_at=alert.resolved_at,
            )
            for alert in alerts
        ]

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get security alerts: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve security alerts",
        )


@alerts_router.post("/alerts/{alert_id}/acknowledge", response_model=dict[str, str])
async def acknowledge_alert(
    alert_id: str,
    request: AlertActionRequest,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """
    Acknowledge a security alert.
    Requires: ADMIN permission
    """
    try:
        from src.core.security.security_audit_service import get_security_audit_service

        logger.info("User %s acknowledging alert %s", current_user.id, alert_id)

        service = get_security_audit_service()
        success = await service.acknowledge_alert(
            db=db, alert_id=alert_id, user_id=current_user.id, notes=request.notes
        )

        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")

        return {"message": "Alert acknowledged successfully", "alert_id": alert_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to acknowledge alert: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to acknowledge alert",
        )


@alerts_router.post("/alerts/{alert_id}/resolve", response_model=dict[str, str])
async def resolve_alert(
    alert_id: str,
    request: AlertActionRequest,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.ADMIN_ALL)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """
    Resolve a security alert.
    Requires: ADMIN permission
    """
    try:
        from src.core.security.security_audit_service import get_security_audit_service

        logger.info("User %s resolving alert %s", current_user.id, alert_id)

        service = get_security_audit_service()
        success = await service.resolve_alert(
            db=db,
            alert_id=alert_id,
            user_id=current_user.id,
            resolution_notes=request.notes or "No notes provided",
            false_positive=request.false_positive,
        )

        if not success:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")

        status_str = "false positive" if request.false_positive else "resolved"
        return {"message": "Alert marked as %s" % status_str, "alert_id": alert_id}

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to resolve alert: %s", e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to resolve alert",
        )
