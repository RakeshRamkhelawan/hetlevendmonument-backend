from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.core.focus_builder.validators import GraphTopologyValidator, GraphValidationError


# Flow Schemas
class FlowCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: str = Field(default="", max_length=2000)
    react_flow_graph: dict[str, Any]  # TODO(TYPE): replace Any with concrete type

    @field_validator("react_flow_graph")
    @classmethod
    def validate_graph_topology(cls, v: dict[str, Any]) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """
        Validate the React Flow graph structure before accepting it.

        Checks:
        - Exactly one trigger node
        - No cycles (DAG requirement)
        - All nodes connected
        - Valid edge references
        - Size limits (max 100 nodes, 500 edges)
        """
        try:
            validator = GraphTopologyValidator(v)
            validator.validate()
        except GraphValidationError as e:
            raise ValueError(str(e))
        return v


class FlowUpdate(BaseModel):
    name: str | None = None
    react_flow_graph: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
    is_published: bool | None = None


class FlowResponse(BaseModel):
    id: int
    tenant_id: int
    name: str
    react_flow_graph: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    activepieces_flow_id: str | None
    is_published: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Piece Schemas
class PieceResponse(BaseModel):
    piece_name: str
    display_name: str
    logo_url: str | None
    actions: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    triggers: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    last_synced_at: datetime

    model_config = ConfigDict(from_attributes=True)
