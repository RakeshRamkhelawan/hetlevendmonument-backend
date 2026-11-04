"""
Pydantic schemas for Sprint 2 Capability Agents
Defines request/response contracts for Planner, Retriever, Executor, Compliance, and Reviewer agents
"""

from enum import Enum
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field

# ============================================================================
# DECISION ENUMS
# ============================================================================


class ConfidenceLevel(str, Enum):
    """Confidence levels for procedure matching"""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ExecutionDecision(str, Enum):
    """Orchestration decision from PlannerAgent"""

    AUTO_EXECUTE = "auto_execute"
    USER_CONFIRM = "user_confirm"
    NO_MATCH = "no_match"


class ComplianceStatus(str, Enum):
    """Result of compliance check"""

    ALLOWED = "allowed"
    BLOCKED = "blocked"
    WARNING = "warning"


class ReviewStatus(str, Enum):
    """Human review decision"""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITH_MODIFICATIONS = "with_modifications"
    NEEDS_REVIEW = "needs_review"  # Legacy compatibility


class AgentStatus(str, Enum):
    """Agent operational status"""

    ACTIVE = "active"
    INACTIVE = "inactive"
    MAINTENANCE = "maintenance"
    DEPRECATED = "deprecated"


# ============================================================================
# SCORING SCHEMAS
# ============================================================================


class ScoredProcedure(BaseModel):
    """A procedure with its calculated confidence score"""

    procedure_id: UUID
    procedure_name: str
    domain_pack_id: UUID
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    tag_score: float = Field(..., ge=0.0, le=1.0)
    semantic_score: float = Field(..., ge=0.0, le=1.0)
    history_score: float = Field(..., ge=0.0, le=1.0)
    recency_score: float = Field(..., ge=0.0, le=1.0)
    user_override_score: float = Field(..., ge=0.0, le=1.0)
    is_ambiguous: bool = False
    intent_match_reason: str | None = None


class ConfidenceScorerInput(BaseModel):
    """Input to ConfidenceScorer.score()"""

    user_intent: str = Field(..., description="Natural language intent from user")
    # TODO(TYPE): replace Any with concrete type
    candidate_procedures: list[dict[str, Any]] = (
        Field(  # TODO(TYPE): replace Any with concrete type
            ..., description="List of candidate procedures from registry"
        )
    )
    tenant_id: UUID
    user_id: UUID
    context: dict[str, object] | None = Field(
        default_factory=dict, description="Additional context"
    )


class ConfidenceScorerOutput(BaseModel):
    """Output from ConfidenceScorer.score()"""

    scored_procedures: list[ScoredProcedure]
    top_match: ScoredProcedure | None = None
    ambiguous_matches: list[ScoredProcedure] = Field(default_factory=list)


# ============================================================================
# PLANNER AGENT SCHEMAS
# ============================================================================


