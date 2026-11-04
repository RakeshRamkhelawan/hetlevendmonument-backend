"""
Company Layer Database Models

SQLAlchemy models for the Paperclip AI Symbiotic Integration.
All models include strict tenant isolation via tenant_id columns.

Models:
- Company: Root entity for organizational data
- Department: Hierarchical organizational units
- Goal: Mission/strategic/project/task hierarchy
- ExternalAgent: Non-platform agents with heartbeat protocol
- BoardDecision: Governance approval queue
- CompanyTemplate: Reusable company configurations
- PackActivationAuditLog: Audit trail for pack activations (Golden Rule R2)
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database.database import Base

# TYPE_CHECKING imports to avoid circular imports
if TYPE_CHECKING:
    pass


# =============================================================================
# Enums
# =============================================================================


class CompanyType(str, Enum):
    """Company type enumeration."""

    MKB = "mkb"  # Small-Medium Business
    ZZP = "zzp"  # Self-employed/Freelancer
    ENTERPRISE = "enterprise"


class GoalType(str, Enum):
    """Goal type enumeration - hierarchy levels."""

    MISSION = "mission"  # Top-level company mission
    STRATEGIC = "strategic"  # Strategic objectives
    PROJECT = "project"  # Project goals
    TASK = "task"  # Individual tasks


class GoalStatus(str, Enum):
    """Goal status enumeration."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class ExternalAgentStatus(str, Enum):
    """External agent lifecycle status."""

    REGISTERED = "registered"
    ACTIVE = "active"
    BUSY = "busy"
    STALE = "stale"  # Missed heartbeats
    DEAD = "dead"  # Too many missed heartbeats


