"""
Canvas Pydantic Schemas

Request and response models for the Canvas API.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from src.domains.canvas.models import AgentStatus, BlockType, CollaboratorRole

# ============================================================================
# Base Schemas
# ============================================================================


class Position(BaseModel):
    """Position on canvas (x, y coordinates)."""

    x: Decimal = Field(..., description="X coordinate")
    y: Decimal = Field(..., description="Y coordinate")


class Size(BaseModel):
    """Size dimensions (width, height)."""

    width: Decimal = Field(..., ge=0, description="Width in pixels")
    height: Decimal = Field(..., ge=0, description="Height in pixels")


class Viewport(BaseModel):
    """User viewport (what they're looking at)."""

    x: Decimal
    y: Decimal
    zoom: Decimal = Field(default=Decimal("1.0"))


# ============================================================================
# Block Content Schemas
# ============================================================================


class TextBlockContent(BaseModel):
    """Content for text blocks."""

    text: str = ""
    format: str = "markdown"  # markdown, html


class MetricBlockContent(BaseModel):
    """Content for metric/KPI blocks."""

    metric_name: str
    current_value: float
    target_value: float | None = None
    unit: str = ""
    trend: str = "neutral"  # up, down, neutral
    chart_type: str = "number"  # line, bar, number
    data_source: str | None = None


class AgentLogEntry(BaseModel):
    """Log entry for agent execution."""

    timestamp: datetime
    level: str  # info, warning, error
    message: str


class AgentResult(BaseModel):
    """Result from agent execution."""

    status: str
    data: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    summary: str | None = None


class AgentBlockContent(BaseModel):
    """Content for agent blocks."""

    agent_id: UUID
    agent_name: str
    status: AgentStatus = AgentStatus.IDLE
    progress: float = Field(default=0.0, ge=0.0, le=100.0)
    current_task: str | None = None
    logs: list[AgentLogEntry] = Field(default_factory=list)
    result: AgentResult | None = None
    auto_refresh: bool = True
    show_logs: bool = True
    show_result: bool = True


class TaskItem(BaseModel):
    """Individual task item."""

    id: str
    text: str
    completed: bool = False


class TaskBlockContent(BaseModel):
    """Content for task/checklist blocks."""

    title: str
    description: str | None = None
    status: str = "pending"  # pending, in_progress, completed
    assignee: UUID | None = None
    due_date: datetime | None = None
    checklist: list[TaskItem] = Field(default_factory=list)


class DataBlockContent(BaseModel):
    """Content for data display blocks."""

    data: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    view_type: str = "table"  # table, json, cards
    data_schema: dict[str, Any] | None = Field(default=None, alias="schema")  # TODO(TYPE): replace Any with concrete type


class ChartDataset(BaseModel):
    """Dataset for chart blocks."""

    label: str
    data: list[float]
    color: str | None = None


class ChartBlockContent(BaseModel):
    """Content for chart blocks."""

    chart_type: str = "bar"  # bar, line, pie, doughnut
    title: str | None = None
    labels: list[str] = Field(default_factory=list)
    datasets: list[ChartDataset] = Field(default_factory=list)


class ImageBlockContent(BaseModel):
    """Content for image blocks."""

    url: str
    alt_text: str | None = None
    caption: str | None = None


BlockContent = (
    TextBlockContent
    | MetricBlockContent
    | AgentBlockContent
    | TaskBlockContent
    | DataBlockContent
    | ChartBlockContent
    | ImageBlockContent
    | dict[str, Any]  # Fallback for unknown types  # TODO(TYPE): replace Any with concrete type
)


# ============================================================================
# Block Schemas
# ============================================================================


class BlockBase(BaseModel):
    """Base block schema."""

    type: BlockType
    position: Position
    size: Size
    z_index: int = 0
    content: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type


class BlockCreate(BlockBase):
    """Schema for creating a block."""

    agent_id: UUID | None = None
    execution_id: UUID | None = None


class BlockUpdate(BaseModel):
    """Schema for updating a block."""

    position: Position | None = None
    size: Size | None = None
    z_index: int | None = None
    content: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type


class BlockRead(BlockBase):
    """Schema for reading a block."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    canvas_id: UUID
    agent_id: UUID | None = None
    execution_id: UUID | None = None
    created_by: UUID
    created_at: datetime
    updated_at: datetime
    version: int


# ============================================================================
# Connection Schemas
# ============================================================================


class ConnectionBase(BaseModel):
    """Base connection schema."""

    from_block_id: UUID
    to_block_id: UUID
    connection_type: str = "straight"  # straight, curved, orthogonal
    color: str | None = None
    label: str | None = None
    is_bidirectional: bool = False
    trigger: str | None = None


class ConnectionCreate(ConnectionBase):
    """Schema for creating a connection."""

    pass


class ConnectionRead(ConnectionBase):
    """Schema for reading a connection."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    canvas_id: UUID


# ============================================================================
# Collaborator Schemas
# ============================================================================


class CollaboratorBase(BaseModel):
    """Base collaborator schema."""

    user_id: UUID
    role: CollaboratorRole = CollaboratorRole.VIEWER


class CollaboratorCreate(CollaboratorBase):
    """Schema for adding a collaborator."""

    pass


class CollaboratorRead(CollaboratorBase):
    """Schema for reading a collaborator."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    canvas_id: UUID
    added_by: UUID
    added_at: datetime
    user_name: str | None = None  # Populated by service
    user_avatar: str | None = None  # Populated by service


# ============================================================================
# Canvas Schemas
# ============================================================================


class CanvasBase(BaseModel):
    """Base canvas schema."""

    name: str = Field(..., min_length=1, max_length=255)
    template: str = "blank"
    is_public: bool = False


class CanvasCreate(CanvasBase):
    """Schema for creating a canvas."""

    pass


class CanvasUpdate(BaseModel):
    """Schema for updating a canvas."""

    name: str | None = Field(None, min_length=1, max_length=255)
    is_public: bool | None = None


class CanvasRead(CanvasBase):
    """Schema for reading a canvas."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    owner_id: UUID
    created_at: datetime
    updated_at: datetime
    version: int

    # Related data (populated by service)
    blocks: list[BlockRead] = Field(default_factory=list)
    connections: list[ConnectionRead] = Field(default_factory=list)
    collaborators: list[CollaboratorRead] = Field(default_factory=list)


class CanvasListRead(CanvasBase):
    """Schema for listing canvases (lightweight)."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    owner_id: UUID
    created_at: datetime
    updated_at: datetime
    block_count: int = 0  # Populated by service
    collaborator_count: int = 0  # Populated by service


# ============================================================================
# Session/Presence Schemas
# ============================================================================


class CanvasSession(BaseModel):
    """Active user session on canvas."""

    session_id: str
    user_id: UUID
    user_name: str
    user_avatar: str | None = None
    cursor_position: Position | None = None
    selected_block_id: UUID | None = None
    viewport: Viewport
    joined_at: datetime


# ============================================================================
# WebSocket Message Schemas
# ============================================================================


class WSMessageType(str, Enum):
    """WebSocket message types."""

    # Client -> Server
    CURSOR_MOVE = "cursor_move"
    BLOCK_SELECT = "block_select"
    OPERATION = "operation"
    JOIN = "join"
    LEAVE = "leave"

    # Server -> Client
    PRESENCE = "presence"
    OPERATION_ACK = "operation_ack"
    OPERATION_BROADCAST = "operation_broadcast"
    ERROR = "error"


class WSMessage(BaseModel):
    """Base WebSocket message."""

    type: WSMessageType
    client_id: str
    timestamp: datetime | None = None


class CursorMoveMessage(WSMessage):
    """Cursor position update."""

    type: WSMessageType = WSMessageType.CURSOR_MOVE
    position: Position
    viewport: Viewport | None = None


class BlockSelectMessage(WSMessage):
    """Block selection update."""

    type: WSMessageType = WSMessageType.BLOCK_SELECT
    block_id: UUID | None = None


class OperationMessage(WSMessage):
    """Canvas operation (for OT)."""

    type: WSMessageType = WSMessageType.OPERATION
    operation_type: str  # insert, delete, update, move
    target_type: str  # block, connection, canvas
    target_id: UUID | None = None
    data: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    revision: int


class PresenceMessage(WSMessage):
    """User presence update."""

    type: WSMessageType = WSMessageType.PRESENCE
    sessions: list[CanvasSession]


class OperationAckMessage(WSMessage):
    """Operation acknowledged."""

    type: WSMessageType = WSMessageType.OPERATION_ACK
    operation_id: str
    revision: int


class OperationBroadcastMessage(WSMessage):
    """Operation broadcast to other clients."""

    type: WSMessageType = WSMessageType.OPERATION_BROADCAST
    operation_type: str
    target_type: str
    target_id: UUID | None = None
    data: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    revision: int
    client_id: str  # Original client


# ============================================================================
# Search/Filter Schemas
# ============================================================================


class CanvasFilter(BaseModel):
    """Filter options for canvas listing."""

    search: str | None = None
    template: str | None = None
    owner_only: bool = False
    shared_only: bool = False


class CanvasSort(BaseModel):
    """Sort options for canvas listing."""

    field: str = "updated_at"  # name, created_at, updated_at
    direction: str = "desc"  # asc, desc
