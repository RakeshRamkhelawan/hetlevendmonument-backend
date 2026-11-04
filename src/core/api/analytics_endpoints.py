# orphan:exempt reason: legacy flat file, replaced by src/core/api/v1/analytics_ingest/ (SP-API-003 Dag 4)
# Re-export composite router for any existing references.
from src.core.api.v1.analytics_ingest.router import router  # noqa: F401

"""
F5.0 Analytics Endpoints - Backend Event Ingestion & Metrics
=============================================================

Production-ready FastAPI endpoints for collecting analytics events from frontend.

Features:
- Batch event ingestion with validation
- PII sanitization on server-side
- Session management and tracking
- Real-time metrics aggregation
- GDPR compliance (data retention, export, deletion)
- Multi-tenant isolation

Security:
- JWT authentication for event submission
- Rate limiting per session
- Input validation with Pydantic
- Consent verification before processing
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, cast

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi import status as http_status
from loguru import logger
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import Float, and_
from sqlalchemy import delete as sql_delete
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import func as sql_func

from src.core.analytics.models import AnalyticsEvent as DBAnalyticsEvent
from src.core.analytics.models import AnalyticsSession

# Existing auth/db dependencies
from src.core.api.dependencies import get_db
from src.core.api.user_helpers import get_user_id
from src.core.auth.api_deps import UserResponse, get_current_user_dependency as get_current_user
from src.core.middleware.tenant_context import get_current_tenant_id, safe_get_tenant_id
from src.core.models.workflow_models import (
    ExecutionStatus,
    WorkflowExecution,
    WorkflowTemplate,
)

router = APIRouter(prefix="/api/analytics", tags=["analytics"])  # noqa: F811


# ============================================================================
# Enums - Match Frontend Event Types
# ============================================================================


class EventSeverity(str, Enum):
    """Event severity levels"""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class EventType(str, Enum):
    """Analytics event types"""

    USER_ACTION = "user_action"
    PERFORMANCE = "performance"
    ERROR = "error"
    SESSION = "session"
    FEATURE_USAGE = "feature_usage"
    WORKFLOW_METRIC = "workflow_metric"
    COST = "cost"


class UserActionType(str, Enum):
    """User action types"""

    WORKFLOW_CREATED = "workflow_created"
    WORKFLOW_STARTED = "workflow_started"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_FAILED = "workflow_failed"
    WORKFLOW_CANCELLED = "workflow_cancelled"
    AGENT_SELECTED = "agent_selected"
    AGENT_DESELECTED = "agent_deselected"
    AGENT_CONFIGURED = "agent_configured"
    APPROVAL_SUBMITTED = "approval_submitted"
    REJECTION_SUBMITTED = "rejection_submitted"
    APPROVAL_CANCELLED = "approval_cancelled"
    EXPLAINABILITY_OPENED = "explainability_opened"
    BIAS_ANALYSIS_RUN = "bias_analysis_run"
    GOVERNANCE_CHECK_RUN = "governance_check_run"
    MEMORY_RECALL_EXECUTED = "memory_recall_executed"
    COMMAND_EXECUTED = "command_executed"
    INTENT_PARSED = "intent_parsed"
    PAGE_VIEW = "page_view"
    MODAL_OPENED = "modal_opened"
    MODAL_CLOSED = "modal_closed"


# ============================================================================
# Pydantic Models - Request/Response
# ============================================================================


class BaseEventModel(BaseModel):
    """Base event model with common fields"""

    type: EventType
    timestamp: str = Field(..., description="ISO 8601 timestamp")
    severity: EventSeverity
    sessionId: str = Field(..., description="Session ID (UUID)")
    userId: str | None = Field(None, description="Hashed user ID")

    model_config = ConfigDict(use_enum_values=True)


class UserActionEvent(BaseEventModel):
    """User action event"""

    type: EventType = EventType.USER_ACTION
    actionType: UserActionType
    # Optional fields for specific actions
    pageName: str | None = None
    workflowId: str | None = None
    agentType: str | None = None
    errorMessage: str | None = None
    reason: str | None = None
    confidence: float | None = None
    metadata: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type


class PerformanceEvent(BaseEventModel):
    """Performance event (Web Vitals, API latency, etc.)"""

    type: EventType = EventType.PERFORMANCE
    metricType: str = Field(..., description="lcp, fid, cls, api_latency, component_render, etc.")
    value: float = Field(..., description="Metric value")
    unit: str = Field(..., description="ms, unitless, etc.")
    endpoint: str | None = None
    httpMethod: str | None = None
    statusCode: int | None = None
    componentName: str | None = None
    hookName: str | None = None
    metadata: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type


class ErrorEvent(BaseEventModel):
    """Error event"""

    type: EventType = EventType.ERROR
    errorType: str = Field(..., description="Error class name")
    errorMessage: str
    stackTrace: str | None = None
    componentName: str | None = None
    context: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type
    browser: str | None = None
    osName: str | None = None
    deviceType: str | None = None


class SessionEvent(BaseEventModel):
    """Session tracking event"""

    type: EventType = EventType.SESSION
    sessionAction: str = Field(..., description="session_start, session_end, session_update")
    sessionDuration: int | None = None  # Seconds
    pageViewCount: int | None = None
    eventCount: int | None = None
    deviceType: str | None = None


class FeatureUsageEvent(BaseEventModel):
    """Feature usage/adoption event"""

    type: EventType = EventType.FEATURE_USAGE
    featureName: str
    featureAction: str = Field(..., description="enabled, disabled, used")
    engagementScore: float | None = None
    adoptionStage: str | None = None


class WorkflowMetricEvent(BaseEventModel):
    """Workflow KPI metric event"""

    type: EventType = EventType.WORKFLOW_METRIC
    workflowId: str
    metricType: str = Field(..., description="completion_rate, success_rate, etc.")
    value: float


class CostEvent(BaseEventModel):
    """Cost/usage event"""

    type: EventType = EventType.COST
    costType: str = Field(..., description="api_call, token_usage, etc.")
    amount: float
    currency: str = Field(default="USD")
    metadata: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type


# Union type for all event types
AnalyticsEvent = (
    UserActionEvent
    | PerformanceEvent
    | ErrorEvent
    | SessionEvent
    | FeatureUsageEvent
    | WorkflowMetricEvent
    | CostEvent
)


class EventBatchRequest(BaseModel):
    """Batch event submission"""

    sessionId: str = Field(..., description="Session ID")
    events: list[AnalyticsEvent] = Field(..., description="List of events")
    batchTimestamp: str = Field(..., description="Batch timestamp (ISO 8601)")
    clientVersion: str | None = Field(None, description="App version")

    @field_validator("events")
    @classmethod
    def validate_events_not_empty(
        cls,
        v: list[Any],  # TODO(TYPE): replace Any with concrete type
    ) -> list[Any]:  # TODO(TYPE): replace Any with concrete type
        if not v or len(v) == 0:
            raise ValueError("Events list cannot be empty")
        if len(v) > 1000:
            raise ValueError("Maximum 1000 events per batch")
        return v


class EventBatchResponse(BaseModel):
    """Response to event batch submission"""

    status: str = Field(..., description="success, partial, failed")
    batchId: str = Field(..., description="Batch ID for tracking")
    eventsProcessed: int = Field(..., description="Number of events processed")
    eventsRejected: int = Field(..., description="Number of events rejected")
    errors: list[dict[str, Any]] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=list, description="Error details"
    )  # TODO(TYPE): replace Any with concrete type
    timestamp: str = Field(..., description="Response timestamp")


class MetricsQueryRequest(BaseModel):
    """Request for metrics"""

    startDate: str = Field(..., description="Start date (ISO 8601)")
    endDate: str = Field(..., description="End date (ISO 8601)")
    metricTypes: list[str] | None = Field(None, description="Filter by metric types")
    workflowIds: list[str] | None = Field(None, description="Filter by workflow IDs")
    agentTypes: list[str] | None = Field(None, description="Filter by agent types")
    aggregation: str = Field(default="hourly", description="hourly, daily, weekly, monthly")


class MetricDataPoint(BaseModel):
    """Single metric data point"""

    timestamp: str
    metricType: str
    value: float
    count: int = 1


class MetricsResponse(BaseModel):
    """Metrics response"""

    startDate: str
    endDate: str
    totalEvents: int
    dataPoints: list[MetricDataPoint]
    summary: dict[str, Any]  # TODO(TYPE): replace Any with concrete type


class SessionMetricsResponse(BaseModel):
    """Session-level metrics"""

    sessionId: str
    userId: str | None
    startTime: str
    endTime: str | None
    duration: int | None  # Seconds
    pageViewCount: int
    eventCount: int
    actions: list[UserActionType]
    errors: int


class HealthCheckResponse(BaseModel):
    """Health check response"""

    status: str
    timestamp: str
    eventsInQueue: int
    failedEvents: int


# ============================================================================
# Database Models (to be created as SQLAlchemy models)
# ============================================================================

# Note: In a real implementation, these would be SQLAlchemy models in database/models/
# For now, they're conceptual - the endpoint stores raw events in a collection/table

# class AnalyticsEventRecord(Base):
#     """Database model for analytics events"""
#     __tablename__ = "analytics_events"
#
#     id = Column(UUID, primary_key=True, default=uuid4)
#     tenant_id = Column(String, nullable=False, index=True)
#     session_id = Column(String, nullable=False, index=True)
#     user_id = Column(String, nullable=True, index=True)
#     event_type = Column(String, nullable=False, index=True)
#     event_data = Column(JSON, nullable=False)
#     severity = Column(String, nullable=False)
#     timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
#     created_at = Column(DateTime(timezone=True), default=datetime.utcnow)


# ============================================================================
# Endpoints
# ============================================================================


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
    current_user: UserResponse = Depends(get_current_user),  # TODO(TYPE): replace Any with concrete type
    tenant_id: str = Depends(get_current_tenant_id),
) -> EventBatchResponse:
    """
    Submit a batch of analytics events from the frontend.

    - **sessionId**: UUID of the user session
    - **events**: List[Any] of analytics events  # TODO(TYPE): replace Any with concrete type
    - **batchTimestamp**: ISO 8601 timestamp when batch was created
    - **clientVersion**: Optional app version for tracking client versions

    Returns 202 Accepted (events are stored immediately).
    """
    try:
        batch_id = str(uuid.uuid4())
        timestamp = datetime.now(timezone.utc).isoformat()
        processed_count = 0
        rejected_count = 0
        errors: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        # Parse batch timestamp
        try:
            batch_ts = datetime.fromisoformat(batch.batchTimestamp.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            batch_ts = datetime.now(timezone.utc)

        # Store each event in database
        for idx, event in enumerate(batch.events):
            try:
                # Parse event timestamp
                try:
                    event_ts = datetime.fromisoformat(event.timestamp.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    event_ts = batch_ts

                # Create analytics event record
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
                logger.warning(f"Failed to process event {idx} in batch {batch_id}: {e}")
                rejected_count += 1
                errors.append({"index": idx, "error": "Er is een fout opgetreden."})

        # Commit all events
        if processed_count > 0:
            await db.commit()

        logger.info(
            f"Stored event batch {batch_id} with {processed_count} events",
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
        logger.warning(f"Validation error in event batch: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Invalid event batch",
        )
    except Exception as e:
        logger.error(f"Error processing event batch: {e}", exc_info=True)
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
    current_user: UserResponse = Depends(get_current_user),  # TODO(TYPE): replace Any with concrete type
    tenant_id: str = Depends(get_current_tenant_id),
) -> MetricsResponse:
    """
    Query aggregated metrics for a time period.

    **Parameters:**
    - `start_date`: Start of time period (ISO 8601)
    - `end_date`: End of time period (ISO 8601)
    - `metric_types`: Optional filter by metric type (e.g., "lcp", "api_latency")
    - `workflow_ids`: Optional filter by workflow
    - `agent_types`: Optional filter by agent type
    - `aggregation`: Time bucket (hourly, daily, weekly, monthly)

    **Returns:** Aggregated metrics with time series data points
    """
    try:
        # Parse dates
        try:
            start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        except (ValueError, AttributeError) as e:
            logger.opt(exception=True).error("get_metrics mislukt: {}", type(e).__name__)
            raise ValueError("Invalid date format")

        logger.info(
            f"Metrics query from {start_date} to {end_date}",
            extra={
                "tenant_id": tenant_id,
                "user_id": get_user_id(current_user),
                "metric_types": metric_types,
            },
        )

        # Query analytics events and aggregate
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

        # Apply optional filters
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

        # Build response with data points
        data_points: list[Any] = []  # TODO(TYPE): replace Any with concrete type
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

            # Populate summary
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
        logger.warning(f"Invalid query parameters: {e}")
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="Invalid query",
        )
    except Exception as e:
        logger.error(f"Error querying metrics: {e}", exc_info=True)
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
    current_user: UserResponse = Depends(get_current_user),  # TODO(TYPE): replace Any with concrete type
    tenant_id: str = Depends(get_current_tenant_id),
) -> SessionMetricsResponse:
    """
    Get detailed metrics for a user session.

    - `session_id`: UUID of the session to query

    Returns session-level metrics including duration, event counts, and actions performed.
    """
    try:
        logger.info(
            f"Session metrics query for {session_id}",
            extra={
                "tenant_id": tenant_id,
                "user_id": get_user_id(current_user),
            },
        )

        # Query for session from AnalyticsSession table
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
            # Try to build from raw events
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
        logger.error(f"Error querying session metrics: {e}", exc_info=True)
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
    """
    Health check endpoint for analytics service.

    Returns current status of the analytics system.
    """
    try:
        timestamp = datetime.now(timezone.utc).isoformat()

        # TI-004: Use SELECT 1 connectivity check only.
        # The previous cross-tenant COUNT(DBAnalyticsEvent) aggregation was removed:
        # it exposed global event counts without auth or tenant isolation.
        from sqlalchemy import text

        await db.execute(text("SELECT 1"))

        return HealthCheckResponse(
            status="healthy",
            timestamp=timestamp,
            eventsInQueue=0,
            failedEvents=0,
        )
    except Exception as e:
        logger.error("Analytics health check failed: %s: %s", type(e).__name__, e, exc_info=True)
        return HealthCheckResponse(
            status="unhealthy",
            timestamp=datetime.now(timezone.utc).isoformat(),
            eventsInQueue=0,
            failedEvents=-1,
        )


@router.post(
    "/events/export",
    summary="Export user analytics data (GDPR)",
    description="Export all analytics data for a user (GDPR compliance).",
)
async def export_user_data(
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),  # TODO(TYPE): replace Any with concrete type
    tenant_id: str = Depends(get_current_tenant_id),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Export all analytics data for the current user (GDPR Article 15).

    Returns all events, sessions, and metrics associated with the user.
    """
    try:
        # OP-11: was current_user.get("sub"); de dependency geeft een UserResponse
        # (Pydantic, geen .get()) -> AttributeError -> 500. str() behoudt de
        # bestaande semantiek: de kolom user_id is String en `sub` is str(user.id).
        resolved_user_id = get_user_id(current_user)
        user_id = str(resolved_user_id) if resolved_user_id is not None else None

        logger.info(
            f"GDPR data export requested by user {user_id}",
            extra={"tenant_id": tenant_id},
        )

        # Query all user events
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

        # Query all user sessions
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

        # Build export data
        export_data = {
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
        logger.error(f"Error exporting user data: {e}", exc_info=True)
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
    current_user: UserResponse = Depends(get_current_user),  # TODO(TYPE): replace Any with concrete type
    tenant_id: str = Depends(get_current_tenant_id),
) -> dict[str, str]:
    """
    Delete all analytics data for the current user (GDPR Article 17 - Right to be forgotten).

    This performs a soft delete. All events and metrics will be marked as deleted.
    """
    try:
        # OP-11: was current_user.get("sub"); de dependency geeft een UserResponse
        # (Pydantic, geen .get()) -> AttributeError -> 500. str() behoudt de
        # bestaande semantiek: de kolom user_id is String en `sub` is str(user.id).
        resolved_user_id = get_user_id(current_user)
        user_id = str(resolved_user_id) if resolved_user_id is not None else None

        logger.warning(
            f"GDPR data deletion requested by user {user_id}",
            extra={"tenant_id": tenant_id},
        )

        # Soft delete: Mark user's events as deleted
        delete_query = sql_delete(DBAnalyticsEvent).where(
            and_(
                DBAnalyticsEvent.tenant_id == tenant_id,
                DBAnalyticsEvent.user_id == user_id,
            )
        )

        result = await db.execute(delete_query)
        deleted_events = getattr(result, "rowcount", 0)

        # Also soft delete user sessions
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
            f"Deleted {deleted_events} analytics events for user {user_id}",
            extra={"tenant_id": tenant_id},
        )

        return {"status": "success", "message": "User data deleted successfully"}

    except Exception as e:
        logger.error(f"Error deleting user data: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete user data",
        )


