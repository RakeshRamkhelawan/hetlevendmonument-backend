# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""Document processing endpoints: process, status, versions (ADR-033 Laag 1)."""

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.v1.documents.dependencies import (
    User,
    audit_service,
    get_current_user,
    get_db,
    require_tenant_id,
)
from src.core.utils.best_effort import best_effort
from src.domains.documents.models import Document, DocumentVersion

logger = logging.getLogger(__name__)

processing_router = APIRouter()


@processing_router.post("/{doc_id}/process")
async def process_document(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(require_tenant_id),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Trigger async document processing via Dramatiq."""
    if current_user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch")

    stmt = select(Document).where(
        Document.id == doc_id,
        Document.tenant_id == tenant_id,
        Document.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "success": False,
                "error": {"code": "NOT_FOUND", "message": "Document not found"},
            },
        )

    vorige_status = doc.status
    doc.status = "processing"
    doc.updated_at = datetime.now(timezone.utc)
    await db.commit()

    from src.workers.actors import process_document_async

    try:
        process_document_async.send(str(doc.id), tenant_id)
    except Exception as exc:
        # Redis weg: de opdracht staat nergens, dus het document hoort niet voor altijd op "processing" te
        # blijven staan (ADR-036 OP-13). Terugzetten en een duidelijke fout, geen stille 500.
        logger.error(
            "Document %s niet verstuurd naar de werker: %s: %s",
            doc.id,
            type(exc).__name__,
            exc,
            exc_info=True,
            extra={"tenant_id": tenant_id},
        )
        doc.status = vorige_status
        doc.updated_at = datetime.now(timezone.utc)
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "success": False,
                "error": {
                    "code": "WACHTRIJ_NIET_BESCHIKBAAR",
                    "message": (
                        "De verwerking van het document is niet gestart: de opdracht kon niet naar "
                        "de werker. Probeer het over enkele minuten opnieuw."
                    ),
                },
            },
        ) from exc

    async with best_effort("document process audit", db_session=db):
        await audit_service.log_action(
            tenant_id=tenant_id,
            action="document.processing_triggered",
            resource=f"document:{doc.id}",
            user_id=current_user.id,
            details={"status": "processing"},
            session=db,
        )

    return {
        "success": True,
        "data": {
            "id": doc.id,
            "status": "processing",
        },
    }


@processing_router.get("/{doc_id}/status")
async def get_document_status(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(require_tenant_id),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get processing status of a document."""
    if current_user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch")

    stmt = select(Document).where(
        Document.id == doc_id,
        Document.tenant_id == tenant_id,
        Document.deleted_at.is_(None),
    )
    result = await db.execute(stmt)
    doc = result.scalar_one_or_none()

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "success": False,
                "error": {"code": "NOT_FOUND", "message": "Document not found"},
            },
        )

    return {
        "success": True,
        "data": {
            "id": doc.id,
            "status": doc.status,
            "version": doc.version,
            "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
        },
    }


@processing_router.get("/{doc_id}/versions")
async def get_document_versions(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(require_tenant_id),
    current_user: User = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """List version history snapshots for a document."""
    if current_user.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Tenant mismatch")

    doc_stmt = select(Document).where(
        Document.id == doc_id,
        Document.tenant_id == tenant_id,
        Document.deleted_at.is_(None),
    )
    doc_result = await db.execute(doc_stmt)
    doc = doc_result.scalar_one_or_none()

    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "success": False,
                "error": {"code": "NOT_FOUND", "message": "Document not found"},
            },
        )

    stmt = (
        select(DocumentVersion)
        .where(
            DocumentVersion.document_id == doc_id,
            DocumentVersion.tenant_id == tenant_id,
        )
        .order_by(DocumentVersion.created_at.desc())
        .offset(offset)
        .limit(limit)
    )

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    result = await db.execute(stmt)
    versions = result.scalars().all()

    data = [
        {
            "id": v.id,
            "document_id": v.document_id,
            "version": v.version,
            "snapshot": v.snapshot,
            "created_at": v.created_at.isoformat() if v.created_at else None,
        }
        for v in versions
    ]

    return {
        "success": True,
        "data": data,
        "total": total,
        "limit": limit,
        "offset": offset,
    }
