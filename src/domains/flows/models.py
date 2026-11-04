from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database.database import Base

# ============================================================================
# SQLAlchemy Models (Database)
# ============================================================================


class Flow(Base):  # type: ignore[misc]
    __tablename__ = "flows"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    tenant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("tenants.id"), nullable=False, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # React Flow Data (Source of Truth for UI)
    react_flow_graph = mapped_column(
        JSON().with_variant(JSONB, "postgresql").with_variant(String, "sqlite"),
        nullable=False,
    )
    ui_version: Mapped[str | None] = mapped_column(String(20), default="1.0")

    # ActivePieces Mapping (Execution Target)
    activepieces_flow_id: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    activepieces_project_id: Mapped[str | None] = mapped_column(String(255))
    activepieces_version: Mapped[int | None] = mapped_column(Integer, default=1)
    # Cache of the last compiled JSON to avoid expensive re-compilation if nothing changed
    activepieces_flow_json = mapped_column(
        JSON().with_variant(JSONB, "postgresql").with_variant(String, "sqlite"),
        nullable=True,
    )

    # Lifecycle
    is_published: Mapped[bool | None] = mapped_column(Boolean, default=False)
    last_executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    execution_count: Mapped[int | None] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    created_by: Mapped[int | None] = mapped_column(Integer, ForeignKey("users.id"))

    # Relationships
    # tenant = relationship("Tenant", back_populates="flows")
    # creator = relationship("User", foreign_keys=[created_by])


class PiecesCacheMetadata(Base):  # type: ignore[misc]
    """Metadata for the cached pieces catalog"""

    __tablename__ = "focus_builder_pieces_cache"
    __table_args__ = {"extend_existing": True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    piece_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    piece_version: Mapped[str | None] = mapped_column(String(50))
    display_name: Mapped[str | None] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    logo_url: Mapped[str | None] = mapped_column(String(500))
    actions = mapped_column(JSON().with_variant(JSONB, "postgresql").with_variant(String, "sqlite"))
    triggers = mapped_column(
        JSON().with_variant(JSONB, "postgresql").with_variant(String, "sqlite")
    )
    auth_config = mapped_column(
        JSON().with_variant(JSONB, "postgresql").with_variant(String, "sqlite")
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


# ============================================================================
# Pydantic Models (API / Intermediate Representation)
# ============================================================================


class ReactFlowNode(BaseModel):
    id: str
    type: str  # trigger, action, branch, loop
    position: dict[str, float]
    data: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    width: float | None = None
    height: float | None = None


class ReactFlowEdge(BaseModel):
    id: str
    source: str
    target: str
    sourceHandle: str | None = None
    targetHandle: str | None = None
    type: str | None = None


class ReactFlowGraph(BaseModel):
    nodes: list[ReactFlowNode] = Field(default_factory=list)
    edges: list[ReactFlowEdge] = Field(default_factory=list)
    viewport: dict[str, float] | None = None

    @field_validator("nodes")
    @classmethod
    def unique_node_ids(cls, nodes: list[ReactFlowNode]) -> list[ReactFlowNode]:
        ids = [n.id for n in nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate node ids detected")
        return nodes

    @field_validator("edges")
    @classmethod
    def unique_edge_ids(cls, edges: list[ReactFlowEdge]) -> list[ReactFlowEdge]:
        ids = [e.id for e in edges]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate edge ids detected")
        return edges


class FlowCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    react_flow_graph: ReactFlowGraph


class FlowUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    react_flow_graph: ReactFlowGraph | None = None
    is_published: bool | None = None


class FlowRead(BaseModel):
    id: int
    name: str
    description: str | None
    is_published: bool | None = False
    last_executed_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None
    activepieces_flow_id: str | None
    # Use Any to avoid validation errors when JSONB returns raw dict
    react_flow_graph: Any  # TODO(TYPE): replace Any with concrete type

    model_config = ConfigDict(from_attributes=True)