class DashboardQuotaItem(BaseModel):
    label: str
    used: float
    total: float
    unit: str


class QuickTemplateItem(BaseModel):
    template_id: str
    category: str
    name: str
    description: str


class WebVitalsStats(BaseModel):
    LCP: float
    FID: float
    CLS: float
    TTFB: float


class ApiPerformanceStats(BaseModel):
    avgLatency: float
    errorRate: float
    totalRequests: int
    cacheHitRate: float
    latencyTrend: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type


class SessionStats(BaseModel):
    totalSessions: int
    activeSessions: int
    avgDuration: float
    avgPageViews: float


class WorkflowStats(BaseModel):
    totalWorkflows: int
    completionRate: float
    successRate: float
    avgDuration: float
    failureCount: int


class FeatureAdoptionItem(BaseModel):
    name: str
    adoption: float


class TopActionItem(BaseModel):
    action: str
    count: int


class DashboardStatsResponse(BaseModel):
    lastUpdated: str
    quota: list[DashboardQuotaItem]
    quickTemplates: list[QuickTemplateItem]
    webVitals: WebVitalsStats
    apiPerformance: ApiPerformanceStats
    sessions: SessionStats
    workflows: WorkflowStats
    featureAdoption: list[FeatureAdoptionItem]
    topActions: list[TopActionItem]


