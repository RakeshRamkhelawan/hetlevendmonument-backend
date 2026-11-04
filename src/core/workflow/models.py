"""
Production-Ready Workflow Database Models
PostgreSQL-optimized schema for C.7 Workflow Real Engine

Design Goals:
- Support DAG execution with dependency tracking
- Enable idempotent task execution (execution_id + task_ref uniqueness)
- Provide audit trail via execution_events
- Multi-tenant isolation via tenant_id
- Support workflow versioning (immutable specs)
"""

import enum
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import JSON, Boolean, DateTime
from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey, Index, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship, synonym
from sqlalchemy.sql import func

from src.core.database.database import Base

# ============================================================================
# ENUMS
# ============================================================================


class WorkflowStatus(str, enum.Enum):
    """Workflow execution status"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class TaskStatus(str, enum.Enum):
    """Task execution status"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRYING = "retrying"
    TIMEOUT = "timeout"
    SKIPPED = "skipped"


class EventType(str, enum.Enum):
    """Workflow event types for audit trail"""

    WORKFLOW_CREATED = "workflow_created"
    WORKFLOW_STARTED = "workflow_started"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_FAILED = "workflow_failed"
    WORKFLOW_CANCELLED = "workflow_cancelled"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_RETRYING = "task_retrying"
    TASK_TIMEOUT = "task_timeout"
    STATUS_CHANGED = "status_changed"


# ============================================================================
# MODELS
# ============================================================================


def _tekstenum(enum_klasse: type[enum.Enum]) -> SQLEnum:
    """Een enumkolom zoals de MIGRATIE hem maakt: gewone tekst (`VARCHAR(50)`) met de WAARDEN (`pending`).

    De migratie (`20260522b_stale_task_index.py`) maakt `status` en `event_type` als `String(50)` met `'pending'`
    als standaard. Een gewone `SQLEnum(Klasse, name=...)` stuurt de enum-NAMEN (`PENDING`) en bindt ze als het
    PostgreSQL-enumtype, dat alleen kleine letters kent: elke INSERT faalde met `invalid input value for enum
    workflow_status_enum: "PENDING"`. Gemeten 2026-10-22 op een database uit de migratieketen: de API kon geen
    enkele workflowuitvoering aanmaken. `native_enum=False` bindt als tekst, `values_callable` kiest de waarden.
    """
    return SQLEnum(
        enum_klasse,
        native_enum=False,
        length=50,
        values_callable=lambda leden: [lid.value for lid in leden],
    )


