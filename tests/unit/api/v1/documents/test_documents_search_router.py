"""Unit tests for documents search router (src/core/api/v1/documents/search_router.py).

Covers:
- GET /search
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute

from src.core.api.v1.documents.search_router import (
    search_documents,
    search_router,
)


class DummyUser:
    def __init__(self, id: int = 1, tenant_id: int = 42) -> None:
        self.id = id
        self.tenant_id = tenant_id


class DummyDocument:
    def __init__(self) -> None:
        self.id = 101
        self.tenant_id = 42
        self.filename = "report_2026.pdf"
        self.mime_type = "application/pdf"
        self.file_size_bytes = 10240
        self.status = "processed"
        self.version = 1
        self.storage_backend = "s3"
        self.checksum_sha256 = "dummy_checksum"
        self.created_at = datetime(2026, 9, 26, 12, 0, 0, tzinfo=timezone.utc)
        self.updated_at = None


def test_routes_registered() -> None:
    routes = [r for r in search_router.routes if isinstance(r, APIRoute)]
    paths = {r.path for r in routes}
    assert "/search" in paths


@pytest.mark.asyncio
async def test_search_documents_tenant_mismatch_raises_403() -> None:
    user = DummyUser(id=1, tenant_id=42)
    db = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await search_documents(
            q="report",
            db=db,
            tenant_id=99,  # Mismatch with user.tenant_id=42
            current_user=user,
        )
    assert exc_info.value.status_code == 403
    assert "Tenant mismatch" in exc_info.value.detail


@pytest.mark.asyncio
async def test_search_documents_success() -> None:
    user = DummyUser(id=1, tenant_id=42)
    db = AsyncMock()

    mock_count = MagicMock()
    mock_count.scalar_one.return_value = 1

    mock_docs = MagicMock()
    mock_docs.scalars.return_value.all.return_value = [DummyDocument()]

    db.execute.side_effect = [mock_count, mock_docs]

    res = await search_documents(
        q="report",
        db=db,
        tenant_id=42,
        current_user=user,
        limit=20,
        offset=0,
    )
    assert res["success"] is True
    assert res["total"] == 1
    assert len(res["data"]) == 1
    assert res["data"][0]["filename"] == "report_2026.pdf"
    assert res["data"][0]["tenant_id"] == 42
