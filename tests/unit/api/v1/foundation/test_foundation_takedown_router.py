import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from contextlib import asynccontextmanager
from fastapi import HTTPException

from src.core.api.v1.foundation.takedown import router, create_takedown
from src.core.api.v1.foundation.schemas import TakedownCreateRequest
from src.core.models.foundation_content import PortalUser, PortalRole, FoundationContent, TakedownRequest, TakedownStatus


def test_routes_registered() -> None:
    paths = [r.path for r in router.routes]
    assert "/takedown" in paths


@pytest.mark.asyncio
async def test_create_takedown_user_wrong_tenant_forbidden() -> None:
    mock_tenant = MagicMock()
    mock_tenant.id = 100

    @asynccontextmanager
    async def fake_public_tenant_scope(slug, session):
        yield mock_tenant

    user = MagicMock(spec=PortalUser)
    user.tenant_id = 999  # Mismatch!

    req = MagicMock()
    data = TakedownCreateRequest(
        content_id=1,
        contact_email="test@example.com",
        reason="Copyright violation",
    )

    with patch("src.core.api.v1.foundation.takedown.public_tenant_scope", fake_public_tenant_scope):
        with pytest.raises(HTTPException) as exc_info:
            await create_takedown(
                tenantSlug="test-tenant",
                request=req,
                data=data,
                current_user=user,
                session=AsyncMock(),
                _check=None,
            )
        assert exc_info.value.status_code == 403
        assert "User does not belong to this tenant" in exc_info.value.detail


@pytest.mark.asyncio
async def test_create_takedown_content_not_found() -> None:
    mock_tenant = MagicMock()
    mock_tenant.id = 100

    @asynccontextmanager
    async def fake_public_tenant_scope(slug, session):
        yield mock_tenant

    user = MagicMock(spec=PortalUser)
    user.tenant_id = 100

    session = AsyncMock()
    scalar_mock = MagicMock()
    scalar_mock.scalar_one_or_none.return_value = None  # Content not found!
    session.execute.return_value = scalar_mock

    req = MagicMock()
    data = TakedownCreateRequest(
        content_id=999,
        contact_email="test@example.com",
        reason="Copyright violation",
    )

    with patch("src.core.api.v1.foundation.takedown.public_tenant_scope", fake_public_tenant_scope):
        with pytest.raises(HTTPException) as exc_info:
            await create_takedown(
                tenantSlug="test-tenant",
                request=req,
                data=data,
                current_user=user,
                session=session,
                _check=None,
            )
        assert exc_info.value.status_code == 404
        assert "Content not found" in exc_info.value.detail


@pytest.mark.asyncio
async def test_create_takedown_success() -> None:
    mock_tenant = MagicMock()
    mock_tenant.id = 100

    @asynccontextmanager
    async def fake_public_tenant_scope(slug, session):
        yield mock_tenant

    user = MagicMock(spec=PortalUser)
    user.id = 42
    user.tenant_id = 100
    user.display_name = "Alice"
    user.email = "alice@example.com"

    session = AsyncMock()
    content = MagicMock(spec=FoundationContent)
    content.id = 1
    content.tenant_id = 100
    scalar_mock = MagicMock()
    scalar_mock.scalar_one_or_none.return_value = content
    session.execute.return_value = scalar_mock

    # Session.refresh sets an id on the created takedown
    def fake_refresh(obj):
        obj.id = 12345
    session.refresh.side_effect = fake_refresh

    req = MagicMock()
    req.client.host = "127.0.0.1"
    data = TakedownCreateRequest(
        content_id=1,
        contact_email="alice@example.com",
        reason="Copyright violation",
    )

    with patch("src.core.api.v1.foundation.takedown.public_tenant_scope", fake_public_tenant_scope):
        with patch("src.core.api.v1.foundation.takedown.notification_service.notify_tenant", new_callable=AsyncMock) as mock_notify:
            with patch("src.core.api.v1.foundation.takedown.AuditService.log_event", new_callable=AsyncMock) as mock_audit:
                resp = await create_takedown(
                    tenantSlug="test-tenant",
                    request=req,
                    data=data,
                    current_user=user,
                    session=session,
                    _check=None,
                )
                assert resp["id"] == 12345
                assert resp["status"] == "pending"
                assert "Takedown request submitted successfully" in resp["message"]
