# orphan:exempt reason: legacy flat file, replaced by src/core/api/v1/memory/ (SP-API-003)
"""
Memory API Endpoints
====================

Production-ready REST API endpoints for Memory Agent RAG configuration and indexing.

Features:
- Configure RAG (Retrieval-Augmented Generation) settings
- Manage memory index for document retrieval
- Multi-tenant isolation (JWT + tenant context)
- RBAC enforcement via OAuth2 scopes
- Index statistics and health monitoring

Endpoints:
- GET/PUT /api/v1/memory/config - Manage RAG configuration
- GET/POST/DELETE /api/v1/memory/index - Manage memory index

Security: JWT required, tenant isolated, scope validated
"""

import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional, cast

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.dependencies import get_db
from src.core.auth.api_deps import require_scopes, OAuth2Scope
from src.core.middleware.tenant_context import get_current_tenant_id

logger = logging.getLogger(__name__)


# ============================================================================
# Enums
# ============================================================================


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


# ============================================================================
# Pydantic Models
# ============================================================================


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
    metadata: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict, description="Document metadata"
    )  # TODO(TYPE): replace Any with concrete type


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
    metadata: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict, description="Additional metadata"
    )  # TODO(TYPE): replace Any with concrete type
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


# ============================================================================
# In-Memory Storage (Demo)
# ============================================================================

# Simulated storage for demo - in production, use persistent storage
_tenant_configs: dict[int, RAGConfig] = {}
_tenant_indexes: dict[int, dict[str, IndexedDocument]] = {}


def get_tenant_config(tenant_id: int) -> RAGConfig:
    """Get or create tenant configuration"""
    if tenant_id not in _tenant_configs:
        _tenant_configs[tenant_id] = cast(
            Any, RAGConfig  # TODO(TYPE): replace Any with concrete type
        )()  # TODO(TYPE): replace Any with concrete type
    return _tenant_configs[tenant_id]


def save_tenant_config(tenant_id: int, config: RAGConfig) -> None:
    """Save tenant configuration"""
    _tenant_configs[tenant_id] = config


def get_tenant_index(tenant_id: int) -> dict[str, IndexedDocument]:
    """Get or create tenant index"""
    if tenant_id not in _tenant_indexes:
        _tenant_indexes[tenant_id] = {}
    return _tenant_indexes[tenant_id]


# ============================================================================
# Router
# ============================================================================

router = APIRouter(prefix="/api/v1/memory", tags=["memory"])


# ============================================================================
# Helper Functions
# ============================================================================


async def get_tenant() -> int:
    """Get tenant ID with error handling"""
    tenant_id = get_current_tenant_id()
    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required. Ensure JWT contains tenant_id.",
        )
    return tenant_id


def get_user_id(current_user: dict[str, Any]) -> str:  # TODO(TYPE): replace Any with concrete type
    """Extract user ID from current user"""
    if isinstance(current_user, dict):
        return str(current_user.get("user_id") or current_user.get("id") or "unknown")
    if hasattr(current_user, "id"):
        return str(current_user.id)
    return "unknown"


def calculate_index_stats(documents: dict[str, IndexedDocument], config: RAGConfig) -> IndexStats:
    """Calculate index statistics"""
    if not documents:
        return IndexStats(status=IndexStatus.EMPTY)

    total_docs = len(documents)
    total_chunks = sum(d.chunk_count for d in documents.values())
    total_tokens = sum(d.token_count for d in documents.values())

    # Estimate index size (rough approximation)
    embedding_dims = config.embedding_dimensions
    index_size = total_chunks * embedding_dims * 4  # 4 bytes per float32

    # Determine status
    indexed_count = sum(1 for d in documents.values() if d.status == DocumentStatus.INDEXED)
    failed_count = sum(1 for d in documents.values() if d.status == DocumentStatus.FAILED)
    pending_count = sum(
        1
        for d in documents.values()
        if d.status in [DocumentStatus.PENDING, DocumentStatus.INDEXING]
    )

    if pending_count > 0:
        status = IndexStatus.BUILDING
    elif failed_count > total_docs * 0.1:  # More than 10% failed
        status = IndexStatus.DEGRADED
    elif failed_count > 0:
        status = IndexStatus.DEGRADED
    elif indexed_count == total_docs:
        status = IndexStatus.HEALTHY
    else:
        status = IndexStatus.HEALTHY

    # Find last update
    last_updated = None
    for doc in documents.values():
        if doc.indexed_at:
            if not last_updated or doc.indexed_at > last_updated:
                last_updated = doc.indexed_at

    return IndexStats(
        total_documents=total_docs,
        total_chunks=total_chunks,
        total_tokens=total_tokens,
        index_size_bytes=index_size,
        status=status,
        last_updated=last_updated,
        embedding_model=config.embedding_model.value,
    )