class BoardDecisionStatus(str, Enum):
    """Board decision status."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ESCALATED = "escalated"


# =============================================================================
# Company Model
# =============================================================================


class Company(Base):  # type: ignore[misc]
    """
    Root entity for organizational data.

    A Company represents the top-level organizational unit in the Company Layer.
    It contains departments, goals, and configuration for the entire organization.
    """

    __tablename__ = "companies"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Tenant isolation
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    # Core fields
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    company_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default=CompanyType.MKB.value
    )
    sector: Mapped[str] = mapped_column(String(100), nullable=False)
    mission: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Configuration
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=lambda: dict())  # TODO(TYPE): replace Any with concrete type
    board_role_config: Mapped[dict[str, Any] | None] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        JSONB, nullable=True, comment="Board role routing configuration (JSONB)"
    )

    # Template reference
    template_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("company_templates.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        default="active",
        nullable=False,
    )

    # Timestamps
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

    # Relationships
    departments: Mapped[list[Department]] = relationship(
        "Department",
        back_populates="company",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    goals: Mapped[list[Goal]] = relationship(
        "Goal",
        back_populates="company",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    external_agents: Mapped[list[ExternalAgent]] = relationship(
        "ExternalAgent",
        back_populates="company",
        lazy="selectin",
    )
    board_decisions: Mapped[list[BoardDecision]] = relationship(
        "BoardDecision",
        back_populates="company",
        lazy="selectin",
    )

    __table_args__ = (
        # Index for tenant-scoped queries
        Index("idx_companies_tenant", "tenant_id"),
        {"comment": "Companies table - root of organizational hierarchy"},
    )


# =============================================================================
# Department Model
# =============================================================================


class Department(Base):  # type: ignore[misc]
    """
    Hierarchical organizational unit.

    Departments form a tree structure within a company, supporting parent-child
    relationships for organizational charts. Each department can have associated
    domain packs and budget configuration.
    """

    __tablename__ = "departments"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Tenant isolation
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    # Company reference
    company_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    # Core fields
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    # Self-referential parent (for hierarchy)
    parent_department_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Head of department
    head_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Board role for this department
    board_role: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
        comment="Board role associated with this department (e.g., CFO, CTO)",
    )

    # Budget
    budget_monthly_tokens: Mapped[int | None] = mapped_column(
        Integer, nullable=True, comment="Monthly token budget for this department"
    )

    # Domain packs activated for this department
    domain_pack_ids: Mapped[list[str]] = mapped_column(
        JSONB, default=lambda: list(), comment="List of activated domain pack IDs"
    )

    # Configuration
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=lambda: dict())  # TODO(TYPE): replace Any with concrete type

    # Optimistic locking version
    version: Mapped[int] = mapped_column(
        Integer, default=1, nullable=False, comment="Optimistic locking version number"
    )

    # Timestamps
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

    # Relationships
    company: Mapped[Company] = relationship(
        "Company",
        back_populates="departments",
        lazy="selectin",
    )
    parent: Mapped[Department | None] = relationship(
        "Department",
        remote_side="Department.id",
        back_populates="children",
        lazy="selectin",
    )
    children: Mapped[list[Department]] = relationship(
        "Department",
        back_populates="parent",
        lazy="selectin",
    )
    goals: Mapped[list[Goal]] = relationship(
        "Goal",
        back_populates="department",
        lazy="selectin",
    )
    external_agents: Mapped[list[ExternalAgent]] = relationship(
        "ExternalAgent",
        back_populates="department",
        lazy="selectin",
    )

    __table_args__ = (
        Index("idx_departments_tenant", "tenant_id"),
        Index("idx_departments_company", "company_id"),
        Index("idx_departments_parent", "parent_department_id"),
    )


# =============================================================================
# Goal Model
# =============================================================================


class Goal(Base):  # type: ignore[misc]
    """
    Goal hierarchy model (Mission -> Strategic -> Project -> Task).

    Goals form a tree structure representing the organization's objectives.
    Each goal can have KPIs, progress tracking, and deadlines.
    """

    __tablename__ = "goals"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Tenant isolation
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    # Company reference
    company_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    # Self-referential parent (for hierarchy)
    parent_goal_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("goals.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    # Department reference (optional - goals can be cross-department)
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Goal type and content
    goal_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="mission, strategic, project, or task"
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # KPIs and metrics
    kpis: Mapped[dict[str, Any]] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        JSONB, default=lambda: dict(), comment="Key Performance Indicators as JSONB"
    )

    # Status and progress
    status: Mapped[str] = mapped_column(
        String(20),
        default=GoalStatus.NOT_STARTED.value,
        nullable=False,
    )
    progress_pct: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False, comment="Progress percentage (0-100)"
    )

    # Timeline
    deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Timestamps
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

    # Relationships
    company: Mapped[Company] = relationship(
        "Company",
        back_populates="goals",
        lazy="selectin",
    )
    department: Mapped[Department | None] = relationship(
        "Department",
        back_populates="goals",
        lazy="selectin",
    )
    parent: Mapped[Goal | None] = relationship(
        "Goal",
        remote_side="Goal.id",
        back_populates="children",
        lazy="selectin",
    )
    children: Mapped[list[Goal]] = relationship(
        "Goal",
        back_populates="parent",
        lazy="selectin",
    )
    board_decisions: Mapped[list[BoardDecision]] = relationship(
        "BoardDecision",
        back_populates="goal",
        lazy="selectin",
    )

    __table_args__ = (
        Index("idx_goals_tenant", "tenant_id"),
        Index("idx_goals_company", "company_id"),
        Index("idx_goals_parent", "parent_goal_id"),
        Index("idx_goals_department", "department_id"),
    )


# =============================================================================
# External Agent Model
# =============================================================================


class ExternalAgent(Base):  # type: ignore[misc]
    """
    External (non-platform) agent for heartbeat protocol.

    External agents are AI agents running outside the SanskritiSetu platform
    that can register, send heartbeats, and receive tasks via the API.
    """

    __tablename__ = "external_agents"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Tenant isolation
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    # Optional company/department assignment
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    department_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Core fields
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    runtime: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="Runtime type (python, node, docker, etc.)"
    )

    # Capabilities
    capabilities: Mapped[list[str]] = mapped_column(
        JSONB, default=lambda: list(), comment="List of agent capabilities"
    )

    # Webhook for task dispatch
    webhook_url: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
    )

    # API key hash (key itself is shown only once at registration)
    api_key_hash: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="Bcrypt hash of API key"
    )

    # Heartbeat configuration
    heartbeat_interval_seconds: Mapped[int] = mapped_column(
        Integer,
        default=30,
        nullable=False,
    )

    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        default=ExternalAgentStatus.REGISTERED.value,
        nullable=False,
    )

    # Metrics
    metrics: Mapped[dict[str, Any]] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        JSONB,
        default=lambda: dict(),
        comment="Agent metrics (tasks completed, avg duration, etc.)",
    )

    # Configuration
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=lambda: dict())  # TODO(TYPE): replace Any with concrete type

    # Timestamps
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

    # Relationships
    company: Mapped[Company | None] = relationship(
        "Company",
        back_populates="external_agents",
        lazy="selectin",
    )
    department: Mapped[Department | None] = relationship(
        "Department",
        back_populates="external_agents",
        lazy="selectin",
    )

    __table_args__ = (
        Index("idx_external_agents_tenant", "tenant_id"),
        Index("idx_external_agents_tenant_status", "tenant_id", "status"),
        Index("idx_external_agents_company", "company_id"),
    )


# =============================================================================
# Board Decision Model
# =============================================================================


class BoardDecision(Base):  # type: ignore[misc]
    """
    Board governance approval queue.

    Board decisions track actions that require approval from board members
    based on risk level and action type. Integrates with PolicyEngine.
    """

    __tablename__ = "board_decisions"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Tenant isolation
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    # Company reference
    company_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    # Requester
    requested_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Board role assigned to decide
    board_role: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="Board role required to decide (CFO, CTO, CEO, etc.)",
    )

    # Action details
    action_type: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="Type of action requiring approval"
    )
    action_context: Mapped[dict[str, Any]] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        JSONB, default=lambda: dict(), comment="Context for the action (Golden Rule R3)"
    )

    # Goal reference (Golden Rule R3)
    goal_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("goals.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Decision
    decision: Mapped[str | None] = mapped_column(
        String(20), nullable=True, comment="pending, approved, rejected, escalated"
    )

    # Decision metadata
    decided_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Timestamps
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

    # Relationships
    company: Mapped[Company] = relationship(
        "Company",
        back_populates="board_decisions",
        lazy="selectin",
    )
    goal: Mapped[Goal | None] = relationship(
        "Goal",
        back_populates="board_decisions",
        lazy="selectin",
    )

    __table_args__ = (
        Index("idx_board_decisions_tenant", "tenant_id"),
        Index("idx_board_decisions_company", "company_id"),
        Index("idx_board_decisions_queue", "tenant_id", "company_id", "decision"),
        Index("idx_board_decisions_goal", "goal_id"),
    )


# =============================================================================
# Company Template Model
# =============================================================================


class CompanyTemplate(Base):  # type: ignore[misc]
    """
    Reusable company configuration template.

    Templates allow companies to be created from pre-configured setups,
    including departments, goals, and pack activations.
    """

    __tablename__ = "company_templates"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Template metadata
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    company_type: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="mkb, zzp, or enterprise"
    )
    sector: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Template definition
    template_definition: Mapped[dict[str, Any]] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        JSONB,
        default=lambda: dict(),
        comment="Complete template definition (departments, goals, packs)",
    )

    # Ownership
    is_platform_template: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="True for built-in platform templates",
    )

    contributed_by_tenant_id: Mapped[int | None] = mapped_column(
        ForeignKey("tenants.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Usage statistics
    usage_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    rating_sum: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )
    rating_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    # Status
    status: Mapped[str] = mapped_column(
        String(20),
        default="active",
        nullable=False,
    )

    # Timestamps
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

    # Relationships
    # Note: contributor relationship to Tenant defined via explicit queries
    # to avoid circular imports with rbac_models

    __table_args__ = (
        Index("idx_company_templates_contributor", "contributed_by_tenant_id"),
        Index("idx_company_templates_type_sector", "company_type", "sector"),
    )

    @property
    def rating_avg(self) -> float | None:
        """Calculate average rating."""
        if self.rating_count == 0:
            return None
        return self.rating_sum / self.rating_count


# =============================================================================
# Pack Activation Audit Log Model
# =============================================================================


class PackActivationAuditLog(Base):  # type: ignore[misc]
    """
    Audit log for pack activations (Golden Rule R2).

    Every pack activation (automatic or manual) generates an audit log entry
    with scoring details and match reasons for explainability.
    """

    __tablename__ = "pack_activation_audit_logs"

    # Primary key
    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    # Tenant and company
    tenant_id: Mapped[int] = mapped_column(
        ForeignKey("tenants.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    # Department that triggered the activation
    department_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("departments.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    # Pack details
    pack_id: Mapped[str] = mapped_column(
        String(100),
        index=True,
        nullable=False,
    )
    pack_name: Mapped[str] = mapped_column(String(200), nullable=False)

    # Scoring
    score: Mapped[float] = mapped_column(Float, nullable=False)
    confidence: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="EXACT, HIGH, MEDIUM, LOW, or NONE"
    )
    match_reason: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Human-readable explanation of the match"
    )

    # Detailed breakdown
    input_signals: Mapped[dict[str, Any]] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        JSONB, default=lambda: dict(), comment="Input signals used for scoring"
    )
    score_breakdown: Mapped[dict[str, Any]] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        JSONB, default=lambda: dict(), comment="Detailed score breakdown by signal type"
    )

    # Activation details
    activated_automatically: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    # User confirmation (if manual)
    user_confirmed: Mapped[bool | None] = mapped_column(
        Boolean,
        nullable=True,
    )
    confirmed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    # Relationships
    # Note: company and department relationships defined via explicit queries
    # to avoid circular imports

    __table_args__ = (
        # Tenant isolation queries
        Index("idx_audit_tenant_company", "tenant_id", "company_id"),
        # Pack lookup queries
        Index("idx_audit_pack", "pack_id"),
        # Time-based queries (recent activations)
        Index("idx_audit_created", "created_at", postgresql_using="btree"),
        # Department lookup
        Index("idx_audit_department", "department_id"),
        # Confidence-based queries
        Index("idx_audit_confidence", "confidence"),
        # Auto-activation queries
        Index("idx_audit_auto_activated", "activated_automatically", "created_at"),
    )
