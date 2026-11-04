"""Unit tests for get_audit_logs query function."""

from unittest.mock import AsyncMock, MagicMock
import pytest

from src.core.middleware.audit_middleware import get_audit_logs, RequestAuditLog


@pytest.mark.asyncio
async def test_get_audit_logs_builds_and_executes_query() -> None:
    mock_db = AsyncMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [
        RequestAuditLog(
            id=1,
            request_id="req-1",
            tenant_id="tenant-1",
            user_id=42,
            action="login",
            method="POST",
            path="/auth/login",
            status_code=200,
            response_time_ms=15,
        )
    ]
    mock_result = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    mock_db.execute.return_value = mock_result

    logs = await get_audit_logs(
        db=mock_db,
        tenant_id="tenant-1",
        user_id=42,
        action="login",
        limit=50,
    )

    assert len(logs) == 1
    assert logs[0]["request_id"] == "req-1"
    assert logs[0]["user_id"] == 42
    assert "user_email" not in logs[0]
    mock_db.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_audit_logs_raises_on_missing_tenant() -> None:
    mock_db = AsyncMock()
    with pytest.raises(ValueError, match="tenant_id is strictly required"):
        await get_audit_logs(db=mock_db, tenant_id="")
