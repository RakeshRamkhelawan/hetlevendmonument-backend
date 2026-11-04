# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""Document upload endpoint (ADR-033 Laag 1)."""

import hashlib
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiofiles
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.v1.documents.dependencies import (
    User,
    audit_service,
    get_current_user,
    get_db,
    require_tenant_id,
)
from src.core.shared.config import get_settings
from src.core.utils.best_effort import best_effort
from src.domains.documents.models import Document

logger = logging.getLogger(__name__)

upload_router = APIRouter()

_ALLOWED_MIME_TYPES = {
    "application/pdf",
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/json",
    "image/png",
    "image/jpeg",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


def secure_filename(name: str | None) -> str:
    """Sanitize a filename to prevent path traversal and unsafe chars."""
    if not name:
        return "unnamed"
    name = name.replace("\\", "_").replace("/", "_").replace("\x00", "")
    safe = ""
    for ch in name:
        if ch.isalnum() or ch in "._-":
            safe += ch
        else:
            safe += "_"
    return safe or "unnamed"


@upload_router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    tenant_id: int = Depends(require_tenant_id),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Upload a document file.

    Returns status="processing". Actual processing is done asynchronously.
    """
    settings = get_settings()
    max_size = getattr(settings, "max_upload_size_bytes", 50 * 1024 * 1024)
    storage_backend = os.getenv("STORAGE_BACKEND", getattr(settings, "storage_backend", "local"))
    upload_dir_root = Path(getattr(settings, "local_upload_dir", "/tmp/uploads"))

    if current_user.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant mismatch",
        )

    content = await file.read(max_size + 1)
    if len(content) > max_size:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="File too large",
        )

    mime_type = file.content_type or "application/octet-stream"
    if mime_type not in _ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "success": False,
                "error": {
                    "code": "UNSUPPORTED_FILE_TYPE",
                    "message": f"File type '{mime_type}' is not allowed",
                },
            },
        )

    if storage_backend != "local":
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail={
                "success": False,
                "error": {
                    "code": "STORAGE_NOT_CONFIGURED",
                    "message": f"Storage backend '{storage_backend}' not implemented",
                },
            },
        )

    checksum = hashlib.sha256(content).hexdigest()
    safe_name = secure_filename(file.filename)

    now = datetime.now(timezone.utc)
    doc = Document(
        tenant_id=tenant_id,
        uploaded_by=current_user.id,
        filename=safe_name,
        mime_type=mime_type,
        file_size_bytes=len(content),
        storage_backend=storage_backend,
        storage_path="",
        checksum_sha256=checksum,
        status="processing",
        created_at=now,
        updated_at=now,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    upload_dir = upload_dir_root / str(tenant_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = upload_dir / f"{doc.id}_{safe_name}"

    async with aiofiles.open(file_path, "wb") as f:
        await f.write(content)

    doc.storage_path = str(file_path)
    doc.updated_at = datetime.now(timezone.utc)
    await db.commit()

    async with best_effort("document upload audit", db_session=db):
        await audit_service.log_action(
            tenant_id=tenant_id,
            action="document.uploaded",
            resource=f"document:{doc.id}",
            user_id=current_user.id,
            details={"filename": safe_name, "size": len(content)},
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
            "storage_backend": doc.storage_backend,
            "checksum_sha256": doc.checksum_sha256,
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
        },
    }
