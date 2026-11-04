from datetime import datetime
from typing import Any

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


class GDPRDeletionReport(BaseModel):
    """Report returned after learning-data deletion."""

    tenant_id: int
    user_id: str
    deleted_counts: dict[str, int]
    total_deleted: int
    audit_logged: bool = True
    executed_at: datetime


class UserDataExport(BaseModel):
    """Serializable export of learning data tied to a user."""

    tenant_id: int
    user_id: str
    exported_at: datetime
    total_records: int
    data: dict[str, list[dict[str, Any]]]  # TODO(TYPE): replace Any with concrete type


class GDPRRetentionReport(BaseModel):
    """Report returned after retention cleanup."""

    tenant_id: int | None
    max_age_days: int
    deleted_counts: dict[str, int]
    total_deleted: int
    executed_at: datetime


class LearningStatusReport(BaseModel):
    """Admin dashboard summary for learning governance."""

    tenant_id: int
    learning_enabled: bool
    counts: dict[str, int]
    recent_audit_actions: list[str]


class LearningAuditEntry(BaseModel):
    """Serialized learning audit entry for admin inspection."""

    id: int
    action: str | None
    resource: str | None
    user_id: int | None
    timestamp: datetime
    details: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
