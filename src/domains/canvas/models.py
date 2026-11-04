"""Canvas domain models.

Minimal SQLAlchemy canvas models used by the canvas API, schemas, and tests.
These models restore the compatibility layer expected by the canvas domain
without pulling in unrelated cross-domain foreign key dependencies.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from src.core.database.database import Base


class BlockType(str, Enum):
    """Supported canvas block types."""

    TEXT = "text"
    METRIC = "metric"
    AGENT = "agent"
    TASK = "task"
    DATA = "data"
    CHART = "chart"
    IMAGE = "image"


class CollaboratorRole(str, Enum):
    """Canvas collaborator roles."""

    VIEWER = "viewer"
    EDITOR = "editor"
    ADMIN = "admin"


class AgentStatus(str, Enum):
    """Agent execution status shown in canvas blocks."""

    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Canvas(Base):  # type: ignore[misc]
    """Top-level collaborative canvas container."""

    __tablename__ = "canvases"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    tenant_id: Mapped[int] = mapped_column(Integer, index=True)
    owner_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    template: Mapped[str] = mapped_column(String(100), default="blank", nullable=False)
    is_public: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    blocks: Mapped[list[CanvasBlock]] = relationship(
        back_populates="canvas", cascade="all, delete-orphan"
    )
    connections: Mapped[list[CanvasConnection]] = relationship(
        back_populates="canvas", cascade="all, delete-orphan"
    )
    collaborators: Mapped[list[CanvasCollaborator]] = relationship(
        back_populates="canvas", cascade="all, delete-orphan"
    )
    operations: Mapped[list[CanvasOperation]] = relationship(
        back_populates="canvas", cascade="all, delete-orphan"
    )


class CanvasBlock(Base):  # type: ignore[misc]
    """Canvas content block."""

    __tablename__ = "canvas_blocks"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    canvas_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("canvases.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    x: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    y: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("0.00"))
    width: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("100.00"))
    height: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=Decimal("100.00"))
    z_index: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    content: Mapped[dict[str, Any]] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        JSONB, default=dict, nullable=False
    )  # TODO(TYPE): replace Any with concrete type
    created_by: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), index=True)
    agent_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    execution_id: Mapped[uuid.UUID | None] = mapped_column(PG_UUID(as_uuid=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    canvas: Mapped[Canvas] = relationship(back_populates="blocks")


class CanvasConnection(Base):  # type: ignore[misc]
    """Connection between two canvas blocks."""

    __tablename__ = "canvas_connections"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    canvas_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("canvases.id", ondelete="CASCADE"), index=True
    )
    from_block_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), index=True)
    to_block_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), index=True)
    connection_type: Mapped[str] = mapped_column(String(50), default="straight")
    color: Mapped[str | None] = mapped_column(String(32))
    label: Mapped[str | None] = mapped_column(String(255))
    is_bidirectional: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    trigger: Mapped[str | None] = mapped_column(String(255))

    canvas: Mapped[Canvas] = relationship(back_populates="connections")


class CanvasCollaborator(Base):  # type: ignore[misc]
    """Collaborator membership for a canvas."""

    __tablename__ = "canvas_collaborators"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    canvas_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("canvases.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), index=True)
    role: Mapped[str] = mapped_column(String(32), default=CollaboratorRole.VIEWER.value)
    added_by: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), index=True)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    canvas: Mapped[Canvas] = relationship(back_populates="collaborators")


class CanvasOperation(Base):  # type: ignore[misc]
    """Revisioned canvas operation used for collaboration sync."""

    __tablename__ = "canvas_operations"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    canvas_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("canvases.id", ondelete="CASCADE"), index=True
    )
    operation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[uuid.UUID] = mapped_column(PG_UUID(as_uuid=True), index=True)
    data: Mapped[dict[str, Any]] = mapped_column(  # TODO(TYPE): replace Any with concrete type
        JSONB, default=dict, nullable=False
    )  # TODO(TYPE): replace Any with concrete type
    client_id: Mapped[str] = mapped_column(String(255), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now()
    )

    canvas: Mapped[Canvas] = relationship(back_populates="operations")


__all__ = [
    "AgentStatus",
    "BlockType",
    "Canvas",
    "CanvasBlock",
    "CanvasCollaborator",
    "CanvasConnection",
    "CanvasOperation",
    "CollaboratorRole",
]
