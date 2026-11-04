# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""
Analytics GDPR endpoints (export + delete user data).

Routes: POST /events/export, DELETE /events/user
"""

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi import status as http_status
from loguru import logger
from sqlalchemy import and_
from sqlalchemy import delete as sql_delete
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.analytics.models import AnalyticsEvent as DBAnalyticsEvent
from src.core.analytics.models import AnalyticsSession
from src.core.api.user_helpers import get_user_id
from src.core.api.v1.analytics_ingest.dependencies import (
    UserResponse,
    get_current_tenant_id,
    get_current_user,
    get_db,
)

router = APIRouter()


@router.post(
    "/events/export",
    summary="Export user analytics data (GDPR)",
    description="Export all analytics data for a user (GDPR compliance).",
)
async def export_user_data(
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Export all analytics data for the current user (GDPR Article 15)."""
    try:
        # OP-11: was current_user.get("sub") -- de dependency geeft een UserResponse
        # (Pydantic, geen .get()), dus dit gooide een AttributeError en daarmee 500.
        # str() behoudt de bestaande semantiek exact: de JWT-claim `sub` is de
        # stringvorm van user.id en de kolom analytics_events.user_id is String.
        resolved_user_id = get_user_id(current_user)
        user_id = str(resolved_user_id) if resolved_user_id is not None else None

        logger.info(
            "GDPR data export requested by user %s",
            user_id,
            extra={"tenant_id": tenant_id},
        )

        events_query = (
            select(DBAnalyticsEvent)
            .where(
                and_(
                    DBAnalyticsEvent.tenant_id == tenant_id,
                    DBAnalyticsEvent.user_id == user_id,
                    DBAnalyticsEvent.is_deleted == False,  # noqa: E712
                )
            )
            .order_by(DBAnalyticsEvent.created_at.desc())
        )

        events_result = await db.execute(events_query)
        events = events_result.scalars().all()

        sessions_query = (
            select(AnalyticsSession)
            .where(
                and_(
                    AnalyticsSession.tenant_id == tenant_id,
                    AnalyticsSession.user_id == user_id,
                )
            )
            .order_by(AnalyticsSession.start_time.desc())
        )

        sessions_result = await db.execute(sessions_query)
        sessions = sessions_result.scalars().all()

        export_data: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "userId": user_id,
            "exportDate": datetime.now(timezone.utc).isoformat(),
            "tenantId": tenant_id,
            "events": [
                {
                    "id": e.id,
                    "eventType": e.event_type,
                    "eventSubtype": e.event_subtype,
                    "timestamp": e.event_timestamp.isoformat(),
                    "data": e.event_data,
                    "sessionId": e.session_id,
                }
                for e in events
            ],
            "sessions": [
                {
                    "sessionId": s.session_id,
                    "startTime": s.start_time.isoformat(),
                    "endTime": s.end_time.isoformat() if s.end_time else None,
                    "duration": s.duration_seconds,
                    "eventCount": s.event_count,
                    "pageViewCount": s.page_view_count,
                    "errorCount": s.error_count,
                }
                for s in sessions
            ],
            "summary": {
                "totalEvents": len(events),
                "totalSessions": len(sessions),
                "exportedAt": datetime.now(timezone.utc).isoformat(),
            },
        }

        return export_data

    except Exception as e:
        logger.error("Error exporting user data: %s", e, exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to export user data",
        )


@router.delete(
    "/events/user",
    summary="Delete user analytics data (GDPR)",
    description="Delete all analytics data for a user (GDPR compliance).",
)
async def delete_user_data(
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
) -> dict[str, str]:
    """Delete all analytics data for the current user (GDPR Article 17)."""
    try:
        # OP-11: was current_user.get("sub") -- de dependency geeft een UserResponse
        # (Pydantic, geen .get()), dus dit gooide een AttributeError en daarmee 500.
        # str() behoudt de bestaande semantiek exact: de JWT-claim `sub` is de
        # stringvorm van user.id en de kolom analytics_events.user_id is String.
        resolved_user_id = get_user_id(current_user)
        user_id = str(resolved_user_id) if resolved_user_id is not None else None

        logger.warning(
            "GDPR data deletion requested by user %s",
            user_id,
            extra={"tenant_id": tenant_id},
        )

        delete_query = sql_delete(DBAnalyticsEvent).where(
            and_(
                DBAnalyticsEvent.tenant_id == tenant_id,
                DBAnalyticsEvent.user_id == user_id,
            )
        )

        result = await db.execute(delete_query)
        deleted_events = getattr(result, "rowcount", 0)

        sessions_result = await db.execute(
            select(AnalyticsSession).where(
                and_(
                    AnalyticsSession.tenant_id == tenant_id,
                    AnalyticsSession.user_id == user_id,
                )
            )
        )
        sessions_to_delete = sessions_result.scalars().all()
        for session in sessions_to_delete:
            session.is_active = False

        await db.commit()

        logger.info(
            "Deleted %d analytics events for user %s",
            deleted_events,
            user_id,
            extra={"tenant_id": tenant_id},
        )

        return {"status": "success", "message": "User data deleted successfully"}

    except Exception as e:
        logger.error("Error deleting user data: %s", e, exc_info=True)
        await db.rollback()
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete user data",
        )
