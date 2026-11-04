"""Tenant isolation integration tests for TenantService (AUDIT-DB-01)."""

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.container import TenantContext
from src.core.models.rbac_models import Tenant
from src.core.services.tenant_service import TenantService
from src.core.api.v1.tenants.schemas import TenantUpdate


@pytest.mark.integration
class TestTenantServiceIsolation:
    async def _create_tenant(
        self, db: AsyncSession, tenant_id: int, name: str, slug: str
    ) -> Tenant:
        tenant = Tenant(
            id=tenant_id,
            name=name,
            slug=slug,
            is_active=True,
            max_users=10,
            max_agents=50,
            max_storage_gb=5,
            subscription_tier="free",
            subscription_status="active",
            data_residency="global",
        )
        db.add(tenant)
        await db.commit()
        await db.refresh(tenant)
        return tenant

    async def test_regular_user_cannot_read_other_tenant(
        self, postgres_session: AsyncSession
    ) -> None:
        """Regular user (tenant A) cannot read tenant B data."""
        await self._create_tenant(postgres_session, 901, "Tenant A", "tenant-a-901")
        await self._create_tenant(postgres_session, 902, "Tenant B", "tenant-b-902")

        ctx = TenantContext(tenant_id=901, bypass_filter=False)
        svc = TenantService(db=postgres_session, tenant_context=ctx)

        with pytest.raises(HTTPException) as exc_info:
            await svc.get_tenant(tenant_id=902)

        assert exc_info.value.status_code == 403

    async def test_regular_user_cannot_update_other_tenant(
        self, postgres_session: AsyncSession
    ) -> None:
        """Regular user (tenant A) cannot update tenant B data."""
        await self._create_tenant(postgres_session, 903, "Tenant A", "tenant-a-903")
        await self._create_tenant(postgres_session, 904, "Tenant B", "tenant-b-904")

        ctx = TenantContext(tenant_id=903, bypass_filter=False)
        svc = TenantService(db=postgres_session, tenant_context=ctx)

        with pytest.raises(HTTPException) as exc_info:
            await svc.update_tenant(tenant_id=904, data=TenantUpdate(name="Hacked"))

        assert exc_info.value.status_code == 403

    async def test_superuser_can_read_any_tenant(self, postgres_session: AsyncSession) -> None:
        """Superuser (bypass_filter=True) can read any tenant."""
        await self._create_tenant(postgres_session, 905, "Tenant A", "tenant-a-905")
        await self._create_tenant(postgres_session, 906, "Tenant B", "tenant-b-906")

        ctx = TenantContext(tenant_id=905, bypass_filter=True)
        svc = TenantService(db=postgres_session, tenant_context=ctx)

        result = await svc.get_tenant(tenant_id=906)

        assert result is not None
        assert result.id == 906

    async def test_regular_user_stats_scoped_to_own_tenant(
        self, postgres_session: AsyncSession
    ) -> None:
        """Regular user cannot request statistics for another tenant."""
        await self._create_tenant(postgres_session, 907, "Tenant A", "tenant-a-907")
        await self._create_tenant(postgres_session, 908, "Tenant B", "tenant-b-908")

        ctx = TenantContext(tenant_id=907, bypass_filter=False)
        svc = TenantService(db=postgres_session, tenant_context=ctx)

        with pytest.raises(HTTPException) as exc_info:
            await svc.get_tenant_stats(tenant_id=908)

        assert exc_info.value.status_code == 403
