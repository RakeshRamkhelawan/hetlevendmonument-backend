"""
SQLAlchemy models for Phase 3 procedures system
Uses UUID primary keys and PostgreSQL JSONB for flexibility
"""

import sys
from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import JSON, Boolean, DateTime
from sqlalchemy import ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.engine import Dialect
from sqlalchemy.types import TypeDecorator, TypeEngine

_module = sys.modules[__name__]
if __name__ == "core.procedures.models":
    sys.modules.setdefault("src.core.procedures.models", _module)
elif __name__ == "src.core.procedures.models":
    sys.modules.setdefault("core.procedures.models", _module)

from src.core.database.database import Base


# Custom type for ARRAY that works with both PostgreSQL and SQLite
class StringArray(TypeDecorator[list[str]]):
    """Array type that uses ARRAY for PostgreSQL and JSON for other databases"""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[list[str]]:
        from typing import cast as _cast

        if dialect.name == "postgresql":
            return _cast(TypeEngine[list[str]], dialect.type_descriptor(PG_ARRAY(String)))
        return _cast(TypeEngine[list[str]], dialect.type_descriptor(JSON()))


class DomainPack(Base):  # type: ignore[misc]
    """
    Domain Pack Model - represents a collection of related procedures for a specific department/domain
    Example: Finance domain includes invoicing, payment approval, audit procedures
    """

    __tablename__ = "domain_packs"
    __table_args__ = (
        Index("idx_domain_packs_tenant", "tenant_id"),
        Index(
            "idx_domain_packs_tenant_name_version",
            "tenant_id",
            "name",
            "version",
            unique=True,
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4, nullable=False
    )
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    department: Mapped[str] = mapped_column(String(255), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    capabilities: Mapped[list[str]] = mapped_column(StringArray, nullable=False, default=[])
    input_contracts = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default={}
    )
    output_contracts = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default={}
    )
    status = mapped_column(
        String(50), nullable=False, default="active", index=True
    )  # active, deprecated, archived
    created_at = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Health monitoring and usage tracking fields
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    usage_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    health_status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="healthy", index=True
    )  # "healthy", "warning", "critical"
    last_health_check: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ProcedureMetadata(Base):  # type: ignore[misc]
    """
    Procedure Metadata Model - enriches FocusBuilderFlow with Phase 3 metadata
    Links a procedure (flow) to a domain pack and adds intent/capability tags
    """

    __tablename__ = "procedure_metadata"
    __table_args__ = (
        Index("idx_procedure_metadata_domain_pack", "domain_pack_id"),
        Index("idx_procedure_metadata_tenant", "tenant_id"),
        Index("idx_procedure_metadata_flow", "flow_id"),
        Index("idx_procedure_metadata_intent_tags", "intent_tags", postgresql_using="gin"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4, nullable=False
    )
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    flow_id = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, index=True
    )  # FK to focus_builder_flows (but we'll use UUID)
    domain_pack_id = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, index=True
    )  # FK to domain_packs
    category: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    intent_tags: Mapped[list[str]] = mapped_column(
        StringArray, nullable=False, default=[], index=True
    )
    prerequisites: Mapped[list[str]] = mapped_column(StringArray, nullable=False, default=[])
    estimated_duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_platform_template: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    procedure_metadata = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default={}
    )
    created_at = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )


class ProcedureExecution(Base):  # type: ignore[misc]
    """
    Procedure Execution Model - records each execution of a procedure
    Tracks status, input/output, and maintains audit trail
    """

    __tablename__ = "procedure_executions"
    __table_args__ = (
        Index("idx_procedure_executions_tenant", "tenant_id"),
        Index("idx_procedure_executions_procedure", "procedure_id"),
        Index("idx_procedure_executions_status", "status"),
        Index("idx_procedure_executions_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4, nullable=False
    )
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    procedure_id = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, index=True
    )  # FK to procedure_metadata
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="pending_approval", index=True
    )
    # Status values: pending_approval, running, completed, failed, escalation_failed, cancelled
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    audit_trail = mapped_column(
        JSON().with_variant(JSONB, "postgresql"), nullable=False, default=[]
    )
    created_at = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )
    updated_at = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AIQualityEvent(Base):  # type: ignore[misc]
    """
    AI Quality Event Model - records quality issues/metrics from procedure executions
    Used for observability and debugging of AI agent operations

    NEO AUDIT FIX (P0): Added tenant_id for multi-tenant isolation.
    """

    __tablename__ = "aiqualityevents"
    __table_args__ = (
        Index("idx_ai_quality_events_execution", "execution_id"),
        Index("idx_ai_quality_events_tenant_id", "tenant_id"),
        Index("idx_ai_quality_events_type", "event_type"),
        Index("idx_ai_quality_events_severity", "severity"),
        Index("idx_ai_quality_events_created_at", "created_at"),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid4, nullable=False
    )
    execution_id = mapped_column(
        PG_UUID(as_uuid=True), nullable=False, index=True
    )  # FK to procedure_executions
    tenant_id = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_type = mapped_column(
        String(50), nullable=False
    )  # hallucination, low_confidence, policy_violation, timeout
    severity: Mapped[str] = mapped_column(
        String(20), nullable=False
    )  # info, warning, error, critical
    details = mapped_column(JSON().with_variant(JSONB, "postgresql"), nullable=False, default={})
    created_at = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )


# Import PackActivationAuditLog from company.models to avoid duplication
# This model is defined in src/core/company/models.py
from src.core.company.models import PackActivationAuditLog

__all__ = [
    "DomainPack",
    "ProcedureMetadata",
    "ProcedureExecution",
    "AIQualityEvent",
    "PackActivationAuditLog",
    "StringArray",
]