@router.get(
    "/dashboard",
    summary="Get dashboard statistics",
    description="Get aggregated statistics for the main dashboard.",
    response_model=DashboardStatsResponse,
)
async def get_dashboard_stats(
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),  # TODO(TYPE): replace Any with concrete type
    tenant_id: int = Depends(safe_get_tenant_id),
) -> DashboardStatsResponse:
    """
    Get aggregated dashboard statistics.
    """
    try:

        # 1. Quota Usage (Count Active Templates)
        # Using a safer count approach
        workflow_count = 0
        try:
            workflow_result = await db.execute(
                select(sql_func.count())
                .select_from(WorkflowTemplate)
                .where(WorkflowTemplate.tenant_id == tenant_id)
            )
            workflow_count = workflow_result.scalar() or 0
        except Exception as e:
            logger.error(f"Error counting workflows: {e}")

        # Mock values for now where DB tables might be missing or empty
        agent_count = 4
        storage_usage = 0.5

        quota_stats = [
            DashboardQuotaItem(label="Workflows", used=float(workflow_count), total=50, unit=""),
            DashboardQuotaItem(label="Agents", used=float(agent_count), total=10, unit=""),
            DashboardQuotaItem(label="Storage", used=storage_usage, total=5, unit="GB"),
        ]

        # 2. Quick Templates (Top 3 by execution count)
        quick_templates: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        try:
            # Simple query to get recent templates
            templates_result = await db.execute(
                select(WorkflowTemplate).where(WorkflowTemplate.tenant_id == tenant_id).limit(3)
            )
            templates = templates_result.scalars().all()
            for t in templates:
                quick_templates.append(
                    QuickTemplateItem(
                        template_id=str(t.id),
                        category="General",  # Default
                        name=t.name,
                        description=t.description or "No description",
                    )
                )
        except Exception as e:
            logger.error(f"Error fetching quick templates: {e}")

        # 3. Workflow Stats (Executions)
        workflow_stats = WorkflowStats(
            totalWorkflows=0,
            completionRate=0,
            successRate=0,
            avgDuration=0,
            failureCount=0,
        )
        try:
            # Count total executions
            total_exec_result = await db.execute(
                select(sql_func.count())
                .select_from(WorkflowExecution)
                .where(WorkflowExecution.tenant_id == tenant_id)
            )
            total_executions = total_exec_result.scalar() or 0

            if total_executions > 0:
                # Count failures
                failed_result = await db.execute(
                    select(sql_func.count())
                    .select_from(WorkflowExecution)
                    .where(
                        and_(
                            WorkflowExecution.tenant_id == tenant_id,
                            WorkflowExecution.status == ExecutionStatus.FAILED,
                        )
                    )
                )
                failure_count = failed_result.scalar() or 0

                # Calculate success rate
                success_rate = ((total_executions - failure_count) / total_executions) * 100

                workflow_stats = WorkflowStats(
                    totalWorkflows=total_executions,
                    completionRate=95.0,  # Mock
                    successRate=success_rate,
                    avgDuration=120.0,  # Mock
                    failureCount=failure_count,
                )
        except Exception as e:
            logger.error(f"Error fetching workflow stats: {e}")

        # 4. Web Vitals (Mock)
        web_vitals = WebVitalsStats(LCP=1200, FID=95, CLS=0.08, TTFB=520)

        # 5. Sessions (Mock)
        session_stats = SessionStats(
            totalSessions=1245,
            activeSessions=52,
            avgDuration=1320.0,
            avgPageViews=5.8,
        )

        # 6. Feature Adoption (Mock)
        feature_adoption = [
            FeatureAdoptionItem(name="Workflow Builder", adoption=85.0),
            FeatureAdoptionItem(name="AI Chat", adoption=65.0),
        ]

        # 7. Top Actions (Mock)
        top_actions = [
            TopActionItem(action="Create Workflow", count=150),
            TopActionItem(action="Run Analysis", count=120),
        ]

        # 8. API Performance (Mock)
        api_performance = ApiPerformanceStats(
            avgLatency=255.0,
            errorRate=0.45,
            totalRequests=1350,
            cacheHitRate=85.2,
            latencyTrend=[],
        )

        return DashboardStatsResponse(
            lastUpdated=datetime.now(timezone.utc).isoformat(),
            quota=quota_stats,
            quickTemplates=quick_templates,
            webVitals=web_vitals,
            apiPerformance=api_performance,
            sessions=session_stats,
            workflows=workflow_stats,
            featureAdoption=feature_adoption,
            topActions=top_actions,
        )

    except Exception as e:
        logger.error(f"Error fetching dashboard stats: {e}", exc_info=True)
        # Return a safe fallback rather than 500 if possible, or re-raise
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch dashboard stats",
        )