class C7Workflow(Base):  # type: ignore[misc]
    """
    Workflow definition (immutable per version)

    Design:
    - Immutable: spec_json never changes once version created
    - Versioning: id (String PK acts as workflow_id) + version for tracking
    - Activation: Only one version can be is_active=True at a time

    NOTE: Schema aligned with 0001_baseline migration (id=String(50) PK)
    DB PK is on 'id' only. Version is a tracking field, not part of PK.
    """

    __tablename__ = "c7_workflows"

    # Primary key matches migration (String, not Integer)
    id: Mapped[str] = mapped_column(String(50), primary_key=True, comment="Workflow ID (UUID/slug)")

    # Backwards compatibility aliases
    workflow_id = synonym("id")

    # Version is tracking only - NOT part of PK (DB has PK on 'id' alone)
    version = mapped_column(
        Integer,
        nullable=True,
        default=1,
        comment="Workflow version (incremental)",
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Additional fields from migration
    workflow_type: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="Workflow category/type"
    )
    trigger_type = mapped_column(String(50), nullable=False, comment="How workflow is triggered")
    trigger_config: Mapped[Any | None] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        JSON, default=dict, comment="Trigger configuration"
    )

    # DAG specification (immutable) - migration calls this 'nodes' + 'edges'
    # Keep spec_json for backwards compat but map from nodes/edges if needed
    nodes: Mapped[Any] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        JSON, nullable=False, default=list, comment="Workflow DAG nodes"
    )
    edges: Mapped[Any] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        JSON, nullable=False, default=list, comment="Workflow DAG edges"
    )
    variables: Mapped[Any | None] = mapped_column(JSON, default=dict, comment="Workflow variables")  # TODO(TYPE): replace Any with concrete type

    # Property for backwards compatibility with code expecting spec_json
    @property
    def spec_json(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Backwards compat: combine nodes + edges into spec format"""
        return {
            "tasks": self.nodes or [],
            "dependencies": self.edges or [],
            "variables": self.variables or {},
        }

    @spec_json.setter
    def spec_json(self, value: object) -> None:
        """Backwards compat: split spec into nodes + edges"""
        if isinstance(value, dict):
            self.nodes = value.get("nodes", value.get("tasks", []))
            self.edges = value.get("edges", value.get("dependencies", []))
            self.variables = value.get("variables", {})
        elif isinstance(value, list):
            # If a list is passed, assume they are nodes
            self.nodes = value
            self.edges = []
            self.variables = {}

    # Ownership & tenancy (from migration schema)
    created_by: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="User ID who created workflow"
    )
    owner_id = synonym("created_by")

    tenant_id = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Multi-tenant isolation - FK to tenants.id",
    )

    # Versioning control
    is_active = mapped_column(Boolean, default=True, nullable=False, comment="Is workflow active")

    # Timestamps
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )

    # Relationships
    executions = relationship(
        "C7WorkflowExecution", back_populates="workflow", cascade="all, delete-orphan"
    )

    # Constraints & Indexes (align with migration - uses 'id' not 'workflow_id')
    __table_args__ = (
        Index("idx_c7_workflow_active", "is_active"),
        Index("idx_c7_workflow_tenant", "tenant_id", "created_at"),
    )


class C7WorkflowExecution(Base):  # type: ignore[misc]
    """
    Workflow execution tracking (one per workflow run)

    Design:
    - Tracks execution state and progress
    - Links to tasks via execution_tasks
    - Stores final results after completion
    """

    __tablename__ = "c7_workflow_executions"

    id: Mapped[str] = mapped_column(String(50), primary_key=True, index=True)
    execution_id = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
        comment="UUID for idempotency",
    )
    workflow_id = mapped_column(
        String(50),
        ForeignKey("c7_workflows.id", ondelete="CASCADE"),
        nullable=False,
    )
    workflow_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    # Execution state
    status = mapped_column(
        _tekstenum(WorkflowStatus),
        nullable=False,
        default=WorkflowStatus.PENDING,
        index=True,
    )

    # Triggering context
    # SECURITY FIX (P5.1.4): Changed from String(100) to Integer FK for proper RLS
    tenant_id = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        comment="Multi-tenant isolation - FK to tenants.id",
    )
    initiated_by = mapped_column(String(100), nullable=True, comment="User ID or system identifier")
    correlation_id = mapped_column(
        String(100), nullable=True, index=True, comment="External request tracking"
    )

    # Timing
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    timeout_at = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Calculated deadline for timeout",
    )

    # Progress tracking
    tasks_total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tasks_completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    tasks_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Input & Output (set on execution)
    input_json = mapped_column(JSON, nullable=True, comment="Workflow input parameters and context")
    output_json = mapped_column(
        JSON, nullable=True, comment="Workflow execution output and results"
    )

    # Final results (set on completion)
    results_json = mapped_column(
        JSON, nullable=True, comment="Final workflow outputs and task results"
    )
    error_message = mapped_column(Text, nullable=True, comment="Error description if status=FAILED")

    # Timestamps
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    workflow = relationship("C7Workflow", back_populates="executions")
    tasks = relationship(
        "C7ExecutionTask", back_populates="execution", cascade="all, delete-orphan"
    )
    events = relationship(
        "C7ExecutionEvent", back_populates="execution", cascade="all, delete-orphan"
    )

    # Indexes
    __table_args__ = (
        Index("idx_c7_execution_status_time", "status", "created_at"),
        Index("idx_c7_execution_tenant_time", "tenant_id", "created_at"),
        Index("idx_c7_execution_correlation", "correlation_id"),
    )


class C7ExecutionTask(Base):  # type: ignore[misc]
    """
    Individual task execution within a workflow

    Design:
    - Idempotency: (execution_id, task_ref) uniqueness prevents duplicate execution
    - Result storage: Large blobs offloaded to object storage (reference in result_json)
    - Retry tracking: retries counter for exponential backoff

    NEO AUDIT FIX (P0): Added tenant_id for multi-tenant isolation.
    Without this, direct queries on task tables bypass execution->workflow->tenant chain.
    """

    __tablename__ = "c7_execution_tasks"

    id: Mapped[str] = mapped_column(String(50), primary_key=True, index=True)
    execution_id = mapped_column(
        String(50),
        ForeignKey("c7_workflow_executions.id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_id = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Task identification (from workflow spec)
    task_ref = mapped_column(
        String(100),
        nullable=False,
        comment="Task reference from workflow spec (e.g., 'task_1')",
    )
    task_type = mapped_column(String(100), nullable=False, comment="Agent type or task category")

    # Execution state
    status = mapped_column(
        _tekstenum(TaskStatus),
        nullable=False,
        default=TaskStatus.PENDING,
        index=True,
    )

    # Worker assignment
    worker_id = mapped_column(
        String(100),
        nullable=True,
        comment="Worker hostname/container ID that executed task",
    )

    # Timing
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Results
    result_json = mapped_column(
        JSON,
        nullable=True,
        comment="Task output. Large blobs -> S3 reference: {storage: 's3', key: '...'}",
    )
    error_json = mapped_column(
        JSON,
        nullable=True,
        comment="Error details: {type, message, stack_trace, retry_after}",
    )

    # Retry tracking
    retries = mapped_column(Integer, nullable=False, default=0, comment="Number of retry attempts")
    max_retries = mapped_column(
        Integer, nullable=False, default=3, comment="Maximum retries allowed"
    )

    # Timestamps
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    execution = relationship("C7WorkflowExecution", back_populates="tasks")

    # Constraints & Indexes
    __table_args__ = (
        UniqueConstraint("execution_id", "task_ref", name="uq_c7_execution_task"),
        Index("idx_c7_task_execution_status", "execution_id", "status"),
        Index("idx_c7_task_tenant_id", "tenant_id"),
        Index("idx_c7_task_worker", "worker_id"),
    )


class C7ExecutionEvent(Base):  # type: ignore[misc]
    """
    Append-only audit log for workflow/task events

    Design:
    - Immutable audit trail (no updates, only inserts)
    - Captures state transitions and errors
    - Enables forensic analysis and debugging

    NEO AUDIT FIX (P0): Added tenant_id for multi-tenant isolation.
    Without this, event audit logs leak across tenants.
    """

    __tablename__ = "c7_execution_events"

    id: Mapped[str] = mapped_column(String(50), primary_key=True, index=True)
    execution_id = mapped_column(
        String(50),
        ForeignKey("c7_workflow_executions.id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_id = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Event classification
    event_type = mapped_column(
        _tekstenum(EventType), nullable=False, index=True
    )

    # Event context
    task_ref = mapped_column(
        String(100), nullable=True, comment="Related task reference if task event"
    )
    payload_json = mapped_column(
        JSON,
        nullable=False,
        server_default="{}",
        comment="Event data: state changes, error details, metrics",
    )

    # Timestamp (immutable)
    created_at = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    # Relationships
    execution = relationship("C7WorkflowExecution", back_populates="events")

    # Indexes
    __table_args__ = (
        Index("idx_c7_event_execution_time", "execution_id", "created_at"),
        Index("idx_c7_event_tenant_id", "tenant_id"),
        Index("idx_c7_event_type_time", "event_type", "created_at"),
    )


class C7WorkflowTemplate(Base):  # type: ignore[misc]
    """
    Reusable workflow templates (optional - can be added later)

    Future enhancement for workflow marketplace/library
    """

    __tablename__ = "c7_workflow_templates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    template_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    # Template spec (can be instantiated into Workflow)
    spec_json: Mapped[Any] = mapped_column(JSON, nullable=False)  # TODO(TYPE): replace Any with concrete type

    # Metadata
    author: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    usage_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Timestamps
    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )

    __table_args__ = (Index("idx_c7_template_category", "category", "usage_count"),)


class C7WorkflowSnapshot(Base):  # type: ignore[misc]
    """
    Workflow binary snapshot for Yjs persistence

    Design:
    - Stores binary Yjs state (BYTEA)
    - Linked to C7Workflow
    - Multi-tenant
    """

    __tablename__ = "c7_workflow_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # FIX: Removed ForeignKey because c7_workflows has Composite PK (id, version)
    # TODO: Refactor to use Composite FK (workflow_id, version) or separate WorkflowDefinition table
    workflow_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # Binary State
    content: Mapped[bytes] = mapped_column(
        LargeBinary, nullable=False, comment="Yjs binary state blob"
    )

    # Metadata
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Multi-tenancy
    tenant_id = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    created_by: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # Relationships
    # Use primaryjoin to handle relationship to C7Workflow which has composite PK
    workflow = relationship(
        "C7Workflow",
        primaryjoin="foreign(C7WorkflowSnapshot.workflow_id) == C7Workflow.id",
        backref="snapshots",
        viewonly=True,  # Viewonly because we aren't strictly enforcing the composite FK here
    )

    __table_args__ = (Index("idx_c7_snapshot_workflow_time", "workflow_id", "created_at"),)


# ============================================================================
# ALIASES FOR BACKWARD COMPATIBILITY
# ============================================================================

Workflow = C7Workflow
WorkflowExecution = C7WorkflowExecution
ExecutionTask = C7ExecutionTask
ExecutionEvent = C7ExecutionEvent
WorkflowTemplate = C7WorkflowTemplate
WorkflowSnapshot = C7WorkflowSnapshot
