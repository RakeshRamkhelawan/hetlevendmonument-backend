"""
Knowledge domain schemas -- Pydantic request/response models.

Migrated from src/core/api/knowledge_endpoints.py (SP-API-003 Dag 5).
"""

from typing import Any

from pydantic import BaseModel, Field


class KnowledgeCreateRequest(BaseModel):
    """Request model voor het aanmaken van knowledge entries."""

    content: str = Field(description="Knowledge content")
    type: str = Field(description="Type of knowledge (fact, procedure, rule, etc.)")
    metadata: dict[str, Any] | None = Field(default=None, description="Additional metadata")
    source: str | None = Field(default="manual", description="Source of knowledge")
    confidence_score: float | None = Field(default=1.0, description="Confidence score (0.0-1.0)")


class KnowledgeUpdateRequest(BaseModel):
    """Request model voor het updaten van knowledge entries."""

    entry_id: int = Field(description="ID of the knowledge entry to update")
    content: str | None = Field(default=None, description="Updated content")
    type: str | None = Field(default=None, description="Updated type")
    metadata: dict[str, Any] | None = Field(default=None, description="Updated metadata")
    confidence_score: float | None = Field(default=None, description="Updated confidence score")


class KnowledgeResponse(BaseModel):
    """Response model voor knowledge operations."""

    success: bool
    message: str
    task_id: str | None = None
    agent_response: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type


class KnowledgeListResponse(BaseModel):
    """Response model voor knowledge listing."""

    entries: list[dict[str, Any]] = Field(description="List of knowledge entries")
    total: int = Field(description="Total number of entries")
    timestamp: str = Field(description="Response timestamp")


class KnowledgeSearchRequest(BaseModel):
    """Request model voor knowledge search."""

    query: str = Field(description="Search query")
    type_filter: str | None = Field(default=None, description="Filter by knowledge type")
    min_confidence: float | None = Field(default=None, description="Minimum confidence score")
    limit: int | None = Field(default=10, description="Max results to return")


class KnowledgeCategoriesResponse(BaseModel):
    """Response model voor knowledge categories."""

    categories: list[str] = Field(description="List of knowledge categories/types")
    count_per_category: dict[str, int] = Field(description="Count of entries per category")
    timestamp: str = Field(description="Response timestamp")
