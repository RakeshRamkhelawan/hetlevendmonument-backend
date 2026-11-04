"""
Workflow Version Models - Multi-tenant Workflow Versioning
===========================================================

Enables workflow snapshots, history tracking, and rollback.

Models:
- WorkflowVersion: Snapshots of workflow at different points
- WorkflowChangeLog: Track changes between versions
"""

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database.database import Base


class WorkflowVersion(Base):  # type: ignore[misc]
    """
    Snapshot of a workflow at a specific point in time.

    Enables workflow history, comparison, and rollback.
    """

    __tablename__ = "workflow_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id"), nullable=False, index=True
    )
    workflow_id: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # Version metadata
    version_number: Mapped[int] = mapped_column(Integer, nullable=False, index=True)  # 1, 2, 3, ...
    created_by: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )  # User ID
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    # Version content
    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str | None] = mapped_column(String)

    # Workflow spec (nodes + edges)
    workflow_spec: Mapped[Any] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        JSON, nullable=False
    )  # {nodes: [...], edges: [...]}  # TODO(TYPE): replace Any with concrete type

    # Metadata
    change_description: Mapped[str | None] = mapped_column(Text)  # What changed in this version
    is_stable: Mapped[bool | None] = mapped_column(
        Boolean, default=False
    )  # Mark as stable/production-ready
    tags: Mapped[Any | None] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        JSON, default=[]
    )  # ["performance-optimized", "error-handled"]

    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at_utc: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    creator = relationship("User", foreign_keys=[created_by])

    __table_args__ = (
        Index("ix_workflow_versions_tenant_workflow", "tenant_id", "workflow_id"),
        Index("ix_workflow_versions_tenant_created", "tenant_id", "created_at"),
    )


class WorkflowChangeLog(Base):  # type: ignore[misc]
    """
    Track what changed between workflow versions.

    Enables diff views and understanding of improvements.
    """

    __tablename__ = "workflow_change_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id"), nullable=False, index=True
    )

    # Version reference
    from_version_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("workflow_versions.id"), nullable=True
    )
    to_version_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workflow_versions.id"), nullable=False
    )

    # Change details
    change_type = mapped_column(
        String, nullable=False
    )  # 'add_node', 'remove_node', 'update_node', 'add_edge'
    target_id: Mapped[str | None] = mapped_column(String)  # node_id or edge_id that changed

    # What changed
    old_value: Mapped[Any | None] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        JSON
    )  # Previous state  # TODO(TYPE): replace Any with concrete type
    new_value: Mapped[Any | None] = mapped_column(
        JSON
    )  # New state  # TODO(TYPE): replace Any with concrete type
    reason: Mapped[str | None] = mapped_column(Text)  # Why this change was made

    created_at_utc: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    __table_args__ = (
        Index("ix_workflow_change_logs_tenant", "tenant_id"),
        Index("ix_workflow_change_logs_versions", "from_version_id", "to_version_id"),
    )
