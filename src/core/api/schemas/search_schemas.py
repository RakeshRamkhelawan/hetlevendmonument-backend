"""
Pydantic Schemas for Search API

Request/response models with OpenAPI documentation.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class FusionMethod(str, Enum):
    """Available fusion methods for hybrid search"""

    RRF = "rrf"
    WEIGHTED = "weighted"


class SearchSource(str, Enum):
    """Source of search result"""

    VECTOR = "vector"
    BM25 = "bm25"
    BOTH = "both"


# ===========================================================================
# REQUEST MODELS
# ===========================================================================


class HybridSearchRequest(BaseModel):
    """Request body for hybrid search endpoint"""

    query: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Search query string",
        examples=["ancient temple architecture"],
    )
    top_k: int = Field(default=10, ge=1, le=100, description="Number of results to return")
    fusion_method: FusionMethod = Field(default=FusionMethod.RRF, description="Score fusion method")
    alpha: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="Balance: 1.0=vector only, 0.0=BM25 only",
    )
    rrf_k: int = Field(default=60, ge=1, le=1000, description="RRF smoothing constant")
    include_content: bool = Field(default=True, description="Include document content in response")
    max_content_length: int = Field(
        default=500, ge=0, le=10000, description="Max content characters in response"
    )

    @field_validator("query")
    @classmethod
    def strip_query(cls, v: str) -> str:
        return v.strip()

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "query": "Mughal architecture Taj Mahal",
                "top_k": 10,
                "fusion_method": "rrf",
                "alpha": 0.5,
            }
        }
    )


class BM25SearchRequest(BaseModel):
    """Request for BM25-only search"""

    query: str = Field(..., min_length=1, max_length=500)
    top_k: int = Field(default=10, ge=1, le=100)
    use_cache: bool = Field(default=True)


# ===========================================================================
# RESPONSE MODELS
# ===========================================================================


class SearchResultItem(BaseModel):
    """Single search result in response"""

    document_id: str = Field(..., description="Unique document ID")
    content: str | None = Field(None, description="Document content (truncated)")
    metadata: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type
    vector_score: float = Field(..., description="Score from vector search")
    bm25_score: float = Field(..., description="Score from BM25 search")
    hybrid_score: float = Field(..., description="Combined fusion score")
    source: SearchSource = Field(..., description="Which search found this")
    rank: int = Field(..., description="Position in results (1-indexed)")


class SearchMetadata(BaseModel):
    """Metadata about the search execution"""

    query: str
    tenant_id: int
    fusion_method: str
    alpha: float
    execution_time_ms: float
    vector_results_count: int
    bm25_results_count: int
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class HybridSearchResponse(BaseModel):
    """Complete response from hybrid search"""

    results: list[SearchResultItem]
    total_results: int
    metadata: SearchMetadata

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "results": [
                    {
                        "document_id": "doc_001",
                        "content": "The Taj Mahal is...",
                        "vector_score": 0.92,
                        "bm25_score": 4.5,
                        "hybrid_score": 0.034,
                        "source": "both",
                        "rank": 1,
                    }
                ],
                "total_results": 1,
                "metadata": {"query": "Taj Mahal", "fusion_method": "rrf"},
            }
        }
    )


class SearchErrorResponse(BaseModel):
    """Error response for search failures"""

    error: str
    error_code: str
    details: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
