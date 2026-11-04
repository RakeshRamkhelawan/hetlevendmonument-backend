"""API-layer request schemas for admin learning endpoints.

Lives in core_api layer so admin_learning_endpoints.py does not need to import
from agent_runtime (src.core.learning.gdpr_models) -- ADR-034 boundary.
"""

from pydantic import BaseModel, Field


class GDPRDeleteUserRequest(BaseModel):
    """Request payload for deleting learning data tied to a user."""

    user_id: str = Field(..., min_length=1, max_length=255)
    reason: str | None = Field(default=None, max_length=500)


class GDPRExportUserRequest(BaseModel):
    """Request payload for exporting learning data tied to a user."""

    user_id: str = Field(..., min_length=1, max_length=255)


class GDPRRetentionRequest(BaseModel):
    """Request payload for applying learning-data retention."""

    max_age_days: int = Field(..., ge=1, le=3650)
