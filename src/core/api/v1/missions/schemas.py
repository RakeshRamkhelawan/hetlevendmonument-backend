"""
Missions domain shared schemas, enums, and helper functions (ADR-033).

Centralises Pydantic models and pure-logic helpers so sub-routers stay thin.
"""

import logging
from enum import Enum
from typing import Any
from uuid import UUID

from fastapi import HTTPException, status
from pydantic import BaseModel, Field

from src.core.middleware.tenant_context import get_current_tenant_id
from src.core.models.mission_models import Mission as MissionORM

logger = logging.getLogger(__name__)


# ============================================================================
# Enums
# ============================================================================


class MissionStatus(str, Enum):
    """Mission execution status."""

    PLANNED = "planned"
    APPROVED = "approved"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class StepStatus(str, Enum):
    """Mission step status."""

    PENDING = "pending"
    APPROVED = "approved"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"
    SKIPPED = "skipped"


class AgentType(str, Enum):
    """Agent types."""

    WORKFLOW = "workflow"
    MEMORY = "memory"
    GOVERNANCE = "governance"
    SPECIALIST = "specialist"


# ============================================================================
# Pydantic Models
# ============================================================================


class MissionStep(BaseModel):
    """A single step in a mission."""

    id: str = Field(..., description="Step ID")
    order: int = Field(..., description="Step order")
    description: str = Field(..., description="Step description")
    action_type: str = Field(..., description="Type of action")
    status: StepStatus = Field(default=StepStatus.PENDING, description="Step status")
    requires_approval: bool = Field(True, description="Whether step requires approval")
    approved_by: str | None = Field(None, description="User who approved")
    approved_at: str | None = Field(None, description="Approval timestamp")
    rejected_by: str | None = Field(None, description="User who rejected")
    rejected_at: str | None = Field(None, description="Rejection timestamp")
    rejection_reason: str | None = Field(None, description="Reason for rejection")
    duration_ms: int | None = Field(None, description="Execution duration")
    cost_usd: float | None = Field(None, description="Execution cost")
    error: str | None = Field(None, description="Error message if failed")


class ExplainabilityChain(BaseModel):
    """5-step reasoning chain for explainability."""

    step_1_input_preprocessing: str = Field(..., description="Input preprocessing details")
    step_2_model_inference: str = Field(..., description="Model inference details")
    step_3_confidence_calculation: str = Field(..., description="Confidence calculation")
    step_4_recommendation: str = Field(..., description="Recommendation details")
    step_5_alternative_considered: str = Field(..., description="Alternatives considered")
    execution_id: str = Field(..., description="Execution ID")
    model_used: str = Field(..., description="Model used")
    tokens_used: int = Field(0, description="Tokens used")
    latency_ms: int = Field(0, description="Latency in ms")
    cost_usd: float = Field(0.0, description="Cost in USD")


class ImpactSummary(BaseModel):
    """Impact summary for a mission."""

    time_saved: str | None = Field(None, description="Estimated time saved")
    cost_impact: float | None = Field(None, description="Cost impact")
    risk_score: float = Field(0.0, ge=0, le=100, description="Risk score 0-100")
    bias_detected: list[str] = Field(default_factory=list, description="Detected biases")


class Mission(BaseModel):
    """Mission model."""

    id: str = Field(..., description="Mission ID")
    title: str = Field(..., description="Mission title")
    description: str = Field("", description="Mission description")
    agent_type: AgentType = Field(..., description="Agent type")
    status: MissionStatus = Field(default=MissionStatus.PLANNED, description="Mission status")
    tenant_id: int = Field(..., description="Tenant ID")
    created_by: str = Field(..., description="User who created")
    created_at: str = Field(..., description="Creation timestamp")
    updated_at: str | None = Field(None, description="Last update timestamp")
    steps: list[MissionStep] = Field(default_factory=list, description="Mission steps")
    impact: ImpactSummary | None = Field(None, description="Impact summary")
    reasoning_chain: ExplainabilityChain | None = Field(None, description="Explainability chain")
    estimated_duration_ms: int | None = Field(None, description="Estimated duration")
    total_cost_usd: float | None = Field(None, description="Total cost")


