# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""
Memory index sub-router -- document index GET, POST, DELETE.

Migrated from src/core/api/memory_endpoints.py (SP-API-003 Dag 5).
"""

import logging
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.dependencies import get_db
from src.core.auth.api_deps import require_scopes, OAuth2Scope

from .dependencies import (
    calculate_index_stats,
    get_tenant,
    get_tenant_config,
    get_tenant_index,
    get_user_id,
    simulate_document_indexing,
)
from .schemas import (
    DeleteIndexResponse,
    DocumentStatus,
    IndexDocumentRequest,
    IndexDocumentResponse,
    IndexResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


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
    current_user: dict[str, Any] = Depends(require_scopes(OAuth2Scope.WORKFLOWS_READ)),  # TODO(TYPE): replace Any with concrete type
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
        message="Index contains %d document(s) with %d chunks"
        % (stats.total_documents, stats.total_chunks),
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
    current_user: dict[str, Any] = Depends(require_scopes(OAuth2Scope.WORKFLOWS_WRITE)),  # TODO(TYPE): replace Any with concrete type
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
            detail="Document with source '%s' already exists. Use force_reindex=true to re-index."
            % request.source,
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
        message="Document indexed successfully with %d chunk(s)" % document.chunk_count,
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
    current_user: dict[str, Any] = Depends(require_scopes(OAuth2Scope.WORKFLOWS_WRITE)),  # TODO(TYPE): replace Any with concrete type
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
            message="Index cleared: %d document(s) removed" % deleted_docs,
            success=True,
        )

    if document_id:
        # Delete specific document
        if document_id not in index:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document %s not found in index" % document_id,
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
            message="Document %s deleted from index" % document_id,
            success=True,
        )

    # No action specified
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Specify document_id to delete a specific document or clear_all=true to clear index",
    )
