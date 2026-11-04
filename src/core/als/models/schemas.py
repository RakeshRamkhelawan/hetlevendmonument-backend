"""
ALS Pydantic Schemas

All Pydantic models for the Agent Learning System.
Used for validation, serialization, and API contracts.

Fixes:
- #4: Pydantic v2 compatibility (ConfigDict)
- #16: tenant_id type int (consistent)
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

# =============================================================================
# Enums
# =============================================================================


class SignalTier(str, Enum):
    REFLEX = "reflex"
    COGNITIVE = "cognitive"
    EMOTIONAL = "emotional"
    SYNAPTIC = "synaptic"
    BROADCAST = "broadcast"


class SignalStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentStatus(str, Enum):
    REGISTERING = "registering"
    HEALTHY = "healthy"
    STRESSED = "stressed"
    OVERLOADED = "overloaded"
    DEGRADED = "degraded"
    OFFLINE = "offline"


class ThreatLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SwarmRole(str, Enum):
    LEADER = "leader"
    STRATEGIST = "strategist"
    EXECUTOR = "executor"
    REVIEWER = "reviewer"
    SPECIALIST = "specialist"
    SUPPORT = "support"


class SwarmStatus(str, Enum):
    FORMING = "forming"
    ACTIVE = "active"
    COMPLETING = "completing"
    COMPLETED = "completed"
    DISSOLVED = "dissolved"


# =============================================================================
# Base Model
# =============================================================================


class ALSBaseModel(BaseModel):
    """Base model with Pydantic v2 config (Fix #4)."""

    model_config = ConfigDict(
        from_attributes=True,
    )

    @field_serializer("*", when_used="json", check_fields=False)
    def serialize_common_types(self, value: Any) -> Any:  # TODO(TYPE): replace Any with concrete type
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, UUID):
            return str(value)
        return value


# =============================================================================
# Signal Schemas
# =============================================================================


class SignalPayload(BaseModel):
    """Signal payload structure."""

    action: str
    parameters: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    metadata: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type


class SignalCreate(ALSBaseModel):
    """Create a new signal."""

    source_agent_id: str
    target_agent_ids: list[str] = Field(default_factory=list)
    tier: SignalTier
    payload: SignalPayload
    correlation_id: str | None = None


class SignalResponse(ALSBaseModel):
    """Signal response."""

    id: UUID
    tenant_id: int
    signal_id: str
    source_agent_id: str
    target_agent_ids: list[str]
    tier: SignalTier
    payload_hash: str  # Fix #12: SHA-256 hash
    status: SignalStatus
    created_at: datetime
    processed_at: datetime | None = None
    duration_ms: int | None = None


# =============================================================================
# Agent Schemas
# =============================================================================


class AgentCapability(BaseModel):
    """Agent capability definition."""

    name: str
    description: str
    confidence: float = Field(ge=0.0, le=1.0)


class AgentRegister(ALSBaseModel):
    """Register a new agent."""

    agent_id: str
    agent_type: str
    capabilities: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type


class AgentResponse(ALSBaseModel):
    """Agent registration response."""

    id: UUID
    tenant_id: int
    agent_id: str
    agent_type: str
    status: AgentStatus
    capabilities: list[str]
    registered_at: datetime
    last_heartbeat: datetime | None = None
    load_percentage: float


class HeartbeatRequest(ALSBaseModel):
    """Agent heartbeat."""

    agent_id: str
    load_percentage: float = Field(ge=0.0, le=100.0)
    status: AgentStatus
    metrics: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type


# =============================================================================
# Knowledge Schemas
# =============================================================================


class InsightCreate(ALSBaseModel):
    """Create a new insight."""

    agent_id: str
    insight_type: str
    context: str
    content: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    confidence: float = Field(ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type


class InsightResponse(ALSBaseModel):
    """Insight response."""

    id: UUID
    tenant_id: int
    agent_id: str
    insight_type: str
    context: str
    content: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    confidence: float
    reinforcement_count: int
    is_deprecated: bool
    created_at: datetime
    last_reinforced: datetime


class KnowledgeQuery(ALSBaseModel):
    """Query collective knowledge."""

    task_type: str
    context: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    min_confidence: float = Field(default=0.3, ge=0.0, le=1.0)
    limit: int = Field(default=10, ge=1, le=100)


# =============================================================================
# Collaboration Schemas
# =============================================================================


class CollaborationCreate(ALSBaseModel):
    """Record a collaboration."""

    agent_a_id: str
    agent_b_id: str
    task_type: str
    success: bool
    execution_time: float
    quality_score: float = Field(ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type


class PartnerRecommendation(ALSBaseModel):
    """Recommended partner for collaboration."""

    agent_id: str
    score: float
    collaboration_count: int
    average_quality: float
    last_collaboration: datetime | None = None


# =============================================================================
# Swarm Schemas
# =============================================================================


class SwarmMemberCreate(BaseModel):
    """Add member to swarm."""

    agent_id: str
    role: SwarmRole
    capabilities: list[str] = Field(default_factory=list)


class SwarmCreate(ALSBaseModel):
    """Create a new swarm."""

    mission: str
    required_capabilities: list[str]
    max_size: int = Field(default=5, ge=2, le=10)


class SwarmResponse(ALSBaseModel):
    """Swarm response."""

    id: UUID
    swarm_id: str
    tenant_id: int
    mission: str
    required_capabilities: list[str]
    status: SwarmStatus
    members: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    capability_coverage: dict[str, bool]
    created_at: datetime
    activated_at: datetime | None = None
    completed_at: datetime | None = None


class TaskAssignment(BaseModel):
    """Assign task to swarm member."""

    task_id: str
    task_title: str
    task_description: str
    priority: int = Field(ge=1, le=9)
    metadata: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type


# =============================================================================
# Immune System Schemas
# =============================================================================


class ThreatDetected(ALSBaseModel):
    """Threat detection report."""

    tenant_id: int
    agent_id: str
    threat_type: str
    threat_level: ThreatLevel
    threat_signature: str  # SHA-256 hash
    context: dict[str, Any]  # TODO(TYPE): replace Any with concrete type


class AntibodyCreate(ALSBaseModel):
    """Create an antibody."""

    agent_id: str
    name: str
    threat_pattern: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    response_action: str
    auto_execute: bool = False


class IncidentResponse(ALSBaseModel):
    """Incident response."""

    incident_id: str
    status: str
    actions_taken: list[str]
    resolved_at: datetime | None = None


# =============================================================================
# API Response Schemas
# =============================================================================


class APIResponse(ALSBaseModel):
    """Standard API response wrapper."""

    success: bool
    data: Any | None = None  # TODO(TYPE): replace Any with concrete type
    error: str | None = None
    error_code: str | None = None
    request_id: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class PaginatedResponse(APIResponse):
    """Paginated API response."""

    total: int
    page: int
    page_size: int
    pages: int
    has_next: bool
    has_prev: bool
