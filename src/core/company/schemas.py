"""Company Layer Pydantic Schemas - Taak 1.4

API request/response schemas for Company Layer endpoints.
Separates API contract from database models.

Architecture: docs/ARCHITECTURE_PAPERCLIP_INTEGRATION.md S.7
PRD: docs/3-PRDs/PRD_PAPERCLIP_INTEGRATION_v1.0.md S.7
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, List, Literal, Optional, Type
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.core.company.context import AgentExecutionContext, BudgetScope, GoalChain, PolicyScope

# ============================================================================
# Company Schemas
# ============================================================================


class CompanyCreate(BaseModel):
    """Request schema for creating a new company.

    Attributes:
        name: Company name (2-100 characters)
        company_type: Type of company (mkb, zzp, enterprise)
        sector: Industry sector
        mission: Optional company mission statement
        template_id: Optional template to base company on
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=2, max_length=100, description="Company name")
    company_type: Literal["mkb", "zzp", "enterprise"] = Field(
        ..., description="Company type: mkb (SME), zzp (freelancer), or enterprise"
    )
    sector: str = Field(..., min_length=1, max_length=50, description="Industry sector")
    mission: str | None = Field(
        default=None, max_length=1000, description="Company mission statement"
    )
    template_id: UUID | None = Field(default=None, description="Template ID to instantiate from")


class CompanyUpdate(BaseModel):
    """Request schema for updating a company.

    All fields are optional for partial updates.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(
        default=None, min_length=2, max_length=100, description="Company name"
    )
    company_type: Literal["mkb", "zzp", "enterprise"] | None = Field(
        default=None, description="Company type"
    )
    sector: str | None = Field(
        default=None, min_length=1, max_length=50, description="Industry sector"
    )
    mission: str | None = Field(
        default=None, max_length=1000, description="Company mission statement"
    )


class CompanyResponse(BaseModel):
    """Response schema for company data.

    Includes computed fields like departments_count and goals_count.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(description="Company unique identifier")
    tenant_id: int = Field(description="Tenant ID for isolation")
    name: str = Field(description="Company name")
    company_type: str = Field(description="Company type")
    sector: str = Field(description="Industry sector")
    mission: str | None = Field(default=None, description="Mission statement")
    status: str = Field(description="Company status (active, suspended, etc.)")
    departments_count: int = Field(default=0, description="Number of departments (computed)")
    goals_count: int = Field(default=0, description="Number of goals (computed)")
    created_at: datetime = Field(description="Creation timestamp")


class CompanyListResponse(BaseModel):
    """Response schema for listing companies."""

    companies: list[CompanyResponse] = Field(description="List of companies")
    total: int = Field(description="Total number of companies")


# ============================================================================
# Department Schemas
# ============================================================================


class DepartmentCreate(BaseModel):
    """Request schema for creating a department.

    Attributes:
        name: Department name
        parent_department_id: Optional parent department for hierarchy
        head_user_id: Optional user ID of department head
        board_role: Board role associated with this department
        budget_monthly_tokens: Monthly token budget for the department
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=100, description="Department name")
    parent_department_id: UUID | None = Field(
        default=None, description="Parent department ID for hierarchy"
    )
    head_user_id: UUID | None = Field(default=None, description="Department head user ID")
    board_role: str | None = Field(
        default=None, max_length=50, description="Board role (e.g., CTO, CFO)"
    )
    budget_monthly_tokens: int | None = Field(
        default=None, ge=0, description="Monthly token budget"
    )


class DepartmentUpdate(BaseModel):
    """Request schema for updating a department.

    Includes expected_version for optimistic locking.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(
        default=None, min_length=1, max_length=100, description="Department name"
    )
    parent_department_id: UUID | None = Field(default=None, description="Parent department ID")
    head_user_id: UUID | None = Field(default=None, description="Department head user ID")
    board_role: str | None = Field(default=None, max_length=50, description="Board role")
    budget_monthly_tokens: int | None = Field(
        default=None, ge=0, description="Monthly token budget"
    )
    expected_version: int | None = Field(
        default=None, ge=1, description="Expected current version for optimistic locking"
    )


