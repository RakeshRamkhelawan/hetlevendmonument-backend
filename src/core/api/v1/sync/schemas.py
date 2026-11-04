"""
Sync API Pydantic schemas.

ASCII-only, no emojis (CLAUDE.md Section 10).
"""

from typing import Any

from pydantic import BaseModel, Field, model_validator


class SnapshotNode(BaseModel):
    """A single node in a workflow snapshot."""

    id: str = Field(..., max_length=256, description="Node identifier")
    type: str = Field(default="default", max_length=100, description="Node type")
    position: dict[str, float] = Field(
        default_factory=dict, max_length=10, description="X/Y position"
    )
    data: dict[str, Any] = Field(default_factory=dict, max_length=100, description="Node payload")  # TODO(TYPE): replace Any with concrete type


class SnapshotEdge(BaseModel):
    """A single edge in a workflow snapshot."""

    id: str = Field(..., max_length=256, description="Edge identifier")
    source: str = Field(..., max_length=256, description="Source node id")
    target: str = Field(..., max_length=256, description="Target node id")
    label: str | None = Field(default=None, max_length=256, description="Optional edge label")


class SnapshotRequest(BaseModel):
    """Request body for saving a workflow snapshot."""

    nodes: list[SnapshotNode] = Field(
        default_factory=list, max_length=5000, description="Workflow nodes"
    )
    edges: list[SnapshotEdge] = Field(
        default_factory=list, max_length=5000, description="Workflow edges"
    )
    version: int = Field(default=1, ge=1, description="Snapshot version")

    @model_validator(mode="before")
    @classmethod
    def _check_total_size(cls, data: Any) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Reject payloads that exceed 1MB serialized."""
        if isinstance(data, dict):
            import json

            size = len(json.dumps(data))
            if size > 1_048_576:
                raise ValueError("Snapshot payload exceeds 1MB limit")
        return data


class SnapshotResponse(BaseModel):
    """Response wrapper for snapshot operations."""

    success: bool
    data: dict[str, Any]  # TODO(TYPE): replace Any with concrete type


class AwarenessResponse(BaseModel):
    """Response wrapper for awareness operations."""

    success: bool
    data: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
