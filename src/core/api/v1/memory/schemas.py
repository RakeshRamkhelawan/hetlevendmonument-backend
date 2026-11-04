"""
Memory domain schemas -- Pydantic models and enums.

Migrated from src/core/api/memory_endpoints.py (SP-API-003 Dag 5).
"""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class EmbeddingModel(str, Enum):
    """Embedding model options"""

    OPENAI_ADA_002 = "text-embedding-ada-002"
    OPENAI_3_SMALL = "text-embedding-3-small"
    OPENAI_3_LARGE = "text-embedding-3-large"
    COHERE_ENGLISH = "embed-english-v3.0"
    COHERE_MULTILINGUAL = "embed-multilingual-v3.0"
    LOCAL_SENTENCE_TRANSFORMERS = "sentence-transformers/all-MiniLM-L6-v2"


class ChunkingStrategy(str, Enum):
    """Document chunking strategy"""

    FIXED_SIZE = "fixed_size"
    SEMANTIC = "semantic"
    SENTENCE = "sentence"
    PARAGRAPH = "paragraph"
    RECURSIVE = "recursive"


class IndexStatus(str, Enum):
    """Index health status"""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    BUILDING = "building"
    FAILED = "failed"
    EMPTY = "empty"


class DocumentStatus(str, Enum):
    """Document indexing status"""

    PENDING = "pending"
    INDEXING = "indexing"
    INDEXED = "indexed"
    FAILED = "failed"
    DELETED = "deleted"


class ChunkingConfig(BaseModel):
    """Configuration for document chunking"""

    strategy: ChunkingStrategy = Field(ChunkingStrategy.RECURSIVE, description="Chunking strategy")
    chunk_size: int = Field(512, ge=100, le=4096, description="Target chunk size in tokens")
    chunk_overlap: int = Field(50, ge=0, le=512, description="Overlap between chunks")
    min_chunk_size: int = Field(100, ge=50, le=1024, description="Minimum chunk size")


class RetrievalConfig(BaseModel):
    """Configuration for retrieval settings"""

    top_k: int = Field(5, ge=1, le=50, description="Number of results to retrieve")
    similarity_threshold: float = Field(0.7, ge=0.0, le=1.0, description="Minimum similarity score")
    rerank_enabled: bool = Field(False, description="Enable reranking of results")
    hybrid_search: bool = Field(False, description="Enable hybrid (semantic + keyword) search")
    mmr_enabled: bool = Field(False, description="Enable Maximal Marginal Relevance")
    mmr_lambda: float = Field(0.5, ge=0.0, le=1.0, description="MMR diversity parameter")


class RAGConfig(BaseModel):
    """Full RAG configuration"""

    embedding_model: EmbeddingModel = Field(
        EmbeddingModel.OPENAI_3_SMALL, description="Embedding model"
    )
    embedding_dimensions: int = Field(1536, description="Embedding vector dimensions")
    chunking: ChunkingConfig = Field(
        default_factory=lambda: ChunkingConfig(),  # type: ignore[call-arg]
        description="Chunking settings",
    )
    retrieval: RetrievalConfig = Field(
        default_factory=lambda: RetrievalConfig(),  # type: ignore[call-arg]
        description="Retrieval settings",
    )
    index_name: str = Field("default", description="Index name")
    namespace: str | None = Field(None, description="Optional namespace for isolation")
    metadata_fields: list[str] = Field(default_factory=list, description="Metadata fields to index")
    updated_at: str | None = Field(None, description="Last update timestamp")
    updated_by: str | None = Field(None, description="User who last updated")


class RAGConfigResponse(BaseModel):
    """Response for RAG configuration"""

    config: RAGConfig
    tenant_id: int
    message: str


class IndexedDocument(BaseModel):
    """A document in the index"""

    id: str = Field(..., description="Document ID")
    source: str = Field(..., description="Document source/path")
    title: str | None = Field(None, description="Document title")
    status: DocumentStatus = Field(..., description="Indexing status")
    chunk_count: int = Field(0, description="Number of chunks")
    token_count: int = Field(0, description="Total tokens")
    indexed_at: str | None = Field(None, description="Indexing timestamp")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Document metadata")


class IndexStats(BaseModel):
    """Statistics about the memory index"""

    total_documents: int = Field(default=0, description="Total documents")
    total_chunks: int = Field(default=0, description="Total chunks")
    total_tokens: int = Field(default=0, description="Total tokens")
    index_size_bytes: int = Field(default=0, description="Index size in bytes")
    status: IndexStatus = Field(default=IndexStatus.EMPTY, description="Index health status")
    last_updated: str | None = Field(default=None, description="Last update timestamp")
    embedding_model: str | None = Field(default=None, description="Current embedding model")


class IndexResponse(BaseModel):
    """Response for index operations"""

    stats: IndexStats
    documents: list[IndexedDocument]
    tenant_id: int
    message: str


class IndexDocumentRequest(BaseModel):
    """Request to index a document"""

    source: str = Field(..., min_length=1, description="Document source/path")
    title: str | None = Field(None, description="Document title")
    content: str | None = Field(None, description="Document content (for text)")
    url: str | None = Field(None, description="Document URL (for web)")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    force_reindex: bool = Field(False, description="Force re-indexing if exists")


class IndexDocumentResponse(BaseModel):
    """Response for document indexing"""

    document: IndexedDocument
    message: str
    success: bool


class DeleteIndexResponse(BaseModel):
    """Response for index deletion"""

    deleted_documents: int
    deleted_chunks: int
    message: str
    success: bool