class DepartmentResponse(BaseModel):
    """Response schema for department data."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(description="Department unique identifier")
    company_id: UUID | None = Field(default=None, description="Parent company ID")
    name: str = Field(description="Department name")
    parent_department_id: UUID | None = Field(default=None, description="Parent department ID")
    head_user_id: UUID | None = Field(default=None, description="Department head user ID")
    board_role: str | None = Field(default=None, description="Board role")
    budget_monthly_tokens: int | None = Field(default=None, description="Token budget")
    domain_pack_ids: list[str] = Field(
        default_factory=list, description="Associated domain pack IDs"
    )
    version: int = Field(default=1, description="Version for optimistic locking")
    children_count: int = Field(default=0, description="Number of child departments (computed)")


class OrgChartResponse(BaseModel):
    """Response schema for organization chart."""

    departments: list[DepartmentResponse] = Field(description="All departments")
    tree_structure: dict[str, Any] = Field(description="Hierarchical tree structure")  # TODO(TYPE): replace Any with concrete type


# ============================================================================
# Goal Schemas
# ============================================================================


class GoalCreate(BaseModel):
    """Request schema for creating a goal.

    Supports goal hierarchy: mission -> strategic -> project -> task
    """

    model_config = ConfigDict(extra="forbid")

    goal_type: Literal["mission", "strategic", "project", "task"] = Field(
        ..., description="Type of goal in hierarchy"
    )
    title: str = Field(..., min_length=1, max_length=200, description="Goal title")
    description: str | None = Field(
        default=None, max_length=2000, description="Detailed description"
    )
    parent_goal_id: UUID | None = Field(default=None, description="Parent goal ID for hierarchy")
    department_id: UUID | None = Field(
        default=None, description="Department responsible for this goal"
    )
    kpis: list[str] = Field(default_factory=list, description="Key performance indicators")
    deadline: datetime | None = Field(default=None, description="Target completion date")


class GoalUpdate(BaseModel):
    """Request schema for updating a goal."""

    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(
        default=None, min_length=1, max_length=200, description="Goal title"
    )
    description: str | None = Field(
        default=None, max_length=2000, description="Detailed description"
    )
    status: str | None = Field(default=None, description="Goal status")
    progress_pct: int | None = Field(
        default=None, ge=0, le=100, description="Progress percentage (0-100)"
    )
    kpis: list[str] | None = Field(default=None, description="Key performance indicators")
    deadline: datetime | None = Field(default=None, description="Target completion date")


class GoalResponse(BaseModel):
    """Response schema for goal data."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(description="Goal unique identifier")
    company_id: UUID | None = Field(default=None, description="Parent company ID")
    goal_type: str = Field(description="Goal type")
    title: str = Field(description="Goal title")
    description: str | None = Field(default=None, description="Detailed description")
    status: str = Field(description="Goal status")
    progress_pct: int = Field(default=0, description="Progress percentage")
    kpis: list[str] = Field(default_factory=list, description="KPIs")
    deadline: datetime | None = Field(default=None, description="Target date")
    parent_goal_id: UUID | None = Field(default=None, description="Parent goal ID")
    children_count: int = Field(default=0, description="Number of child goals (computed)")

    @field_validator("kpis", mode="before")
    @classmethod
    def validate_kpis(cls, v: object) -> object:
        """Handle JSON kpis from database - convert dict or None to list."""
        if v is None or v == {}:
            return []
        if isinstance(v, dict):
            # Convert dict to list of "key: value" strings
            return [f"{k}: {v_val}" for k, v_val in v.items()]
        return v


class GoalAncestryResponse(BaseModel):
    """Response schema for goal ancestry chain."""

    chain: list[GoalResponse] = Field(description="Goals from mission to task")
    goal_chain: GoalChain | None = Field(
        default=None, description="GoalChain object for context"
    )


class GoalTreeResponse(BaseModel):
    """Response schema for goal tree visualization."""

    goals: list[GoalResponse] = Field(description="All goals")
    tree_structure: dict[str, Any] = Field(description="Hierarchical tree structure")  # TODO(TYPE): replace Any with concrete type


# ============================================================================
# External Agent Schemas
# ============================================================================


