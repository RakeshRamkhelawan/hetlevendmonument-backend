# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""
Memory config sub-router -- RAG configuration GET and PUT.

Migrated from src/core/api/memory_endpoints.py (SP-API-003 Dag 5).
"""

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Body, Depends
from fastapi import HTTPException
from fastapi import status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.dependencies import get_db, require_admin_user
from src.core.auth.api_deps import require_scopes, OAuth2Scope, UserResponse

from .dependencies import (
    get_tenant,
    get_tenant_config,
    get_user_id,
    save_tenant_config,
)
from .schemas import RAGConfig, RAGConfigResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/config",
    response_model=RAGConfigResponse,
    summary="Get RAG configuration",
    description="Retrieves the current RAG configuration for the tenant.",
)
async def get_config(
    db: AsyncSession = Depends(get_db),
    tenant_id: int | None = Depends(get_tenant),
    current_user: dict[str, Any] = Depends(require_scopes(OAuth2Scope.WORKFLOWS_READ)),  # TODO(TYPE): replace Any with concrete type
    _beheerder: UserResponse = Depends(require_admin_user),  # rolcontrole: beheerder (403)
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
    current_user: dict[str, Any] = Depends(require_scopes(OAuth2Scope.WORKFLOWS_WRITE)),  # TODO(TYPE): replace Any with concrete type
    _beheerder: UserResponse = Depends(require_admin_user),  # rolcontrole: beheerder (403)
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