class ExecutionStep(BaseModel):
    """A single step in an execution plan"""

    step_number: int
    action: str
    description: str | None = None
    # TODO(TYPE): replace Any with concrete type
    parameters: dict[str, Any] = Field(
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type
    compliance_checks: list[str] = Field(default_factory=list)


class PlannerTask(BaseModel):
    """Input to PlannerAgent"""

    user_intent: str
    procedure: ScoredProcedure
    tenant_id: UUID
    user_id: UUID
    domain_pack_context: dict[str, object] | None = Field(default_factory=dict)


class PlannerResult(BaseModel):
    """Output from PlannerAgent"""

    execution_plan: list[ExecutionStep]
    estimated_duration_minutes: int
    confidence_in_plan: float = Field(..., ge=0.0, le=1.0)
    decision: ExecutionDecision
    reasoning: str
    requires_human_approval: bool


# ============================================================================
# RETRIEVER AGENT SCHEMAS
# ============================================================================


class RetrieverTask(BaseModel):
    """Input to RetrieverAgent"""

    query: str
    filters: dict[str, object] = Field(default_factory=dict)
    tenant_id: UUID
    max_results: int = Field(default=10, ge=1, le=100)


class RetrievalResult(BaseModel):
    """A single retrieval result"""

    source_id: UUID
    source_type: str  # kb_article, procedure, template, etc.
    content: str
    relevance_score: float = Field(..., ge=0.0, le=1.0)
    metadata: dict[str, object] = Field(default_factory=dict)


class RetrieverResult(BaseModel):
    """Output from RetrieverAgent"""

    results: list[RetrievalResult]
    total_count: int


# ============================================================================
# EXECUTOR AGENT SCHEMAS
# ============================================================================


class ExecutorTask(BaseModel):
    """Input to ExecutorAgent"""

    tool_name: str
    arguments: dict[str, object]
    tenant_id: UUID
    user_id: UUID
    execution_context: dict[str, object] | None = Field(default_factory=dict)


class ExecutorResult(BaseModel):
    """Output from ExecutorAgent"""

    success: bool
    result: object | None = None
    error: str | None = None
    audit_log_id: UUID | None = None
    retries_attempted: int = 0


# ============================================================================
# COMPLIANCE AGENT SCHEMAS
# ============================================================================


class ComplianceContext(BaseModel):
    """Context for compliance checking"""

    action: str
    target_resource: str
    # TODO(TYPE): replace Any with concrete type
    parameters: dict[str, Any] = Field(
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type
    tenant_id: UUID
    user_id: UUID


class ComplianceIssue(BaseModel):
    """A compliance issue detected"""

    policy_violated: str
    severity: str  # info, warning, critical
    message: str
    remediation: str | None = None


class ComplianceResult(BaseModel):
    """Output from ComplianceAgent"""

    status: ComplianceStatus
    issues: list[ComplianceIssue] = Field(default_factory=list)
    passed_checks: list[str] = Field(default_factory=list)


# ============================================================================
# REVIEWER AGENT SCHEMAS
# ============================================================================


class ReviewerTask(BaseModel):
    """Input to ReviewerAgent for review request"""

    decision_description: str = Field(..., min_length=1)
    context: dict[str, object] = Field(default_factory=dict)
    tenant_id: UUID
    user_id: UUID
    assigned_reviewer_id: UUID | None = None


class ReviewerContext(BaseModel):
    """Context for review decision (legacy)"""

    execution_plan: PlannerResult
    execution_results: list[ExecutorResult] = Field(default_factory=list)
    compliance_check: ComplianceResult | None = None
    tenant_id: UUID
    user_id: UUID


class ReviewDecision(BaseModel):
    """A reviewable decision point"""

    decision_id: str
    title: str
    description: str
    risk_score: float = Field(..., ge=0.0, le=1.0)
    requires_manager_approval: bool


class ReviewerResult(BaseModel):
    """Output from ReviewerAgent"""

    review_id: UUID
    status: ReviewStatus
    decision_description: str
    context: dict[str, object] = Field(default_factory=dict)
    tenant_id: UUID
    user_id: UUID
    assigned_reviewer_id: UUID | None = None
    submitted_at: datetime
    reviewed_at: datetime | None = None
    reviewer_id: UUID | None = None
    reviewer_comments: str | None = None
    # Legacy fields for compatibility
    decisions: list[ReviewDecision] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    escalation_required: bool = False
    escalation_reason: str | None = None


# ============================================================================
# PROCEDURE RESOLVER SCHEMAS
# ============================================================================


class ProcedureResolverInput(BaseModel):
    """Input to ProcedureResolver.resolve()"""

    user_intent: str
    tenant_id: UUID
    user_id: UUID
    domain_filter: str | None = None


class ProcedureResolverOutput(BaseModel):
    """Output from ProcedureResolver.resolve()"""

    decision: ExecutionDecision
    matched_procedure: ScoredProcedure | None = None
    execution_plan: PlannerResult | None = None
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str
    ambiguous_alternatives: list[ScoredProcedure] = Field(default_factory=list)


# ============================================================================
# AGENT REGISTRY SCHEMAS
# ============================================================================


class AgentRegistration(BaseModel):
    """Input to AgentRegistry.register_agent()"""

    agent_type: str = Field(..., min_length=1)
    agent_name: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1)
    capabilities: list[str] = Field(default_factory=list)
    tenant_id: UUID
    description: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class AgentMetadata(BaseModel):
    """Agent registration metadata"""

    agent_id: UUID
    agent_type: str
    agent_name: str
    version: str
    capabilities: list[str]
    tenant_id: UUID
    status: AgentStatus
    description: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    registered_at: datetime
    updated_at: datetime