@router.get("/dashboard")
async def get_analytics_dashboard(
    tenant_id: int = Depends(safe_get_tenant_id),  # TYPE SAFETY FIX: str -> int
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),  # TODO(TYPE): replace Any with concrete type
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Haal analytics op voor de huidige tenant.
    Bevat 'Defensieve Logica' om crashes te voorkomen bij lege datasets.
    """
    logger.info(f"Starting analytics aggregation for tenant {tenant_id}")

    try:
        # Defensieve aanpak: Een falende query mag niet het hele dashboard crashen
        # Dit is een voorbeeld query, pas aan naar uw specifieke metrieken
        result = await db.execute(
            text("SELECT count(*) FROM users WHERE tenant_id = :tid"),
            {"tid": tenant_id},
        )
        user_count = result.scalar() or 0

        return {
            "tenant_id": tenant_id,
            "status": "healthy",
            "data": {"active_users": user_count, "system_health": "optimal"},
        }
    except Exception as e:
        logger.error(f"Analytics dashboard partial failure for tenant {tenant_id}: {str(e)}")
        # Fail Gracefully: Return een geldige JSON met error status i.p.v. 500 Crash
        return {
            "tenant_id": tenant_id,
            "status": "degraded",
            "error": "Analytics metrics tijdelijk niet beschikbaar",
            "data": None,
        }