class ExternalAgentRegister(BaseModel):
    """Request schema for registering an external agent.

    Used by external agents to register with the platform.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=100, description="Agent name")
    runtime: str = Field(
        ..., min_length=1, max_length=50, description="Runtime environment (e.g., python-3.11)"
    )
    capabilities: list[str] = Field(..., min_length=1, description="List of agent capabilities")
    heartbeat_interval_seconds: int = Field(
        default=30, ge=10, le=300, description="Heartbeat interval in seconds"
    )
    webhook_url: str | None = Field(
        default=None, max_length=500, description="Webhook URL for callbacks"
    )
    department_id: UUID | None = Field(
        default=None, description="Department this agent belongs to"
    )

    @field_validator("webhook_url")
    @classmethod
    def validate_webhook_url(cls, v: str | None) -> str | None:
        """Validate webhook URL if provided."""
        if v is not None and not v.startswith(("http://", "https://")):
            raise ValueError("webhook_url must start with http:// or https://")
        return v


class ExternalAgentResponse(BaseModel):
    """Response schema for external agent data."""

    model_config = ConfigDict(from_attributes=True)

    agent_id: UUID = Field(description="Agent unique identifier")
    name: str = Field(description="Agent name")
    runtime: str = Field(description="Runtime environment")
    capabilities: list[str] = Field(description="Agent capabilities")
    status: str = Field(description="Agent status")
    last_heartbeat_at: datetime | None = Field(description="Last heartbeat timestamp")
    metrics: dict[str, Any] = Field(default_factory=dict, description="Agent metrics")  # TODO(TYPE): replace Any with concrete type


class HeartbeatRequest(BaseModel):
    """Request schema for agent heartbeat.

    Sent periodically by external agents to report status.
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["idle", "busy", "error"] = Field(..., description="Current agent status")
    current_task_id: UUID | None = Field(
        default=None, description="ID of task currently being processed"
    )
    progress: float | None = Field(
        default=None, ge=0, le=100, description="Task progress percentage"
    )
    metrics: dict[str, Any] = Field(default_factory=dict, description="Current agent metrics")  # TODO(TYPE): replace Any with concrete type


class HeartbeatResponse(BaseModel):
    """Response schema for heartbeat acknowledgment.

    Contains pending tasks for the agent to process.
    """

    ack: bool = Field(default=True, description="Heartbeat acknowledged")
    pending_tasks: list[str] = Field(default_factory=list, description="List of pending task IDs")


class TaskNextResponse(BaseModel):
    """Response schema for next task assignment.

    Sent to agent when work is available.
    """

    model_config = ConfigDict(extra="forbid")

    task_id: UUID = Field(description="Task unique identifier")
    action: str = Field(description="Action to perform")
    input: dict[str, Any] = Field(default_factory=dict, description="Task input data")  # TODO(TYPE): replace Any with concrete type
    context: AgentExecutionContext = Field(description="Execution context with goal chain")
    sla_seconds: int = Field(default=3600, ge=0, description="SLA timeout in seconds")
    domain_pack: dict[str, Any] | None = Field(  # TODO(TYPE): replace Any with concrete type
        default=None, description="Domain pack configuration"
    )


class TaskCompleteRequest(BaseModel):
    """Request schema for task completion.

    Sent by agent when task is finished.
    """

    model_config = ConfigDict(extra="forbid")

    status: Literal["completed", "failed"] = Field(..., description="Task completion status")
    output: dict[str, Any] = Field(default_factory=dict, description="Task output data")  # TODO(TYPE): replace Any with concrete type
    reasoning_trace: str | None = Field(
        default=None, max_length=10000, description="Reasoning trace for debugging"
    )


# ============================================================================
# Board Governance Schemas
# ============================================================================


class BoardDecisionResponse(BaseModel):
    """Response schema for board decision data."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(description="Decision unique identifier")
    company_id: UUID = Field(description="Company ID")
    requested_by: UUID = Field(description="User who requested decision")
    board_role: str = Field(description="Required board role for approval")
    action_type: str = Field(description="Type of action requiring approval")
    action_context: dict[str, Any] = Field(default_factory=dict, description="Action context data")  # TODO(TYPE): replace Any with concrete type
    goal_id: UUID | None = Field(default=None, description="Related goal ID if applicable")
    decision: Literal["approved", "rejected"] | None = Field(
        default=None, description="Decision outcome"
    )
    decided_by: UUID | None = Field(default=None, description="User who made the decision")
    reason: str | None = Field(default=None, description="Decision reason")
    decided_at: datetime | None = Field(default=None, description="Decision timestamp")
    created_at: datetime = Field(description="Request timestamp")


class BoardApproveRequest(BaseModel):
    """Request schema for approving a board decision.

    Reason is optional for approvals.
    """

    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(default=None, max_length=1000, description="Approval reason")


class BoardRejectRequest(BaseModel):
    """Request schema for rejecting a board decision.

    Reason is required for rejections.
    """

    model_config = ConfigDict(extra="forbid")

    reason: str = Field(..., min_length=1, max_length=1000, description="Rejection reason")


class BoardQueueResponse(BaseModel):
    """Response schema for board approval queue."""

    decisions: list[BoardDecisionResponse] = Field(description="Pending decisions")
    pending_count: int = Field(description="Total number of pending decisions")


# ============================================================================
# Template Schemas
# ============================================================================


class TemplateResponse(BaseModel):
    """Response schema for company template data."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(description="Template unique identifier")
    name: str = Field(description="Template name")
    company_type: str = Field(description="Applicable company type")
    sector: str = Field(description="Applicable sector")
    description: str = Field(description="Template description")
    is_platform_template: bool = Field(description="Whether this is a built-in template")
    usage_count: int = Field(description="Number of times used")
    rating_avg: float | None = Field(ge=0, le=5, description="Average rating (0-5)")


