"""Unit tests for tenants routers (AUDIT-DB-01)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.core.api.v1.tenants.dependencies import TenantService
from src.core.api.v1.tenants.tenants_detail_router import delete_tenant, get_tenant, update_tenant
from src.core.api.v1.tenants.tenants_list_router import create_tenant


@pytest.fixture
def mock_service() -> AsyncMock:
    svc = AsyncMock(spec=TenantService)
    svc.db = MagicMock()
    return svc


@pytest.fixture
def mock_superuser() -> MagicMock:
    user = MagicMock()
    user.is_superuser = True
    user.tenant_id = 1
    user.id = 101
    return user


@pytest.fixture
def mock_regular_user() -> MagicMock:
    user = MagicMock()
    user.is_superuser = False
    user.tenant_id = 2
    user.id = 102
    return user


@pytest.mark.unit
class TestTenantsListRouter:
    async def test_create_tenant_rejects_non_superuser(
        self, mock_service: AsyncMock, mock_regular_user: MagicMock
    ) -> None:
        from src.core.api.v1.tenants.schemas import TenantCreate

        data = TenantCreate(name="Acme", slug="acme")
        with pytest.raises(HTTPException) as exc_info:
            await create_tenant(data=data, service=mock_service, current_user=mock_regular_user)

        assert exc_info.value.status_code == 403
        mock_service.create_tenant.assert_not_awaited()

    async def test_create_tenant_success_for_superuser(
        self, mock_service: AsyncMock, mock_superuser: MagicMock
    ) -> None:
        from src.core.api.v1.tenants.schemas import TenantCreate, TenantResponse

        mock_response = MagicMock(spec=TenantResponse)
        mock_response.id = 42
        mock_response.name = "Acme"
        mock_response.slug = "acme"
        mock_service.create_tenant.return_value = mock_response

        with patch(
            "src.core.api.v1.tenants.tenants_list_router.audit_service.log_action"
        ) as mock_log:
            data = TenantCreate(name="Acme", slug="acme")
            result = await create_tenant(
                data=data, service=mock_service, current_user=mock_superuser
            )

        assert result.id == 42
        mock_service.create_tenant.assert_awaited_once_with(data)
        mock_log.assert_awaited_once()


@pytest.mark.unit
class TestTenantsDetailRouter:
    async def test_get_tenant_rejects_other_tenant(
        self, mock_service: AsyncMock, mock_regular_user: MagicMock
    ) -> None:
        with pytest.raises(HTTPException) as exc_info:
            await get_tenant(tenant_id=99, service=mock_service, current_user=mock_regular_user)

        assert exc_info.value.status_code == 403
        mock_service.get_tenant.assert_not_awaited()

    async def test_delete_tenant_invalidates_cache(
        self,
        mock_service: AsyncMock,
        mock_superuser: MagicMock,
    ) -> None:
        from src.core.api.v1.tenants.dependencies import clear_tenant_cache

        mock_service.delete_tenant.return_value = True

        with patch(
            "src.core.api.v1.tenants.tenants_detail_router.clear_tenant_cache"
        ) as mock_clear:
            await delete_tenant(tenant_id=1, service=mock_service, current_user=mock_superuser)

        mock_service.delete_tenant.assert_awaited_once_with(1)
        mock_clear.assert_called_once_with(1)

    async def test_get_tenant_returns_service_result(
        self, mock_service: AsyncMock, mock_regular_user: MagicMock
    ) -> None:
        from src.core.api.v1.tenants.schemas import TenantResponse

        mock_response = MagicMock(spec=TenantResponse)
        mock_response.id = 2
        mock_service.get_tenant.return_value = mock_response

        result = await get_tenant(tenant_id=2, service=mock_service, current_user=mock_regular_user)

        assert result.id == 2
        mock_service.get_tenant.assert_awaited_once_with(2)

    async def test_get_tenant_not_found(
        self, mock_service: AsyncMock, mock_superuser: MagicMock
    ) -> None:
        mock_service.get_tenant.return_value = None

        with pytest.raises(HTTPException) as exc_info:
            await get_tenant(tenant_id=1, service=mock_service, current_user=mock_superuser)

        assert exc_info.value.status_code == 404

    async def test_update_tenant_logs_audit(
        self, mock_service: AsyncMock, mock_superuser: MagicMock
    ) -> None:
        from src.core.api.v1.tenants.schemas import TenantResponse, TenantUpdate

        mock_response = MagicMock(spec=TenantResponse)
        mock_response.id = 1
        mock_service.update_tenant.return_value = mock_response

        with patch(
            "src.core.api.v1.tenants.tenants_detail_router.audit_service.log_action"
        ) as mock_log:
            data = TenantUpdate(name="New Name")
            result = await update_tenant(
                tenant_id=1, data=data, service=mock_service, current_user=mock_superuser
            )

        assert result.id == 1
        mock_service.update_tenant.assert_awaited_once_with(1, data)
        mock_log.assert_awaited_once()

    async def test_delete_tenant_logs_audit(
        self, mock_service: AsyncMock, mock_superuser: MagicMock
    ) -> None:
        mock_service.delete_tenant.return_value = True

        with (
            patch(
                "src.core.api.v1.tenants.tenants_detail_router.audit_service.log_action"
            ) as mock_log,
            patch("src.core.api.v1.tenants.tenants_detail_router.clear_tenant_cache") as mock_clear,
        ):
            await delete_tenant(tenant_id=1, service=mock_service, current_user=mock_superuser)

        mock_service.delete_tenant.assert_awaited_once_with(1)
        mock_log.assert_awaited_once()
        mock_clear.assert_called_once_with(1)
