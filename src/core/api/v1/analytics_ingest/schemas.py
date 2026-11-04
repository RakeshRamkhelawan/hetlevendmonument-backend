"""
Pydantic schemas for analytics_ingest domain.

Shared between events_router, gdpr_router, and dashboard_router.
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ============================================================================
# Enums
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
# Event Models
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
    pageName: str | None = None
    workflowId: str | None = None
    agentType: str | None = None
    errorMessage: str | None = None
    reason: str | None = None
    confidence: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type


class PerformanceEvent(BaseEventModel):
    """Performance event (Web Vitals, API latency, etc.)"""

    type: EventType = EventType.PERFORMANCE
    metricType: str = Field(..., description="lcp, fid, cls, api_latency, etc.")
    value: float = Field(..., description="Metric value")
    unit: str = Field(..., description="ms, unitless, etc.")
    endpoint: str | None = None
    httpMethod: str | None = None
    statusCode: int | None = None
    componentName: str | None = None
    hookName: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type


class ErrorEvent(BaseEventModel):
    """Error event"""

    type: EventType = EventType.ERROR
    errorType: str = Field(..., description="Error class name")
    errorMessage: str
    stackTrace: str | None = None
    componentName: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    browser: str | None = None
    osName: str | None = None
    deviceType: str | None = None


class SessionEvent(BaseEventModel):
    """Session tracking event"""

    type: EventType = EventType.SESSION
    sessionAction: str = Field(..., description="session_start, session_end, session_update")
    sessionDuration: int | None = None
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
    metadata: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type


AnalyticsEvent = (
    UserActionEvent
    | PerformanceEvent
    | ErrorEvent
    | SessionEvent
    | FeatureUsageEvent
    | WorkflowMetricEvent
    | CostEvent
)


# ============================================================================
# Request / Response Models
# ============================================================================


class EventBatchRequest(BaseModel):
    """Batch event submission"""

    sessionId: str = Field(..., description="Session ID")
    events: list[AnalyticsEvent] = Field(..., description="List of events")
    batchTimestamp: str = Field(..., description="Batch timestamp (ISO 8601)")
    clientVersion: str | None = Field(None, description="App version")

    @field_validator("events")
    @classmethod
    def validate_events_not_empty(cls, v: list[Any]) -> list[Any]:  # TODO(TYPE): replace Any with concrete type
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
    errors: list[dict[str, Any]] = Field(default_factory=list, description="Error details")
    timestamp: str = Field(..., description="Response timestamp")


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
    duration: int | None
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


# Dashboard schemas


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
