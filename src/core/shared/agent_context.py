"""Shared execution context models -- no project-level imports.

Moved from src.core.company.context to break the shared -> domain_pack
circular dependency. src.core.company.context re-exports these types for
backward compatibility with all existing callers.
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator


class GoalChain(BaseModel):
    """Goal hierarchy validator for mission -> strategic -> project -> task chain."""

    model_config = {"frozen": False, "validate_assignment": True}

    mission_id: UUID | None = None
    mission_title: str | None = None
    strategic_goal_id: UUID | None = None
    strategic_goal_title: str | None = None
    project_goal_id: UUID | None = None
    project_goal_title: str | None = None
    task_goal_id: UUID | None = None
    task_goal_title: str | None = None

    def is_complete(self) -> bool:
        """Return True when both mission_id and task_goal_id are set."""
        return self.mission_id is not None and self.task_goal_id is not None

    def depth(self) -> int:
        """Count non-None goal IDs (0-4 range)."""
        return sum(
            1
            for v in (
                self.mission_id,
                self.strategic_goal_id,
                self.project_goal_id,
                self.task_goal_id,
            )
            if v is not None
        )

    @classmethod
    def from_ancestry(cls, goals: list[dict[str, Any]]) -> GoalChain:  # TODO(TYPE): replace Any with concrete type
        """Build GoalChain from a list of goal ancestry dicts."""
        if not goals:
            return cls()

        type_to_id_field = {
            "mission": "mission_id",
            "strategic": "strategic_goal_id",
            "project": "project_goal_id",
            "task": "task_goal_id",
        }
        type_to_title_field = {
            "mission": "mission_title",
            "strategic": "strategic_goal_title",
            "project": "project_goal_title",
            "task": "task_goal_title",
        }

        kwargs: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        for goal in goals:
            goal_type = goal.get("goal_type", "").lower()
            if goal_type in type_to_id_field:
                goal_id = goal.get("id")
                if isinstance(goal_id, str):
                    goal_id = UUID(goal_id)
                kwargs[type_to_id_field[goal_type]] = goal_id
                title = goal.get("title")
                if title:
                    kwargs[type_to_title_field[goal_type]] = title

        return cls(**kwargs)


class PolicyScope(BaseModel):
    """Policy enforcement scope for agent actions."""

    model_config = {"frozen": False}

    risk_level: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"] = Field(
        default="LOW", description="Risk level for policy enforcement"
    )
    requires_approval: bool = Field(default=False, description="Whether board approval is required")
    approval_board_role: str | None = Field(
        default=None, description="Board role that can approve (e.g. CTO, CFO)"
    )
    allowed_actions: list[str] = Field(default_factory=list, description="Whitelisted actions")
    forbidden_actions: list[str] = Field(default_factory=list, description="Blacklisted actions")


class BudgetScope(BaseModel):
    """Budget tracking for agent token consumption."""

    model_config = {"frozen": False}

    monthly_token_budget: int | None = Field(
        default=None, ge=0, description="Monthly token budget limit"
    )
    tokens_consumed_this_month: int | None = Field(
        default=None, ge=0, description="Tokens consumed this month"
    )
    budget_remaining_pct: float | None = Field(
        default=None, ge=0.0, le=1.0, description="Remaining budget percentage (0.0-1.0)"
    )

    @model_validator(mode="after")
    def calculate_remaining_pct(self) -> BudgetScope:
        """Calculate budget_remaining_pct from budget and consumption."""
        budget = self.monthly_token_budget
        consumed = self.tokens_consumed_this_month

        if budget is not None and consumed is not None:
            if budget > 0:
                remaining = max(0, budget - consumed)
                self.budget_remaining_pct = remaining / budget
            else:
                self.budget_remaining_pct = 0.0
        else:
            self.budget_remaining_pct = None

        return self


class AgentExecutionContext(BaseModel):
    """Canonical execution context for all agent operations.

    Single source of truth for tenant isolation, goal hierarchy, policy
    enforcement, budget constraints and execution tracing.
    """

    model_config = {"frozen": False, "validate_assignment": True}

    # Required fields
    tenant_id: int = Field(..., description="Tenant identifier for isolation")
    task_id: UUID = Field(..., description="Task identifier")
    trace_id: UUID = Field(..., description="OpenTelemetry trace ID")

    # Company context
    company_id: UUID | None = Field(
        default=None, description="Company UUID (None in degraded mode)"
    )
    company_type: str | None = Field(default=None, description="Company type: mkb, zzp, enterprise")
    sector: str | None = Field(default=None, description="Industry sector")

    # Department context
    department_id: UUID | None = Field(default=None, description="Department UUID")
    department_name: str | None = Field(default=None, description="Department name")
    board_role: str | None = Field(default=None, description="Board role for approval routing")

    # Execution context
    pack_id: UUID | None = Field(default=None, description="Domain pack UUID")
    pack_name: str | None = Field(default=None, description="Domain pack name")
    procedure_id: UUID | None = Field(default=None, description="Procedure UUID")

    # Scopes
    goal_chain: GoalChain = Field(default_factory=GoalChain, description="Goal hierarchy chain")
    policy_scope: PolicyScope = Field(
        default_factory=PolicyScope, description="Policy enforcement scope"
    )
    budget_scope: BudgetScope = Field(
        default_factory=BudgetScope, description="Budget tracking scope"
    )

    # Execution settings
    sla_seconds: int | None = Field(default=None, ge=0, description="SLA timeout in seconds")
    is_degraded: bool = Field(default=False, description="Whether context is in degraded mode")

    @field_validator(
        "company_id",
        "department_id",
        "pack_id",
        "procedure_id",
        "task_id",
        "trace_id",
        mode="before",
    )
    @classmethod
    def convert_uuid_strings(cls, v: Any) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Convert string UUIDs to UUID objects."""
        if isinstance(v, str):
            return UUID(v)
        return v

    def validate_completeness(self) -> tuple[bool, list[str]]:
        """Return (is_valid, missing_fields). Sets is_degraded when incomplete."""
        missing_fields: list[str] = []
        if self.company_id is None:
            missing_fields.append("company_id")
        if not self.goal_chain.is_complete():
            missing_fields.append("goal_chain")
        is_valid = len(missing_fields) == 0
        self.is_degraded = not is_valid
        return is_valid, missing_fields

    def to_dict(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Serialize to dict (JSON-compatible)."""
        return self.model_dump(mode="json")

    def get_trace_context(self) -> dict[str, str]:
        """Return OpenTelemetry trace context headers."""
        return {
            "trace_id": str(self.trace_id),
            "tenant_id": str(self.tenant_id),
            "company_id": str(self.company_id) if self.company_id else "",
        }
