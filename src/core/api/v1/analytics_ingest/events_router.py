# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""
Analytics events ingestion and query endpoints.

Routes: POST /events, GET /metrics, GET /sessions/{session_id}, GET /health
"""

import uuid
from datetime import datetime, timezone
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from loguru import logger
from sqlalchemy import Float, and_
from sqlalchemy import delete as sql_delete
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func as sql_func

from src.core.analytics.models import AnalyticsEvent as DBAnalyticsEvent
from src.core.analytics.models import AnalyticsSession
from src.core.api.user_helpers import get_user_id
from src.core.api.v1.analytics_ingest.dependencies import (
    UserResponse,
    analytics_consent_allowed,
    get_current_tenant_id,
    get_current_user,
    get_db,
)
from src.core.api.v1.analytics_ingest.schemas import (
    EventBatchRequest,
    EventBatchResponse,
    EventType,
    HealthCheckResponse,
    MetricDataPoint,
    MetricsResponse,
    SessionMetricsResponse,
    UserActionType,
)

router = APIRouter()


@router.post(
    "/events",
    response_model=EventBatchResponse,
    status_code=http_status.HTTP_202_ACCEPTED,
    summary="Submit analytics events batch",
    description="Batch submission endpoint for frontend events. Events are stored in database.",
)
async def submit_events(
    batch: EventBatchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
    analytics_allowed: bool = Depends(analytics_consent_allowed),
) -> EventBatchResponse:
    """
    Submit a batch of analytics events from the frontend.

    - **sessionId**: UUID of the user session
    - **events**: List of analytics events
    - **batchTimestamp**: ISO 8601 timestamp when batch was created
    - **clientVersion**: Optional app version for tracking client versions

    Returns 202 Accepted (events are stored immediately).
    """
    try:
        batch_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        processed_count = 0
        rejected_count = 0
        errors: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
        try:
            batch_ts = datetime.fromisoformat(batch.batchTimestamp.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            batch_ts = datetime.now(timezone.utc)

        # GDPR-004: analytics_allowed is resolved by the analytics_consent_allowed dependency
        # (reads the stored consent for the verified-JWT user via the dependencies facade --
        # ADR-033; fail-closed). Events for a user without analytics consent are not persisted.
        for idx, event in enumerate(batch.events):
            try:
                if not analytics_allowed:
                    rejected_count += 1
                    errors.append({"index": idx, "error": "analytics_consent_absent"})
                    continue

                try:
                    event_ts = datetime.fromisoformat(event.timestamp.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    event_ts = batch_ts

                analytics_event = DBAnalyticsEvent(
                    tenant_id=tenant_id,
                    session_id=batch.sessionId,
                    user_id=event.userId,
                    event_type=event.type.value if hasattr(event.type, "value") else event.type,
                    event_subtype=getattr(event, "actionType", None),
                    severity=(
                        event.severity.value if hasattr(event.severity, "value") else event.severity
                    ),
                    event_data=event.model_dump(),
                    event_timestamp=event_ts,
                    batch_id=batch_id,
                    context={
                        "client_version": batch.clientVersion,
                        "batch_index": idx,
                    },
                )
                db.add(analytics_event)
                processed_count += 1

            except Exception as e:
                logger.warning(
                    "Failed to process event %d in batch %s: %s",
                    idx,
                    batch_id,
                    e,
                )
                rejected_count += 1
                errors.append({"index": idx, "error": "Er is een fout opgetreden."})

        if processed_count > 0:
            await db.commit()

        logger.info(
            "Stored event batch %s with %d events",
            batch_id,
            processed_count,
            extra={
                "tenant_id": tenant_id,
                "batch_id": batch_id,
                "processed": processed_count,
                "rejected": rejected_count,
                "user_id": get_user_id(current_user),
            },
        )

        status = "success" if rejected_count == 0 else "partial"
        return EventBatchResponse(
            status=status,
            batchId=batch_id,
            eventsProcessed=processed_count,
            eventsRejected=rejected_count,
            errors=errors,
            timestamp=timestamp,
        )

    except ValueError as e:
        logger.warning("Validation error in event batch: %s", e)
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Invalid event batch",
        )
    except Exception as e:
        logger.error("Error processing event batch: %s", e, exc_info=True)
        await db.rollback()
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process event batch",
        )


@router.get(
    "/metrics",
    response_model=MetricsResponse,
    summary="Query aggregated metrics",
    description="Retrieve aggregated analytics metrics for a time period from database.",
)
async def get_metrics(
    start_date: str = Query(..., description="Start date (ISO 8601)"),
    end_date: str = Query(..., description="End date (ISO 8601)"),
    metric_types: list[str] | None = Query(None, description="Filter by metric types"),
    workflow_ids: list[str] | None = Query(None, description="Filter by workflow IDs"),
    agent_types: list[str] | None = Query(None, description="Filter by agent types"),
    aggregation: str = Query("daily", description="hourly, daily, weekly, monthly"),
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
) -> MetricsResponse:
    """Query aggregated metrics for a time period."""
    try:
        try:
            start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        except (ValueError, AttributeError) as e:
            logger.opt(exception=True).error("get_metrics mislukt: {}", type(e).__name__)
            raise ValueError("Invalid date format")

        logger.info(
            "Metrics query from %s to %s",
            start_date,
            end_date,
            extra={
                "tenant_id": tenant_id,
                "user_id": get_user_id(current_user),
                "metric_types": metric_types,
            },
        )

        query = select(
            DBAnalyticsEvent.event_type,
            sql_func.count(DBAnalyticsEvent.id).label("count"),
            sql_func.avg(
                sql_func.cast(
                    sql_func.json_extract(DBAnalyticsEvent.event_data, "$.value"),
                    type_=Float,
                )
            ).label("avg_value"),
            sql_func.min(
                sql_func.cast(
                    sql_func.json_extract(DBAnalyticsEvent.event_data, "$.value"),
                    type_=Float,
                )
            ).label("min_value"),
            sql_func.max(
                sql_func.cast(
                    sql_func.json_extract(DBAnalyticsEvent.event_data, "$.value"),
                    type_=Float,
                )
            ).label("max_value"),
        ).where(
            and_(
                DBAnalyticsEvent.tenant_id == tenant_id,
                DBAnalyticsEvent.event_timestamp >= start_dt,
                DBAnalyticsEvent.event_timestamp <= end_dt,
                DBAnalyticsEvent.is_deleted == False,  # noqa: E712
            )
        )

        if metric_types:
            query = query.where(DBAnalyticsEvent.event_type.in_(metric_types))
        if agent_types:
            query = query.where(
                sql_func.json_contains(
                    DBAnalyticsEvent.event_data,
                    sql_func.json_object("agentType", sql_func.any(agent_types)),
                )
            )

        query = query.group_by(DBAnalyticsEvent.event_type)
        result = await db.execute(query)
        rows = result.all()

        data_points: list[MetricDataPoint] = []
        summary: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
            "avgLCP": None,
            "avgAPILatency": None,
            "errorRate": None,
            "sessionCount": 0,
        }

        total_events = 0
        for row in rows:
            event_type, count, avg_val, min_val, max_val = row
            total_events += count
            data_points.append(
                MetricDataPoint(
                    timestamp=start_date,
                    metricType=event_type or "unknown",
                    value=float(avg_val or 0),
                    count=count,
                )
            )
            if event_type == "performance" and avg_val:
                summary["avgAPILatency"] = float(avg_val)
            elif event_type == "error":
                if total_events > 0:
                    summary["errorRate"] = (count / total_events) * 100

        return MetricsResponse(
            startDate=start_date,
            endDate=end_date,
            totalEvents=total_events,
            dataPoints=data_points,
            summary=summary,
        )

    except ValueError as e:
        logger.warning("Invalid query parameters: %s", e)
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Invalid query",
        )
    except Exception as e:
        logger.error("Error querying metrics: %s", e, exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to query metrics",
        )


@router.get(
    "/sessions/{session_id}",
    response_model=SessionMetricsResponse,
    summary="Get session metrics",
    description="Retrieve detailed metrics for a specific session from database.",
)
async def get_session_metrics(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
    tenant_id: str = Depends(get_current_tenant_id),
) -> SessionMetricsResponse:
    """Get detailed metrics for a user session."""
    try:
        logger.info(
            "Session metrics query for %s",
            session_id,
            extra={"tenant_id": tenant_id, "user_id": get_user_id(current_user)},
        )

        query = select(AnalyticsSession).where(
            and_(
                AnalyticsSession.tenant_id == tenant_id,
                AnalyticsSession.session_id == session_id,
            )
        )
        result = await db.execute(query)
        session_record = result.scalar_one_or_none()

        if session_record:
            return SessionMetricsResponse(
                sessionId=session_record.session_id,
                userId=session_record.user_id,
                startTime=session_record.start_time.isoformat(),
                endTime=session_record.end_time.isoformat() if session_record.end_time else None,
                duration=session_record.duration_seconds,
                pageViewCount=session_record.page_view_count,
                eventCount=session_record.event_count,
                actions=(
                    [UserActionType(k) for k in session_record.actions.keys()]
                    if session_record.actions
                    else []
                ),
                errors=session_record.error_count,
            )
        else:
            events_query = (
                select(DBAnalyticsEvent)
                .where(
                    and_(
                        DBAnalyticsEvent.tenant_id == tenant_id,
                        DBAnalyticsEvent.session_id == session_id,
                        DBAnalyticsEvent.is_deleted == False,  # noqa: E712
                    )
                )
                .order_by(DBAnalyticsEvent.event_timestamp)
            )

            events_result = await db.execute(events_query)
            events = events_result.scalars().all()

            if not events:
                raise HTTPException(status_code=404, detail="Session not found")

            start_time = events[0].event_timestamp
            end_time = events[-1].event_timestamp
            duration = int((end_time - start_time).total_seconds())
            error_count = sum(1 for e in events if e.event_type == "error")
            page_views = sum(
                1
                for e in events
                if e.event_type == "user_action" and e.event_subtype == "page_view"
            )
            actions: set[str] = set()
            for e in events:
                if e.event_subtype:
                    actions.add(e.event_subtype)

            return SessionMetricsResponse(
                sessionId=session_id,
                userId=events[0].user_id if events else None,
                startTime=start_time.isoformat(),
                endTime=end_time.isoformat(),
                duration=duration,
                pageViewCount=page_views,
                eventCount=len(events),
                actions=cast(list[UserActionType], list(actions)),
                errors=error_count,
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error querying session metrics: %s", e, exc_info=True)
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to query session metrics",
        )


@router.get(
    "/health",
    response_model=HealthCheckResponse,
    summary="Analytics service health",
)
async def health_check(
    db: AsyncSession = Depends(get_db),
) -> HealthCheckResponse:
    """Health check endpoint for analytics service."""
    try:
        timestamp = datetime.now(timezone.utc).isoformat()
        # SELECT 1 connectivity check -- no cross-tenant data aggregation (AUDIT-TI-004)
        await db.execute(text("SELECT 1"))
        return HealthCheckResponse(
            status="healthy",
            timestamp=timestamp,
            eventsInQueue=0,
            failedEvents=0,
        )
    except Exception as e:
        logger.error("Health check failed: %s", e, exc_info=True)
        return HealthCheckResponse(
            status="unhealthy",
            timestamp=datetime.now(timezone.utc).isoformat(),
            eventsInQueue=0,
            failedEvents=-1,
        )