class CreateMissionRequest(BaseModel):
    """Request to create a mission."""

    title: str
    description: str
    agent_type: AgentType
    steps: list[MissionStep] = Field(default_factory=list)


class ApproveRequest(BaseModel):
    """Request to approve a mission step."""

    step_id: str | None = Field(
        None,
        description="Specific step to approve (optional, defaults to next pending)",
    )
    comment: str | None = Field(None, description="Approval comment")


class RejectRequest(BaseModel):
    """Request to reject a mission step."""

    step_id: str | None = Field(
        None, description="Specific step to reject (optional, defaults to next pending)"
    )
    reason: str = Field(..., description="Rejection reason (required)")
    comment: str | None = Field(None, description="Additional comment")


class MissionResponse(BaseModel):
    """Response for mission operations."""

    mission: Mission
    message: str
    action: str
    timestamp: str


class MissionListResponse(BaseModel):
    """Response for mission list."""

    missions: list[Mission]
    total: int
    page: int
    page_size: int


# ============================================================================
# Helper Functions
# ============================================================================


async def get_tenant() -> int:
    """Get tenant ID from JWT middleware context -- fail-secure guard."""
    tenant_id = get_current_tenant_id()
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required. Ensure JWT contains tenant_id.",
        )
    return tenant_id


def get_user_id(current_user: Any) -> str:  # TODO(TYPE): replace Any with concrete type
    """Extract user ID from current user (handles both User model and dict)."""
    if isinstance(current_user, dict):
        return str(current_user.get("user_id") or current_user.get("id") or "unknown")
    if hasattr(current_user, "id"):
        return str(current_user.id)
    return "unknown"


def _parse_mission_id(mission_id: str) -> UUID:
    """Validate and parse mission_id string to UUID."""
    try:
        return UUID(mission_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid mission ID format",
        ) from exc


def _orm_to_pydantic(orm: MissionORM) -> Mission:
    """Convert Mission ORM instance to Pydantic Mission model."""
    payload = orm.payload or {}
    return Mission(
        id=str(orm.id),
        title=orm.title,
        description=orm.description or "",
        agent_type=AgentType(orm.agent_type),
        status=MissionStatus(orm.status),
        tenant_id=orm.tenant_id,
        created_by=orm.created_by,
        created_at=orm.created_at.isoformat() if orm.created_at else "",
        updated_at=orm.updated_at.isoformat() if orm.updated_at else None,
        steps=[MissionStep(**s) for s in payload.get("steps", [])],
        impact=ImpactSummary(**payload["impact"]) if payload.get("impact") else None,
        reasoning_chain=(
            ExplainabilityChain(**payload["reasoning_chain"])
            if payload.get("reasoning_chain")
            else None
        ),
        estimated_duration_ms=payload.get("estimated_duration_ms"),
        total_cost_usd=payload.get("total_cost_usd"),
    )


def find_next_pending_step(steps: list[dict[str, Any]]) -> dict[str, Any] | None:  # TODO(TYPE): replace Any with concrete type
    """Find the next pending step that requires approval."""
    for step in sorted(steps, key=lambda s: s.get("order", 0)):
        if step.get("status") == "pending" and step.get("requires_approval", True):
            return step
    return None


def update_mission_status(steps: list[dict[str, Any]]) -> str:  # TODO(TYPE): replace Any with concrete type
    """Update mission status based on step statuses."""
    if not steps:
        return "planned"

    statuses = [s.get("status") for s in steps]

    if "rejected" in statuses:
        return "rejected"
    if "failed" in statuses:
        return "failed"
    if all(s == "completed" for s in statuses):
        return "completed"
    if "executing" in statuses:
        return "executing"
    if "approved" in statuses:
        return "approved"

    return "planned"
