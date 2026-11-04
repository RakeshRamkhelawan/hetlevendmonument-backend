"""
Pydantic schemas for Orchestration API endpoints.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

# --- Enums -------------------------------------------------------------------


class WorkflowMode(str, Enum):
    """Workflow execution modes."""

    AUTO = "auto"
    SEQUENTIAL = "sequential"
    PARALLEL = "parallel"


class TaskStatus(str, Enum):
    """Task execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class HealthStatus(str, Enum):
    """Agent health status."""

    HEALTHY = "healthy"
    WARNING = "warning"
    CRITICAL = "critical"
    STALE = "stale"
    UNKNOWN = "unknown"


class CriticMode(str, Enum):
    """Critic agent modes."""

    SILENT = "silent"
    ADVISORY = "advisory"
    BLOCKING = "blocking"


# --- Base Models -------------------------------------------------------------


class TaskDataSchema(BaseModel):
    """Schema for task data."""

    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    parameters: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type
    metadata: dict[str, Any] = Field(
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type


class SubTaskSchema(BaseModel):
    """Schema for workflow sub-task."""

    id: str
    title: str
    description: str
    assigned_agent: str | None = None
    dependencies: list[str] = Field(default_factory=list)
    estimated_duration_ms: int = 0


# --- Request Schemas ---------------------------------------------------------


class OrchestrateTaskRequest(BaseModel):
    """Request to orchestrate a task through MasterOrchestratorAgent."""

    task: TaskDataSchema
    workflow_mode: WorkflowMode = WorkflowMode.AUTO
    max_subtasks: int = Field(default=6, ge=2, le=20)
    require_critic_review: bool = False


class RouteTaskRequest(BaseModel):
    """Request to route a task to appropriate agent."""

    task: TaskDataSchema
    required_capabilities: list[str] = Field(default_factory=list)
    preferred_agents: list[str] = Field(default_factory=list)
    fallback_to_llm: bool = True


class CritiqueRequest(BaseModel):
    """Request for agent output critique."""

    agent_name: str = Field(..., min_length=1, max_length=100)
    task_id: str = Field(..., min_length=1, max_length=100)
    output: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    error: str | None = None
    latency_ms: int = Field(default=0, ge=0)
    mode: CriticMode = CriticMode.ADVISORY


class HealthRecordRequest(BaseModel):
    """Request to record agent health metrics."""

    agent_id: str
    agent_type: str
    latency_ms: float = Field(..., ge=0)
    success: bool
    load: float = Field(default=0.0, ge=0.0, le=1.0)
    error_message: str | None = None


# --- Response Schemas --------------------------------------------------------


class ExecutionResultSchema(BaseModel):
    """Schema for task execution result."""

    task_id: str
    success: bool
    result_data: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type
    execution_time: float = Field(..., ge=0)
    error_message: str | None = None


class WorkflowPlanSchema(BaseModel):
    """Schema for workflow plan."""

    workflow_id: str
    subtasks: list[SubTaskSchema]
    estimated_total_duration_ms: int
    parallelizable: bool


class OrchestrateTaskResponse(BaseModel):
    """Response from task orchestration."""

    workflow_id: str
    status: TaskStatus
    plan: WorkflowPlanSchema | None = None
    results: list[ExecutionResultSchema] = Field(default_factory=list)
    synthesis: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    total_execution_time: float = 0.0
    critique: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type


class RouteTaskResponse(BaseModel):
    """Response from task routing."""

    task_id: str
    routed_to_agent: str
    agent_type: str | None = None
    routing_method: str  # "cache", "capability_match", "llm", "fallback"
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    alternative_agents: list[str] = Field(default_factory=list)
    cache_hit: bool = False


class SingleJudgeVerdictSchema(BaseModel):
    """Schema for a single judge's verdict in the multi-model panel."""

    judge_index: int
    score: float = Field(..., ge=0.0, le=1.0)
    issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class JudgePanelVerdictSchema(BaseModel):
    """Schema for the aggregated multi-model judge panel result (Tier-3)."""

    consensus: float = Field(..., ge=0.0, le=1.0)
    verdicts: list[SingleJudgeVerdictSchema]
    outliers_removed: int = 0
    failed_judges: int = 0
    raw_scores: list[float] = Field(default_factory=list)


class CritiqueIssueSchema(BaseModel):
    """Schema for critique issue."""

    severity: str  # "critical", "warning", "info"
    message: str
    category: str  # "completeness", "accuracy", "format", "performance"


class CritiqueResponseSchema(BaseModel):
    """Response from critique request."""

    task_id: str
    agent_name: str
    score: float = Field(..., ge=0.0, le=1.0)
    issues: list[CritiqueIssueSchema] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    approved: bool
    should_retry: bool = False
    processing_time_ms: int = 0


class AgentHealthSchema(BaseModel):
    """Schema for individual agent health."""

    agent_id: str
    agent_type: str
    status: HealthStatus
    error_rate: float
    success_rate: float
    avg_latency_ms: float
    current_load: float
    tasks_processed: int
    last_heartbeat: datetime | None = None
    alerts: list[str] = Field(default_factory=list)


class HealthReportResponse(BaseModel):
    """Response for health report."""

    timestamp: datetime
    total_agents: int
    agents: list[AgentHealthSchema]
    by_status: dict[str, int]
    overall_health_score: float
    degraded_agents: list[str] = Field(default_factory=list)


class HealthSnapshotResponse(BaseModel):
    """Response for single agent health snapshot."""

    agent_id: str
    exists: bool
    snapshot: AgentHealthSchema | None = None


class LoadBalancerStatsSchema(BaseModel):
    """Schema for load balancer statistics."""

    name: str
    strategy: str
    total_nodes: int
    healthy_nodes: int
    total_requests: int
    failed_requests: int
    failure_rate: float
    sticky_sessions: int


class OrchestrationStatsResponse(BaseModel):
    """Response for orchestration system statistics."""

    tenant_id: int
    master_orchestrator_id: str
    router_id: str
    health_monitor_id: str
    registered_agents: int
    active_workflows: int
    health_report: HealthReportResponse | None = None
    load_balancer_stats: dict[str, LoadBalancerStatsSchema] = Field(default_factory=dict)
    cache_stats: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type


class WorkflowStatusResponse(BaseModel):
    """Response for workflow status query."""

    workflow_id: str
    exists: bool
    status: TaskStatus | None = None
    subtask_count: int = 0
    completed_subtasks: int = 0
    failed_subtasks: int = 0
    progress_percentage: float = 0.0


class TelemetryDataPoint(BaseModel):
    """Single hourly telemetry entry from critique_hourly_stats."""

    hour: str
    agent_name: str
    avg_score: float = Field(..., ge=0.0, le=1.0)
    critique_count: int = Field(..., ge=0)


class TelemetryResponse(BaseModel):
    """Response schema for GET /critics/telemetry."""

    success: bool
    data: list[TelemetryDataPoint]
