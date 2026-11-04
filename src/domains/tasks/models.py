"""Agentic task domain models.

Provides a generic, tenant-isolated `Task` entity for the agentic copilot
 task-management layer. This model is intentionally separate from the
workflow-specific `C7ExecutionTask` table.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON as JSONType,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database.database import Base

if TYPE_CHECKING:
    pass


class TaskStatus(StrEnum):
    """Lifecycle states for an agentic task."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskPriority(StrEnum):
    """Priority levels for an agentic task."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Task(Base):  # type: ignore[misc]
    """Tenant-isolated task for agentic execution."""

    __tablename__ = "agentic_tasks"

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        nullable=False,
        default=uuid4,
    )
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        server_default=TaskStatus.PENDING.value,
    )
    priority: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default=TaskPriority.MEDIUM.value,
    )
    created_by: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    assigned_agent_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    payload: Mapped[dict[str, Any] | None] = (  # TODO(TYPE): replace Any with concrete type
        mapped_column(
            JSONType,
            nullable=True,
        )
    )
    result: Mapped[dict[str, Any] | None] = (  # TODO(TYPE): replace Any with concrete type
        mapped_column(
            JSONType,
            nullable=True,
        )
    )
    parent_task_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("agentic_tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    external_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_agentic_tasks_tenant_status", "tenant_id", "status"),
        Index("ix_agentic_tasks_tenant_assigned", "tenant_id", "assigned_agent_id"),
        Index("ix_agentic_tasks_external_ref", "external_ref"),
        {"extend_existing": True},
    )

    def __repr__(self) -> str:
        return (
            f"<Task(id={self.id}, tenant_id={self.tenant_id}, "
            f"title={self.title}, status={self.status})>"
        )
