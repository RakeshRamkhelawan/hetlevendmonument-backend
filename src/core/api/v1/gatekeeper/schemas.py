"""Pydantic schemas for Gatekeeper API endpoints."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class DecisionResponse(BaseModel):
    """Response schema for a Gatekeeper decision."""

    decision_id: str
    task_id: str
    decision: str  # allow/block/hitl/defer
    risk_category: str
    risk_level: str
    hitl_required: bool
    hitl_ticket_ref: str | None
    decision_hash: str
    previous_hash: str | None
    timestamp: datetime

    class Config:
        from_attributes = True


class DecisionListResponse(BaseModel):
    """Paginated list of decisions."""

    data: list[DecisionResponse]
    total: int
    limit: int
    offset: int


class HITLApprovalRequest(BaseModel):
    """Request to approve a HITL ticket."""

    ticket_ref: str = Field(..., description="HITL ticket reference", min_length=3)
    approved_by: str = Field(
        ..., description="User approving the request", min_length=3, max_length=100
    )
    notes: str | None = Field(None, description="Optional approval notes", max_length=1000)


class HITLRejectionRequest(BaseModel):
    """Request to reject a HITL ticket."""

    ticket_ref: str = Field(..., description="HITL ticket reference", min_length=3)
    rejected_by: str = Field(
        ..., description="User rejecting the request", min_length=3, max_length=100
    )
    reason: str = Field(..., description="Reason for rejection", min_length=10, max_length=1000)


class HITLResponse(BaseModel):
    """Response after HITL approval/rejection."""

    status: str  # approved/rejected
    ticket_ref: str
    message: str


class GatekeeperStatsResponse(BaseModel):
    """Statistics for Gatekeeper decisions."""

    total_decisions: int
    allowed: int
    blocked: int
    require_hitl: int
    hitl_pending: int
    hitl_approved: int
    hitl_rejected: int
    chain_integrity: bool  # True if chain intact


class ChainVerificationResponse(BaseModel):
    """Response for chain verification endpoint."""

    task_id: str
    chain_valid: bool
    decisions_count: int
    first_decision: str | None
    last_decision: str | None


class ErrorResponse(BaseModel):
    """Standard error response."""

    success: bool = False
    error: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
