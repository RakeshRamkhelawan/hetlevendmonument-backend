"""
Memory domain dependencies and in-memory storage helpers.

Migrated from src/core/api/memory_endpoints.py (SP-API-003 Dag 5).
"""

import uuid
from datetime import datetime, timezone
from typing import Any, cast

from fastapi import HTTPException, status

from src.core.middleware.tenant_context import get_current_tenant_id

from .schemas import (
    DocumentStatus,
    EmbeddingModel,
    IndexDocumentRequest,
    IndexedDocument,
    IndexStatus,
    IndexStats,
    RAGConfig,
)

# Simulated storage for demo - in production, use persistent storage
_tenant_configs: dict[int, RAGConfig] = {}
_tenant_indexes: dict[int, dict[str, IndexedDocument]] = {}


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


def get_tenant_config(tenant_id: int) -> RAGConfig:
    """Get or create tenant configuration"""
    if tenant_id not in _tenant_configs:
        _tenant_configs[tenant_id] = cast(Any, RAGConfig)()  # TODO(TYPE): replace Any with concrete type
    return _tenant_configs[tenant_id]


def save_tenant_config(tenant_id: int, config: RAGConfig) -> None:
    """Save tenant configuration"""
    _tenant_configs[tenant_id] = config


def get_tenant_index(tenant_id: int) -> dict[str, IndexedDocument]:
    """Get or create tenant index"""
    if tenant_id not in _tenant_indexes:
        _tenant_indexes[tenant_id] = {}
    return _tenant_indexes[tenant_id]


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
        computed_status = IndexStatus.BUILDING
    elif failed_count > total_docs * 0.1:  # More than 10% failed
        computed_status = IndexStatus.DEGRADED
    elif failed_count > 0:
        computed_status = IndexStatus.DEGRADED
    elif indexed_count == total_docs:
        computed_status = IndexStatus.HEALTHY
    else:
        computed_status = IndexStatus.HEALTHY

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
        status=computed_status,
        last_updated=last_updated,
        embedding_model=config.embedding_model.value,
    )


def simulate_document_indexing(request: IndexDocumentRequest) -> IndexedDocument:
    """Simulate document indexing (demo)"""
    doc_id = "doc_%s" % uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc)

    # Simulate content analysis
    content = request.content or "[Content from: %s]" % request.source
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
