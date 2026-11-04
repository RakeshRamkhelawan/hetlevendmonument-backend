from typing import Any, Optional

"""
VIBE_BE_003: Workflow Database Models

SQLAlchemy models for VIBE workflow persistence:
- WorkflowTemplate: Saved workflow definitions
- WorkflowInstance: Instances of a template
- WorkflowExecution: Execution history and state

Multi-tenant via tenant_id foreign key.
"""

from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from src.core.database.database import Base

# ============================================================================
# Enums
# ============================================================================


class WorkflowStatus(str, PyEnum):
    """Status of a workflow template."""

    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


class ExecutionStatus(str, PyEnum):
    """Status of a workflow execution."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class NodeExecutionStatus(str, PyEnum):
    """Status of a single node execution."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


# ============================================================================
# Workflow Template Model
# ============================================================================


class WorkflowTemplate(Base):  # type: ignore[misc]
    """
    Saved workflow definition template.

    Contains the node/edge structure that can be instantiated and executed.
    Multi-tenant isolated via tenant_id.
    """

    __tablename__ = "workflow_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Multi-tenant isolation
    tenant_id = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Template metadata
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status = mapped_column(
        Enum(WorkflowStatus), default=WorkflowStatus.DRAFT, nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Workflow definition (JSON structure)
    nodes: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)  # TODO(TYPE): replace Any with concrete type
    edges: Mapped[Any] = mapped_column(JSON, nullable=False, default=list)  # TODO(TYPE): replace Any with concrete type
    metadata_ = mapped_column("metadata", JSON, default=dict)

    # Generation context
    original_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    complexity: Mapped[str | None] = mapped_column(String(20), nullable=True)
    generation_model: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Ownership
    created_by = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Statistics
    execution_count: Mapped[int | None] = mapped_column(Integer, default=0)
    last_executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Timestamps
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now()
    )

    # Relationships
    instances = relationship(
        "WorkflowInstance", back_populates="template", cascade="all, delete-orphan"
    )

    # Indexes
    __table_args__ = (
        Index("idx_workflow_template_tenant_name", "tenant_id", "name"),
        Index("idx_workflow_template_tenant_status", "tenant_id", "status"),
        Index("idx_workflow_template_created_by", "created_by"),
    )

    def __repr__(self) -> str:
        return f"<WorkflowTemplate(id={self.id}, name='{self.name}', status={self.status})>"


# ============================================================================
# Workflow Instance Model
# ============================================================================


class WorkflowInstance(Base):  # type: ignore[misc]
    """
    Instance of a workflow template.

    Represents a specific configuration of a template ready for execution.
    """

    __tablename__ = "workflow_instances"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Multi-tenant isolation
    tenant_id = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Template reference
    template_id = mapped_column(
        Integer,
        ForeignKey("workflow_templates.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    template_version: Mapped[int] = mapped_column(Integer, nullable=False)

    # Instance metadata
    name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Configuration overrides (JSON)
    config: Mapped[Any | None] = mapped_column(JSON, default=dict)  # TODO(TYPE): replace Any with concrete type
    input_data: Mapped[Any | None] = mapped_column(JSON, default=dict)  # TODO(TYPE): replace Any with concrete type

    # Schedule (optional)
    schedule_cron: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_scheduled: Mapped[bool | None] = mapped_column(Boolean, default=False)
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # State
    is_active: Mapped[bool | None] = mapped_column(Boolean, default=True)

    # Ownership
    created_by = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    # Timestamps
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now()
    )

    # Relationships
    template = relationship("WorkflowTemplate", back_populates="instances")
    executions = relationship(
        "WorkflowExecution", back_populates="instance", cascade="all, delete-orphan"
    )

    # Indexes
    __table_args__ = (
        Index("idx_workflow_instance_tenant", "tenant_id"),
        Index("idx_workflow_instance_template", "template_id"),
        Index("idx_workflow_instance_scheduled", "is_scheduled", "next_run_at"),
    )

    def __repr__(self) -> str:
        return f"<WorkflowInstance(id={self.id}, template_id={self.template_id})>"


# ============================================================================
# Workflow Execution Model
# ============================================================================


class WorkflowExecution(Base):  # type: ignore[misc]
    """
    Record of a workflow execution.

    Tracks the state machine: PENDING -> RUNNING -> SUCCEEDED/FAILED.
    """

    __tablename__ = "workflow_executions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)

    # Multi-tenant isolation
    tenant_id = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Instance reference
    instance_id = mapped_column(
        Integer,
        ForeignKey("workflow_instances.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Execution tracking
    execution_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    status = mapped_column(
        Enum(ExecutionStatus),
        default=ExecutionStatus.PENDING,
        nullable=False,
        index=True,
    )

    # Trigger info
    trigger_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # manual, scheduled, webhook
    triggered_by = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    # Input/Output data
    input_data: Mapped[Any | None] = mapped_column(JSON, default=dict)  # TODO(TYPE): replace Any with concrete type
    output_data: Mapped[Any | None] = mapped_column(JSON, default=dict)  # TODO(TYPE): replace Any with concrete type

    # Node execution state (JSON: {node_id: {status, output, error}})
    node_states: Mapped[Any | None] = mapped_column(JSON, default=dict)  # TODO(TYPE): replace Any with concrete type
    current_node: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Progress
    nodes_completed: Mapped[int | None] = mapped_column(Integer, default=0)
    nodes_total: Mapped[int | None] = mapped_column(Integer, default=0)
    progress_percent: Mapped[float | None] = mapped_column(Float, default=0.0)

    # Timing
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Error tracking
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_node_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_details: Mapped[Any | None] = mapped_column(JSON, nullable=True)  # TODO(TYPE): replace Any with concrete type

    # Retry info
    retry_count: Mapped[int | None] = mapped_column(Integer, default=0)
    max_retries: Mapped[int | None] = mapped_column(Integer, default=3)

    # Timestamps
    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now()
    )

    # Relationships
    instance = relationship("WorkflowInstance", back_populates="executions")

    # Indexes
    __table_args__ = (
        Index("idx_workflow_execution_tenant_status", "tenant_id", "status"),
        Index("idx_workflow_execution_instance", "instance_id"),
        Index("idx_workflow_execution_created", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<WorkflowExecution(id={self.id}, execution_id='{self.execution_id}', status={self.status})>"

    @property
    def is_terminal(self) -> bool:
        """Check if execution is in a terminal state."""
        return self.status in (
            ExecutionStatus.SUCCEEDED,
            ExecutionStatus.FAILED,
            ExecutionStatus.CANCELLED,
        )
