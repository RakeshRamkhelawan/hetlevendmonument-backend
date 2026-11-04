"""
ActivePieces Database Models

SQLAlchemy models for persisting ActivePieces data:
- Flows
- Connections
- Flow Runs
- Sync Logs
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database.database import Base

JSONType = JSON().with_variant(JSONB, "postgresql")


class ActivePiecesFlow(Base):  # type: ignore[misc]
    """Database model for ActivePieces flows"""

    __tablename__ = "activepieces_flows"

    id: Mapped[Any] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)  # TODO(TYPE): replace Any with concrete type
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # ActivePieces reference
    ap_flow_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # Flow metadata
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str | None] = mapped_column(
        String(50), default="DISABLED"
    )  # ENABLED, DISABLED

    # Full flow definition (React Flow + AP format)
    flow_definition: Mapped[Any | None] = mapped_column(JSONType, default=dict)  # TODO(TYPE): replace Any with concrete type

    # Timestamps
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    runs = relationship(
        "ActivePiecesFlowRun",
        back_populates="flow",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<ActivePiecesFlow(id={self.id}, name='{self.name}', status='{self.status}')>"


class ActivePiecesConnection(Base):  # type: ignore[misc]
    """Database model for ActivePieces app connections"""

    __tablename__ = "activepieces_connections"

    id: Mapped[Any] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)  # TODO(TYPE): replace Any with concrete type
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # ActivePieces reference
    ap_connection_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # Connection metadata
    app_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str | None] = mapped_column(
        String(50), default="ACTIVE"
    )  # ACTIVE, ERROR, EXPIRED

    # Encrypted credentials (encrypted at application level)
    encrypted_credentials: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Usage tracking
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<ActivePiecesConnection(id={self.id}, app='{self.app_name}', name='{self.name}')>"


class ActivePiecesFlowRun(Base):  # type: ignore[misc]
    """Database model for ActivePieces flow execution runs"""

    __tablename__ = "activepieces_flow_runs"

    id: Mapped[Any] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)  # TODO(TYPE): replace Any with concrete type
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # References
    flow_id = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("activepieces_flows.id", ondelete="CASCADE"),
        nullable=False,
    )
    ap_run_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    project_id: Mapped[str] = mapped_column(String(255), nullable=False)

    # Execution metadata
    status = mapped_column(String(50), default="RUNNING")  # RUNNING, SUCCEEDED, FAILED, STOPPED
    payload: Mapped[Any | None] = mapped_column(JSONType, default=dict)  # Input payload  # TODO(TYPE): replace Any with concrete type
    output: Mapped[Any | None] = mapped_column(JSONType, nullable=True)  # Output data  # TODO(TYPE): replace Any with concrete type
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Performance metrics
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Timestamps
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    flow = relationship("ActivePiecesFlow", back_populates="runs")

    def __repr__(self) -> str:
        return (
            f"<ActivePiecesFlowRun(id={self.id}, status='{self.status}', flow_id={self.flow_id})>"
        )


class ActivePiecesSyncLog(Base):  # type: ignore[misc]
    """Database model for ActivePieces synchronization logs"""

    __tablename__ = "activepieces_sync_logs"

    id: Mapped[Any] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)  # TODO(TYPE): replace Any with concrete type
    tenant_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # Sync metadata
    sync_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # 'pieces', 'flows', 'connections'
    status: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # 'success', 'partial', 'failed'

    # Statistics
    items_synced: Mapped[int | None] = mapped_column(Integer, default=0)
    items_failed: Mapped[int | None] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return (
            f"<ActivePiecesSyncLog(id={self.id}, type='{self.sync_type}', status='{self.status}')>"
        )


# ============================================================================
# Input/Output Models (Pydantic) for API
# ============================================================================

from pydantic import BaseModel, ConfigDict, Field


class ReactFlowData(BaseModel):
    label: str | None = None
    triggerType: str | None = None  # WEBHOOK, SCHEDULE, etc.
    pieceName: str | None = None
    pieceVersion: str | None = None
    actionName: str | None = None
    triggerName: str | None = None
    input: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    conditions: list[list[dict[str, Any]]] | None = None  # TODO(TYPE): replace Any with concrete type
    items: str | None = None


class ReactFlowNode(BaseModel):
    id: str
    type: str  # trigger, action, branch, loop
    data: ReactFlowData
    position: dict[str, float]


class ReactFlowEdge(BaseModel):
    id: str
    source: str
    target: str
    sourceHandle: str | None = None
    targetHandle: str | None = None


class ReactFlowGraph(BaseModel):
    nodes: list[ReactFlowNode]
    edges: list[ReactFlowEdge]
    viewport: dict[str, float] | None = None


class APAction(BaseModel):
    name: str
    type: str  # PIECE, BRANCH, LOOP_ON_ITEMS, CODE
    displayName: str
    settings: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    nextAction: Optional["APAction"] = None
    onSuccessAction: Optional["APAction"] = None
    onFailureAction: Optional["APAction"] = None
    firstLoopAction: Optional["APAction"] = None
    valid: bool = True


class APTrigger(BaseModel):
    name: str = "trigger"
    type: str  # WEBHOOK, SCHEDULE, PIECE_TRIGGER, EMPTY
    displayName: str
    settings: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    nextAction: APAction | None = None
    valid: bool = True


class APFlow(BaseModel):
    displayName: str
    trigger: APTrigger
    valid: bool = True
    schema_version: str = Field(default="1", alias="schemaVersion")

    model_config = ConfigDict(populate_by_name=True)


# Resolve recursive references
APAction.model_rebuild()
APTrigger.model_rebuild()


class IRNode(BaseModel):
    """Intermediate Representation Node"""

    id: str
    type: str
    piece_name: str
    config: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    next_action: str | None = None
