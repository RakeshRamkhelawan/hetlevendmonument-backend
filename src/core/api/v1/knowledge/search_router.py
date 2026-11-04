# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""
Knowledge search sub-router -- list, search, categories.

Migrated from src/core/api/knowledge_endpoints.py (SP-API-003 Dag 5).
"""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.dependencies import get_db
from src.core.auth.api_deps import UserResponse, get_current_user_dependency, require_scopes, OAuth2Scope
from src.core.knowledge.models import KnowledgeEntry
from src.core.middleware.tenant_context import get_current_tenant_id
from src.core.shared.production_logging import SafeLogger

from .schemas import (
    KnowledgeCategoriesResponse,
    KnowledgeListResponse,
    KnowledgeSearchRequest,
)

logger = SafeLogger(__name__)

router = APIRouter()


@router.get("/", response_model=KnowledgeListResponse)
async def list_knowledge(
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=100),
    type_filter: str | None = Query(default=None),
) -> KnowledgeListResponse:
    """
    List all knowledge entries with pagination and optional type filtering from database.
    Requires: AGENTS_READ
    """
    try:
        logger.info(
            "User %s listing knowledge entries (skip=%s, limit=%s, type=%s)",
            current_user.id,
            skip,
            limit,
            type_filter,
        )

        # Convert tenant_id to int if it's a string
        tenant_id_int = int(tenant_id) if isinstance(tenant_id, str) else tenant_id

        query = select(KnowledgeEntry).where(KnowledgeEntry.tenant_id == tenant_id_int)

        if type_filter:
            query = query.where(KnowledgeEntry.type == type_filter)

        query = query.order_by(KnowledgeEntry.created_at.desc())

        count_query = select(func.count(KnowledgeEntry.id)).where(
            KnowledgeEntry.tenant_id == tenant_id_int
        )
        if type_filter:
            count_query = count_query.where(KnowledgeEntry.type == type_filter)

        count_result = await db.execute(count_query)
        total = count_result.scalar() or 0

        query = query.offset(skip).limit(limit)

        result = await db.execute(query)
        entries = result.scalars().all()

        entries_data = [
            {
                "id": entry.id,
                "content": (
                    entry.content[:200] + "..." if len(entry.content) > 200 else entry.content
                ),
                "type": entry.type,
                "confidence_score": entry.confidence_score,
                "metadata": entry.entry_metadata,
                "created_at": entry.created_at.isoformat() if entry.created_at else None,
                "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
            }
            for entry in entries
        ]

        return KnowledgeListResponse(
            entries=entries_data,
            total=total,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as e:
        logger.exception("Error listing knowledge: %s: %s", type(e).__name__, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list knowledge",
        )


@router.post("/search", response_model=KnowledgeListResponse)
async def search_knowledge(
    request: KnowledgeSearchRequest,
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
) -> KnowledgeListResponse:
    """
    Search knowledge base with query and filters using full-text search.
    Requires: AGENTS_READ
    """
    try:
        logger.info("User %s searching knowledge: %s", current_user.id, request.query)

        tenant_id_int = int(tenant_id) if isinstance(tenant_id, str) else tenant_id

        search_pattern = "%%%s%%" % request.query
        query = select(KnowledgeEntry).where(
            and_(
                KnowledgeEntry.tenant_id == tenant_id_int,
                KnowledgeEntry.content.ilike(search_pattern),
            )
        )

        if request.type_filter:
            query = query.where(KnowledgeEntry.type == request.type_filter)

        if request.min_confidence is not None:
            query = query.where(KnowledgeEntry.confidence_score >= request.min_confidence)

        query = query.order_by(KnowledgeEntry.confidence_score.desc())

        limit = request.limit or 10
        query = query.limit(limit)

        result = await db.execute(query)
        entries = result.scalars().all()

        entries_data = [
            {
                "id": entry.id,
                "content": (
                    entry.content[:200] + "..." if len(entry.content) > 200 else entry.content
                ),
                "type": entry.type,
                "confidence_score": entry.confidence_score,
                "metadata": entry.entry_metadata,
                "created_at": entry.created_at.isoformat() if entry.created_at else None,
                "updated_at": entry.updated_at.isoformat() if entry.updated_at else None,
            }
            for entry in entries
        ]

        return KnowledgeListResponse(
            entries=entries_data,
            total=len(entries_data),
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as e:
        logger.exception("Error searching knowledge: %s: %s", type(e).__name__, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to search knowledge",
        )


@router.get("/categories", response_model=KnowledgeCategoriesResponse)
async def get_knowledge_categories(
    current_user: UserResponse = Depends(get_current_user_dependency),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
    db: AsyncSession = Depends(get_db),
    tenant_id: str = Depends(get_current_tenant_id),
) -> KnowledgeCategoriesResponse:
    """
    Get all knowledge categories/types with entry counts from database.
    Requires: AGENTS_READ
    """
    try:
        logger.info("User %s requesting knowledge categories", current_user.id)

        tenant_id_int = int(tenant_id) if isinstance(tenant_id, str) else tenant_id

        query = (
            select(KnowledgeEntry.type, func.count(KnowledgeEntry.id).label("count"))
            .where(KnowledgeEntry.tenant_id == tenant_id_int)
            .group_by(KnowledgeEntry.type)
        )

        result = await db.execute(query)
        rows = result.all()

        categories: list[str] = []
        count_per_category: dict[str, int] = {}
        for row in rows:
            category_type, count = row
            if category_type:
                categories.append(category_type)
                count_per_category[category_type] = count

        return KnowledgeCategoriesResponse(
            categories=sorted(categories),
            count_per_category=count_per_category,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
    except Exception as e:
        logger.exception("Error getting knowledge categories: %s: %s", type(e).__name__, e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get categories",
        )
