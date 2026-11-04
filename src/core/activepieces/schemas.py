from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

TenantID = int


class ActivePiecesBase(BaseModel):
    """Base model for ActivePieces entities."""

    pass


# ============================================================================
# == Connection (App Connection) Models
# ============================================================================
class ConnectionBase(ActivePiecesBase):
    """Base connection properties."""

    name: str = Field(..., description="Unique name of the connection")
    app_name: str = Field(..., description="Name of the app (e.g., 'gmail')")
    value: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        ..., description="Connection configuration/tokens"
    )  # TODO(TYPE): replace Any with concrete type


class ConnectionCreate(ConnectionBase):
    """Schema for creating a connection.

    `project_id` is optioneel en bepaalt niets: het project is dat van de verbinding van de tenant;
    een ander project geeft een 403 (ADR-040 B3/B4).
    """

    project_id: str | None = Field(None, description="Genegeerd tenzij het het eigen project is")


class ConnectionRead(ConnectionBase):
    """Schema for reading a connection."""

    project_id: str = Field(..., description="ActivePieces Project ID")
    id: str
    created: datetime
    updated: datetime


# ============================================================================
# == Flow Models
# ============================================================================
class FlowBase(ActivePiecesBase):
    """Base flow properties."""

    project_id: str
    folder_id: str | None = None
    status: str = Field(..., description="Flow status (ENABLED/DISABLED)")


class FlowRead(FlowBase):
    """Schema for reading a flow."""

    id: str
    version_id: str
    created: datetime
    updated: datetime


class FlowTriggerRequest(ActivePiecesBase):
    """Schema for triggering a flow via webhook/sync request."""

    payload: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type


# ============================================================================
# == Flow Run Models
# ============================================================================
class FlowRunRead(ActivePiecesBase):
    """Schema for reading a flow run status."""

    id: str
    project_id: str
    flow_id: str
    status: str = Field(..., description="RUNNING, SUCCEEDED, FAILED")
    start_time: datetime
    finish_time: datetime | None = None
    duration: float | None = None


# ============================================================================
# == Piece (Integration) Models
# ============================================================================
class PieceRead(ActivePiecesBase):
    """Schema for an available integration piece."""

    model_config = ConfigDict(populate_by_name=True)

    name: str
    display_name: str = Field(..., alias="displayName")
    description: str | None = None
    logo_url: str | None = Field(None, alias="logoUrl")
    version: str
    categories: list[str] | None = Field(default_factory=list)
    actions: dict[str, Any] | int = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type
    triggers: dict[str, Any] | int = Field(
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type


# ============================================================================
# == Webhook Models
# ============================================================================
class WebhookPayload(ActivePiecesBase):
    """Schema for incoming webhooks from ActivePieces."""

    flow_id: str
    run_id: str
    status: str
    payload: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
