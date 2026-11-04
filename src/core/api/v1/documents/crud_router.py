# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""Document CRUD endpoints: list, get, update, delete (ADR-033 Laag 1)."""

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
from src.core.api.v1.documents.schemas import DocumentUpdateRequest
from src.core.utils.best_effort import best_effort
from src.domains.documents.models import Document

logger = logging.getLogger(__name__)

crud_router = APIRouter()


@crud_router.get("/")
async def list_documents(
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(require_tenant_id),
    current_user: User = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    status: str | None = Query(None, max_length=50),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """List documents for the current tenant."""
    if current_user.tenant_id != tenant_id:
        raise HTTPException(
            status_code=403,
            detail="Tenant mismatch",
        )

    stmt = select(Document).where(
        Document.tenant_id == tenant_id,
        Document.deleted_at.is_(None),
    )
    if status:
        stmt = stmt.where(Document.status == status)

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    stmt = stmt.offset(offset).limit(limit).order_by(Document.created_at.desc())
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
            "deleted_at": d.deleted_at.isoformat() if d.deleted_at else None,
            "created_at": d.created_at.isoformat() if d.created_at else None,
            "updated_at": d.updated_at.isoformat() if d.updated_at else None,
        }
        for d in docs
    ]

    return {
        "success": True,
        "data": data,
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@crud_router.get("/{doc_id}")
async def get_document(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(require_tenant_id),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get a single document by ID."""
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
            "tenant_id": doc.tenant_id,
            "filename": doc.filename,
            "mime_type": doc.mime_type,
            "file_size_bytes": doc.file_size_bytes,
            "status": doc.status,
            "version": doc.version,
            "storage_backend": doc.storage_backend,
            "storage_path": doc.storage_path,
            "checksum_sha256": doc.checksum_sha256,
            "content": doc.content,
            "deleted_at": doc.deleted_at.isoformat() if doc.deleted_at else None,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
            "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
        },
    }


@crud_router.put("/{doc_id}")
async def update_document(
    doc_id: int,
    payload: DocumentUpdateRequest,
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(require_tenant_id),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Update document metadata. Bumps version on every update."""
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

    if payload.filename is not None:
        from src.core.api.v1.documents.upload_router import secure_filename

        doc.filename = secure_filename(payload.filename)
    if payload.status is not None:
        doc.status = payload.status
    if payload.metadata_ is not None:
        doc.metadata_ = payload.metadata_

    doc.version += 1
    doc.updated_at = datetime.now(timezone.utc)

    await db.commit()
    await db.refresh(doc)

    async with best_effort("document update audit", db_session=db):
        await audit_service.log_action(
            tenant_id=tenant_id,
            action="document.updated",
            resource=f"document:{doc.id}",
            user_id=current_user.id,
            details={
                "version": doc.version,
                "fields_updated": list(payload.model_dump(exclude_unset=True).keys()),
            },
            session=db,
        )

    return {
        "success": True,
        "data": {
            "id": doc.id,
            "tenant_id": doc.tenant_id,
            "filename": doc.filename,
            "mime_type": doc.mime_type,
            "file_size_bytes": doc.file_size_bytes,
            "status": doc.status,
            "version": doc.version,
            "storage_backend": doc.storage_backend,
            "checksum_sha256": doc.checksum_sha256,
            "updated_at": doc.updated_at.isoformat() if doc.updated_at else None,
        },
    }


@crud_router.delete("/{doc_id}")
async def delete_document(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(require_tenant_id),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Soft-delete a document."""
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

    doc.deleted_at = datetime.now(timezone.utc)
    doc.is_deleted = True
    doc.updated_at = datetime.now(timezone.utc)
    await db.commit()

    async with best_effort("document delete audit", db_session=db):
        await audit_service.log_action(
            tenant_id=tenant_id,
            action="document.deleted",
            resource=f"document:{doc.id}",
            user_id=current_user.id,
            details={"soft_deleted": True},
            session=db,
        )

    return {
        "success": True,
        "data": {
            "id": doc.id,
            "deleted_at": doc.deleted_at.isoformat() if doc.deleted_at else None,  # pyright: ignore[reportOptionalMemberAccess]
        },
    }
