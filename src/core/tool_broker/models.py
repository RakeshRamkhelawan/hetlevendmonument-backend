"""
SQLAlchemy ORM models for the Tool Broker.
"""

from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database.database import Base


class HITLTicket(Base):  # type: ignore[misc]
    """Persistent Human-in-the-Loop approval ticket."""

    __tablename__ = "hitl_tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ticket_ref: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    tool_name: Mapped[str] = mapped_column(String(256), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)  # TODO(TYPE): replace Any with concrete type
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"), nullable=True)

    #: Wat de MENS erbij schreef toen hij besloot (ADR-036 OP-69).
    #:
    #: `ToolHITLRejection.reason` is verplicht met `min_length=10` en `ToolHITLApproval.notes` is
    #: optioneel; beide werden gevalideerd en daarna weggegooid, omdat er geen kolom voor was. Op
    #: een endpoint waarvan de hele rechtvaardiging AI Act art. 14 is -- aantoonbaar menselijk
    #: toezicht -- was de motivering van de mens het enige dat NIET werd bewaard.
    #:
    #: Bewust EEN kolom voor beide: het is in beide gevallen "wat de beslisser erover zei", en de
    #: status vertelt al welk besluit het was. Deze tekst is door een MENS geschreven en niet door
    #: een model, dus hij valt buiten de pseudonimisering en overleeft de opruiming.
    resolution_note: Mapped[str | None] = mapped_column(String(1000), nullable=True)


class Tool(Base):  # type: ignore[misc]
    """Tenant-scoped tool registered in the Tool Broker."""

    __tablename__ = "tools"
    __table_args__ = (Index("ix_tools_tenant_deleted", "tenant_id", "deleted_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    tool_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(20), server_default=text("'active'"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, server_default=text("1"), nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp(), nullable=False
    )
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    code: Mapped[str | None] = mapped_column(Text, nullable=True)
    endpoint_url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    parameters: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)  # TODO(TYPE): replace Any with concrete type
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)  # TODO(TYPE): replace Any with concrete type
    tags: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    timeout_seconds: Mapped[int] = mapped_column(Integer, server_default=text("30"), nullable=False)
    retry_policy: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)  # TODO(TYPE): replace Any with concrete type
    usage_count: Mapped[int] = mapped_column(Integer, server_default=text("0"), nullable=False)
    created_by: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )


class ToolVersion(Base):  # type: ignore[misc]
    """Immutable snapshot of a Tool at a specific version."""

    __tablename__ = "tool_versions"
    __table_args__ = (
        UniqueConstraint("tool_id", "version", name="uq_tool_versions_tool_id_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tool_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tools.id", ondelete="CASCADE"), nullable=False, index=True
    )
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)  # TODO(TYPE): replace Any with concrete type
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp(), nullable=False
    )