class TemplateInstantiateRequest(BaseModel):
    """Request schema for instantiating a template.

    Creates a new company based on a template.
    """

    model_config = ConfigDict(extra="forbid")

    template_id: UUID = Field(description="Template to instantiate")
    company_name: str = Field(
        ..., min_length=2, max_length=100, description="Name for the new company"
    )
    customizations: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict, description="Custom values for template variables"
    )


class TemplateContributeRequest(BaseModel):
    """Request schema for contributing a template.

    Allows tenants to share their company configurations as templates.
    Secrets are automatically scrubbed before storage.
    """

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=2, max_length=200, description="Template name")
    company_type: str = Field(
        ..., min_length=1, max_length=20, description="Company type (mkb, zzp, enterprise)"
    )
    sector: str = Field(..., min_length=1, max_length=100, description="Industry sector")
    description: str = Field(..., min_length=1, max_length=2000, description="Template description")
    template_definition: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        ..., description="Complete template definition (departments, goals, etc.)"
    )


class TemplateListResponse(BaseModel):
    """Response schema for template list."""

    templates: list[TemplateResponse] = Field(description="List of templates")
    total: int = Field(description="Total number of templates")


# ============================================================================
# Onboarding Schemas
# ============================================================================


class OnboardingAIMatchRequest(BaseModel):
    """Request schema for AI-powered template matching.

    Describes company needs in natural language.
    """

    model_config = ConfigDict(extra="forbid")

    description: str = Field(
        ..., min_length=10, max_length=2000, description="Description of company needs"
    )


class OnboardingAIMatchResponse(BaseModel):
    """Response schema for AI template matching.

    Returns best matching template with confidence score.
    """

    template_id: UUID = Field(description="Recommended template ID")
    template_name: str = Field(description="Template name")
    confidence: float = Field(..., ge=0, le=1, description="Match confidence (0-1)")
    match_reason: str = Field(description="Explanation of why this template matches")


class OnboardingCompleteRequest(BaseModel):
    """Request schema for completing onboarding.

    Final step to create company with optional template and initial goals.
    """

    model_config = ConfigDict(extra="forbid")

    template_id: UUID | None = Field(default=None, description="Template to use (optional)")
    company_name: str = Field(..., min_length=2, max_length=100, description="Company name")
    company_type: Literal["mkb", "zzp", "enterprise"] = Field(..., description="Company type")
    sector: str = Field(..., min_length=1, max_length=50, description="Industry sector")
    mission: str | None = Field(default=None, max_length=1000, description="Company mission")
    goals: list[GoalCreate] | None = Field(default=None, description="Initial goals to create")


# ============================================================================
# Error Response Schemas
# ============================================================================


class ConflictResponse(BaseModel):
    """Response schema for 409 Conflict errors.

    Used for optimistic locking conflicts and duplicate resources.

    Example:
        {
            "detail": "Department is gewijzigd door andere gebruiker",
            "error_code": "CONFLICT",
            "current_version": 5,
            "conflicting_user": "user@example.com"
        }
    """

    model_config = ConfigDict(extra="forbid")

    detail: str = Field(..., description="Human-readable error description")
    error_code: str = Field(default="CONFLICT", description="Error code for programmatic handling")
    current_version: int = Field(..., description="Current resource version")
    conflicting_user: str | None = Field(
        default=None, description="User who caused the conflict"
    )
