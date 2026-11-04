"""Pydantic schemas for the Council API (SP-ARCH-ARCH-2 / ARCH-004)."""

from pydantic import BaseModel, Field


class CouncilDecisionResponse(BaseModel):
    """A pending HITL decision surfaced to the compliance dashboard."""

    id: str
    agent_id: str
    risk_level: str  # low | medium | high | critical
    timeout_at: str
    description: str | None = None


class CouncilDecisionListResponse(BaseModel):
    """Response wrapper matching the frontend's useCouncilDecisions contract."""

    decisions: list[CouncilDecisionResponse] = Field(default_factory=list)
