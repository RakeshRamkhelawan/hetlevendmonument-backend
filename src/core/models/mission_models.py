"""
Mission Database Model

SQLAlchemy ORM model for Mission persistence.
Replaces the in-memory _missions_store dict (SP-A01).

Multi-tenant via tenant_id foreign key + RLS policy.
Soft-delete via deleted_at timestamp.
"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database.database import Base


class Mission(Base):  # type: ignore[misc]
    """
    Mission persistence model.

    Stores mission state including steps, impact, and reasoning chain
    in a JSONB payload column. Core filterable fields (tenant_id,
    status, agent_type) are explicit columns for query performance.

    ADR-005: tenant_id NOT NULL + RLS
    ADR-010: PostgreSQL persistence (no in-memory state)
    CLAUDE.md S.11.5: clock_timestamp() for serializable ordering
    """

    __tablename__ = "missions"

    __table_args__ = (
        Index(
            "ix_missions_active",
            "tenant_id",
            "created_at",
            postgresql_where="deleted_at IS NULL",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_by: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_type: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default=text("'workflow'")
    )
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default=text("'planned'")
    )
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)  # TODO(TYPE): replace Any with concrete type
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("clock_timestamp()"),
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
