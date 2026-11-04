# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""Document search endpoint (ADR-033 Laag 1)."""

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.v1.documents.dependencies import (
    User,
    get_current_user,
    get_db,
    require_tenant_id,
)
from src.domains.documents.models import Document

logger = logging.getLogger(__name__)

search_router = APIRouter()


@search_router.get("/search")
async def search_documents(
    q: str = Query(..., min_length=1, max_length=200),
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(require_tenant_id),
    current_user: User = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Fulltext search documents by filename via PostgreSQL to_tsvector."""
    if current_user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch")

    stmt = (
        select(Document)
        .where(
            Document.tenant_id == tenant_id,
            Document.deleted_at.is_(None),
            func.to_tsvector("english", func.replace(Document.filename, "_", " ")).op("@@")(
                func.plainto_tsquery("english", q)
            ),
        )
        .order_by(Document.created_at.desc())
        .offset(offset)
        .limit(limit)
    )

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    result = await db.execute(stmt)
    docs = result.scalars().all()

    data = [
        {
            "id": d.id,
            "tenant_id": d.tenant_id,
            "filename": d.filename,
            "mime_type": d.mime_type,
            "file_size_bytes": d.file_size_bytes,
            "status": d.status,
            "version": d.version,
            "storage_backend": d.storage_backend,
            "checksum_sha256": d.checksum_sha256,
            "created_at": d.created_at.isoformat() if d.created_at else None,
            "updated_at": d.updated_at.isoformat() if d.updated_at else None,
        }
        for d in docs
    ]

    return {
        "success": True,
        "data": data,
        "query": q,
        "total": total,
        "limit": limit,
        "offset": offset,
    }
