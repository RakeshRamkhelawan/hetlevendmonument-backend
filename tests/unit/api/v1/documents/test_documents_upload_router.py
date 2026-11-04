import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException, UploadFile

from src.core.api.v1.documents.upload_router import upload_router, upload_document
from src.core.api.v1.documents.dependencies import User


def test_routes_registered() -> None:
    paths = [r.path for r in upload_router.routes]
    assert "/upload" in paths


@pytest.mark.asyncio
async def test_upload_document_tenant_mismatch_forbidden() -> None:
    user = MagicMock(spec=User)
    user.tenant_id = 100

    mock_file = AsyncMock(spec=UploadFile)

    with pytest.raises(HTTPException) as exc_info:
        await upload_document(
            file=mock_file,
            db=AsyncMock(),
            tenant_id=200,  # Mismatch!
            current_user=user,
        )
    assert exc_info.value.status_code == 403
    assert "Tenant mismatch" in exc_info.value.detail


@pytest.mark.asyncio
async def test_upload_document_unsupported_type_raises_400() -> None:
    user = MagicMock(spec=User)
    user.tenant_id = 100

    mock_file = AsyncMock(spec=UploadFile)
    mock_file.read.return_value = b"binary exe data"
    mock_file.content_type = "application/x-msdownload"

    with pytest.raises(HTTPException) as exc_info:
        await upload_document(
            file=mock_file,
            db=AsyncMock(),
            tenant_id=100,
            current_user=user,
        )
    assert exc_info.value.status_code == 400
    assert "File type 'application/x-msdownload' is not allowed" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_upload_document_success() -> None:
    user = MagicMock(spec=User)
    user.id = 42
    user.tenant_id = 100

    mock_file = AsyncMock(spec=UploadFile)
    mock_file.read.return_value = b"Hello, PDF content"
    mock_file.content_type = "text/plain"
    mock_file.filename = "report.txt"

    session = AsyncMock()
    def fake_refresh(obj):
        obj.id = 999
    session.refresh.side_effect = fake_refresh

    with patch("src.core.api.v1.documents.upload_router.aiofiles.open") as mock_open:
        mock_file_context = AsyncMock()
        mock_open.return_value.__aenter__.return_value = mock_file_context
        with patch("src.core.api.v1.documents.upload_router.audit_service.log_action", new_callable=AsyncMock):
            resp = await upload_document(
                file=mock_file,
                db=session,
                tenant_id=100,
                current_user=user,
            )
            assert resp["success"] is True
            assert resp["data"]["id"] == 999
            assert resp["data"]["filename"] == "report.txt"
            assert resp["data"]["mime_type"] == "text/plain"
            assert resp["data"]["status"] == "processing"