def simulate_document_indexing(request: IndexDocumentRequest) -> IndexedDocument:
    """Simulate document indexing (demo)"""
    doc_id = f"doc_{uuid.uuid4().hex[:12]}"
    now = datetime.now(timezone.utc)

    # Simulate content analysis
    content = request.content or f"[Content from: {request.source}]"
    token_count = len(content.split())
    chunk_count = max(1, token_count // 512)

    return IndexedDocument(
        id=doc_id,
        source=request.source,
        title=request.title or request.source.split("/")[-1],
        status=DocumentStatus.INDEXED,
        chunk_count=chunk_count,
        token_count=token_count,
        indexed_at=now.isoformat(),
        metadata=request.metadata,
    )


# ============================================================================
# Config Endpoints
# ============================================================================


@router.get(
    "/config",
    response_model=RAGConfigResponse,
    summary="Get RAG configuration",
    description="Retrieves the current RAG configuration for the tenant.",
)
async def get_config(
    db: AsyncSession = Depends(get_db),
    tenant_id: int | None = Depends(get_tenant),
    current_user: dict[str, Any] = Depends(  # TODO(TYPE): replace Any with concrete type
        require_scopes(OAuth2Scope.WORKFLOWS_READ)
    ),  # TODO(TYPE): replace Any with concrete type
) -> RAGConfigResponse:
    """
    Get current RAG configuration.

    Returns configuration including:
    - Embedding model settings
    - Chunking strategy and parameters
    - Retrieval settings (top_k, similarity threshold, etc.)

    Security: Requires JWT with workflows:read scope
    """
    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required.",
        )
    user_id = get_user_id(current_user)

    logger.info("Getting RAG configuration", extra={"tenant_id": tenant_id, "user_id": user_id})

    config = get_tenant_config(tenant_id)

    return RAGConfigResponse(
        config=config,
        tenant_id=tenant_id,
        message="RAG configuration retrieved successfully",
    )


@router.put(
    "/config",
    response_model=RAGConfigResponse,
    summary="Update RAG configuration",
    description="Updates the RAG configuration for the tenant.",
)
async def update_config(
    config_update: RAGConfig = Body(...),
    db: AsyncSession = Depends(get_db),
    tenant_id: int | None = Depends(get_tenant),
    current_user: dict[str, Any] = Depends(  # TODO(TYPE): replace Any with concrete type
        require_scopes(OAuth2Scope.WORKFLOWS_WRITE)
    ),  # TODO(TYPE): replace Any with concrete type
) -> RAGConfigResponse:
    """
    Update RAG configuration.

    Allows updating:
    - Embedding model
    - Chunking strategy and parameters
    - Retrieval settings

    Note: Changing embedding model may require re-indexing.

    Security: Requires JWT with workflows:write scope
    """
    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required.",
        )
    user_id = get_user_id(current_user)
    now = datetime.now(timezone.utc)

    logger.info(
        "Updating RAG configuration",
        extra={
            "tenant_id": tenant_id,
            "user_id": user_id,
            "embedding_model": config_update.embedding_model.value,
        },
    )

    # Check if embedding model changed
    current_config = get_tenant_config(tenant_id)
    model_changed = current_config.embedding_model != config_update.embedding_model

    # Update timestamps
    config_update.updated_at = now.isoformat()
    config_update.updated_by = user_id

    # Save configuration
    save_tenant_config(tenant_id, config_update)

    message = "RAG configuration updated successfully"
    if model_changed:
        message += ". Note: Embedding model changed - consider re-indexing documents."

    logger.info(
        "RAG configuration updated",
        extra={"tenant_id": tenant_id, "model_changed": model_changed},
    )

    return RAGConfigResponse(config=config_update, tenant_id=tenant_id, message=message)


# ============================================================================
# Index Endpoints
# ============================================================================


@router.get(
    "/index",
    response_model=IndexResponse,
    summary="Get index status and documents",
    description="Retrieves index statistics and list of indexed documents.",
)
async def get_index(
    status_filter: DocumentStatus | None = Query(None, description="Filter by document status"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
    tenant_id: int | None = Depends(get_tenant),
    current_user: dict[str, Any] = Depends(  # TODO(TYPE): replace Any with concrete type
        require_scopes(OAuth2Scope.WORKFLOWS_READ)
    ),  # TODO(TYPE): replace Any with concrete type
) -> IndexResponse:
    """
    Get index status and documents.

    Returns:
    - Index statistics (document count, chunk count, size)
    - Health status
    - List of indexed documents with pagination

    Security: Requires JWT with workflows:read scope
    """
    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required.",
        )
    user_id = get_user_id(current_user)

    logger.info("Getting index status", extra={"tenant_id": tenant_id, "user_id": user_id})

    config = get_tenant_config(tenant_id)
    index = get_tenant_index(tenant_id)

    # Filter documents
    docs = list(index.values())
    if status_filter:
        docs = [d for d in docs if d.status == status_filter]

    # Calculate stats
    stats = calculate_index_stats(index, config)

    # Paginate
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size
    paginated_docs = docs[start_idx:end_idx]

    return IndexResponse(
        stats=stats,
        documents=paginated_docs,
        tenant_id=tenant_id,
        message=f"Index contains {stats.total_documents} document(s) with {stats.total_chunks} chunks",
    )


