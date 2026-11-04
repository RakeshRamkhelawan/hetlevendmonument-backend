"""
Pydantic models for Agent Council policies.

Allows per-tenant configuration of officer behaviors and aggregation rules.
See ADR-027 and docs/copilot-architecture.md.
"""

from __future__ import annotations


from pydantic import BaseModel, Field


class OfficerPolicy(BaseModel):
    """Configuration for a single Council Officer."""

    can_veto: bool = True
    timeout_ms: int = Field(default=500, ge=50, le=5000)
    strictness: float = Field(default=0.5, ge=0.0, le=1.0)


class CouncilPolicy(BaseModel):
    """Configuration for the entire Agent Council deliberation."""

    # Keyed by officer name (e.g., "ComplianceOfficer")
    officers: dict[str, OfficerPolicy] = Field(default_factory=dict)
    
    # Default aggregation mode from ADR-027
    aggregation_mode: str = "strict-highest-bar"
    
    # Threshold for automatic HITL requirement (if confidence is low)
    hitl_threshold: float = Field(default=0.3, ge=0.0, le=1.0)

    class Config:
        frozen = True
