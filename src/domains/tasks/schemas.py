"""Pydantic schemas for the agentic task domain."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

TaskStatusLiteral = Literal["pending", "in_progress", "completed", "failed", "cancelled"]
TaskPriorityLiteral = Literal["low", "medium", "high", "critical"]


class TaskCreate(BaseModel):
    """Schema for creating a new agentic task.

    ``tenant_id`` is intentionally absent: the tenant is derived from the
    authenticated request context and injected by the service layer.
    """

    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    status: TaskStatusLiteral | None = "pending"
    priority: TaskPriorityLiteral | None = "medium"
    created_by: int | None = None
    assigned_agent_id: str | None = None
    payload: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    parent_task_id: UUID | None = None
    external_ref: str | None = None
    due_at: datetime | None = None


class TaskUpdate(BaseModel):
    """Schema for updating an existing agentic task.

    ``tenant_id``, ``id`` and ``created_by`` are immutable and are not
    accepted.
    """

    title: str | None = None
    description: str | None = None
    status: TaskStatusLiteral | None = None
    priority: TaskPriorityLiteral | None = None
    assigned_agent_id: str | None = None
    payload: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    result: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    parent_task_id: UUID | None = None
    external_ref: str | None = None
    due_at: datetime | None = None


class TaskRead(BaseModel):
    """Read-only schema for an agentic task."""

    id: UUID
    tenant_id: int
    title: str
    description: str | None
    status: str
    priority: str
    created_by: int | None
    assigned_agent_id: str | None
    payload: dict[str, Any] | None  # TODO(TYPE): replace Any with concrete type
    result: dict[str, Any] | None  # TODO(TYPE): replace Any with concrete type
    parent_task_id: UUID | None
    external_ref: str | None
    due_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
