"""
Pydantic schemas for Notification CRUD endpoints.
"""

from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class NotificationResponse(BaseModel):
    """Schema for a single notification."""

    id: int
    tenant_id: int
    user_id: int
    type: str
    title: str
    body: str | None = None
    data: dict[str, Any] | None = None  # TODO(TYPE): replace with concrete type  # TODO(TYPE): replace Any with concrete type
    channel: str
    is_read: bool
    read_at: datetime | None = None
    created_at: datetime

    class Config:
        from_attributes = True


class NotificationListResponse(BaseModel):
    """Schema for a paginated list of notifications."""

    success: bool
    data: list[NotificationResponse]
    total: int
    limit: int
    offset: int