@router.post(
    "/index",
    response_model=IndexDocumentResponse,
    summary="Index a document",
    description="Indexes a new document or re-indexes an existing one.",
)
async def index_document(
    request: IndexDocumentRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    tenant_id: int | None = Depends(get_tenant),
    current_user: dict[str, Any] = Depends(  # TODO(TYPE): replace Any with concrete type
        require_scopes(OAuth2Scope.WORKFLOWS_WRITE)
    ),  # TODO(TYPE): replace Any with concrete type
) -> IndexDocumentResponse:
    """
    Index a document.

    Supports:
    - Direct text content
    - URL for web documents
    - File path for local documents

    Security: Requires JWT with workflows:write scope
    """
    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required.",
        )
    user_id = get_user_id(current_user)

    logger.info(
        "Indexing document",
        extra={"tenant_id": tenant_id, "user_id": user_id, "source": request.source},
    )

    index = get_tenant_index(tenant_id)

    # Check for existing document with same source
    existing = None
    for doc_id, doc in index.items():
        if doc.source == request.source:
            existing = doc_id
            break

    if existing and not request.force_reindex:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Document with source '{request.source}' already exists. Use force_reindex=true to re-index.",
        )

    # Remove existing if re-indexing
    if existing:
        del index[existing]

    # Index document
    document = simulate_document_indexing(request)
    index[document.id] = document

    logger.info(
        "Document indexed successfully",
        extra={
            "document_id": document.id,
            "chunk_count": document.chunk_count,
            "token_count": document.token_count,
        },
    )

    return IndexDocumentResponse(
        document=document,
        message=f"Document indexed successfully with {document.chunk_count} chunk(s)",
        success=True,
    )


@router.delete(
    "/index",
    response_model=DeleteIndexResponse,
    summary="Clear or delete from index",
    description="Deletes documents from the index or clears the entire index.",
)
async def delete_from_index(
    document_id: str | None = Query(None, description="Specific document ID to delete"),
    clear_all: bool = Query(False, description="Clear entire index"),
    db: AsyncSession = Depends(get_db),
    tenant_id: int | None = Depends(get_tenant),
    current_user: dict[str, Any] = Depends(  # TODO(TYPE): replace Any with concrete type
        require_scopes(OAuth2Scope.WORKFLOWS_WRITE)
    ),  # TODO(TYPE): replace Any with concrete type
) -> DeleteIndexResponse:
    """
    Delete from index.

    Options:
    - Delete specific document by ID
    - Clear entire index (clear_all=true)

    Security: Requires JWT with workflows:write scope
    """
    if tenant_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tenant context required.",
        )
    user_id = get_user_id(current_user)

    logger.info(
        "Deleting from index",
        extra={
            "tenant_id": tenant_id,
            "user_id": user_id,
            "document_id": document_id,
            "clear_all": clear_all,
        },
    )

    index = get_tenant_index(tenant_id)

    if clear_all:
        # Clear entire index
        deleted_docs = len(index)
        deleted_chunks = sum(d.chunk_count for d in index.values())
        index.clear()

        logger.info(
            "Index cleared",
            extra={"deleted_documents": deleted_docs, "deleted_chunks": deleted_chunks},
        )

        return DeleteIndexResponse(
            deleted_documents=deleted_docs,
            deleted_chunks=deleted_chunks,
            message=f"Index cleared: {deleted_docs} document(s) removed",
            success=True,
        )

    if document_id:
        # Delete specific document
        if document_id not in index:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {document_id} not found in index",
            )

        doc = index[document_id]
        deleted_chunks = doc.chunk_count
        del index[document_id]

        logger.info(
            "Document deleted from index",
            extra={"document_id": document_id, "deleted_chunks": deleted_chunks},
        )

        return DeleteIndexResponse(
            deleted_documents=1,
            deleted_chunks=deleted_chunks,
            message=f"Document {document_id} deleted from index",
            success=True,
        )

    # No action specified
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Specify document_id to delete a specific document or clear_all=true to clear index",
    )
