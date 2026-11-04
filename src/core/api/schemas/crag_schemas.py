"""
CRAG API Schemas
"""

from typing import Any, Optional

from pydantic import BaseModel, Field


class CRAGRequest(BaseModel):
    """Request body for CRAG chat"""

    query: str = Field(..., min_length=1, max_length=1000, description="User question")
    # Optional config overrides could go here


class CRAGResponse(BaseModel):
    """Response from CRAG agent"""

    answer: str
    sources: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    web_search_triggered: bool
    original_query: str
    metadata: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
