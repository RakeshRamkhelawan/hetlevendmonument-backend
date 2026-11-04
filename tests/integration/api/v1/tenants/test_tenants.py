"""
Integration tests for Tenant CRUD endpoints.

Ported from tests/unit/temp_disabled/api/v1/test_tenants.py.
Uses real AsyncClient + seeded DB via integration conftest fixtures.
"""

import uuid

import pytest
from fastapi import status
from httpx import AsyncClient

from src.core.shared.tenant_instellingen import BEHEERDE_INSTELLINGEN


@pytest.mark.asyncio
@pytest.mark.integration
class TestTenantCRUD:
    """CRUD happy/unhappy path tests via HTTP (superuser)."""

    async def test_create_tenant_success(self, async_client: AsyncClient, admin_token: str) -> None:
        unique = str(uuid.uuid4())[:8]
        response = await async_client.post(
            "/api/v1/tenants/",
            json={
                "name": f"Test Tenant {unique}",
                "slug": f"test-tenant-{unique}",
                "domain": f"test-{unique}.example.com",
                "settings": {"theme": "dark"},
                "max_users": 50,
                "max_agents": 100,
                "max_storage_gb": 10,
                "subscription_tier": "pro",
            },
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        assert data["name"] == f"Test Tenant {unique}"
        assert data["slug"] == f"test-tenant-{unique}"
        assert data["is_active"] is True
        assert "id" in data

    async def test_create_tenant_duplicate_slug(
        self, async_client: AsyncClient, admin_token: str
    ) -> None:
        unique = str(uuid.uuid4())[:8]
        slug = f"duplicate-slug-{unique}"
        await async_client.post(
            "/api/v1/tenants/",
            json={"name": f"First Tenant {unique}", "slug": slug},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        response = await async_client.post(
            "/api/v1/tenants/",
            json={"name": f"Second Tenant {unique}", "slug": slug},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "already exists" in response.json()["detail"]

    async def test_list_tenants_pagination(
        self, async_client: AsyncClient, admin_token: str
    ) -> None:
        response = await async_client.get(
            "/api/v1/tenants/?skip=0&limit=10",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "data" in data
        assert "total" in data
        assert "page" in data
        assert "per_page" in data

    async def test_get_tenant_by_id(self, async_client: AsyncClient, admin_token: str) -> None:
        unique = str(uuid.uuid4())[:8]
        create_resp = await async_client.post(
            "/api/v1/tenants/",
            json={"name": f"Get Test {unique}", "slug": f"get-test-{unique}"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        tenant_id = create_resp.json()["id"]

        response = await async_client.get(
            f"/api/v1/tenants/{tenant_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["id"] == tenant_id
        assert data["name"] == f"Get Test {unique}"

    async def test_get_tenant_not_found(self, async_client: AsyncClient, admin_token: str) -> None:
        response = await async_client.get(
            "/api/v1/tenants/99999",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_update_tenant(self, async_client: AsyncClient, admin_token: str) -> None:
        unique = str(uuid.uuid4())[:8]
        create_resp = await async_client.post(
            "/api/v1/tenants/",
            json={"name": f"Update Test {unique}", "slug": f"update-test-{unique}"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        tenant_id = create_resp.json()["id"]
        # Sinds 12bfbc96 (2026-10-20) laat een algemene wijziging van `settings` de beheerde sleutels (vier ogen,
        # escalatietermijn, taalmodelkeuze) staan; die hebben een eigen route. De standaardwaarden kwamen met
        # 0cb9a41c. Verwacht is dus: precies die sleutels zoals bij het aanmaken, plus wat meegegeven is.
        bij_aanmaken = create_resp.json().get("settings") or {}
        behouden = {k: v for k, v in bij_aanmaken.items() if k in BEHEERDE_INSTELLINGEN}

        response = await async_client.put(
            f"/api/v1/tenants/{tenant_id}",
            json={"name": "Updated Name", "settings": {"key": "value"}},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["settings"] == {**behouden, "key": "value"}

    async def test_delete_tenant_soft_delete(
        self, async_client: AsyncClient, admin_token: str
    ) -> None:
        unique = str(uuid.uuid4())[:8]
        create_resp = await async_client.post(
            "/api/v1/tenants/",
            json={"name": f"Delete Test {unique}", "slug": f"delete-test-{unique}"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        tenant_id = create_resp.json()["id"]

        response = await async_client.delete(
            f"/api/v1/tenants/{tenant_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == status.HTTP_204_NO_CONTENT

        get_resp = await async_client.get(
            f"/api/v1/tenants/{tenant_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert get_resp.json()["is_active"] is False


@pytest.mark.asyncio
@pytest.mark.integration
class TestTenantPermissions:
    """Permission boundary tests (regular user vs superuser)."""

    async def test_non_superuser_cannot_create(
        self, async_client: AsyncClient, normal_user_token: str
    ) -> None:
        response = await async_client.post(
            "/api/v1/tenants/",
            json={"name": "Unauthorized", "slug": "unauthorized"},
            headers={"Authorization": f"Bearer {normal_user_token}"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_user_can_only_see_own_tenant(
        self,
        async_client: AsyncClient,
        normal_user_token: str,
        test_user: dict,
    ) -> None:
        response = await async_client.get(
            f"/api/v1/tenants/{test_user['tenant_id']}",
            headers={"Authorization": f"Bearer {normal_user_token}"},
        )
        assert response.status_code == status.HTTP_200_OK

    async def test_user_cannot_access_other_tenant(
        self, async_client: AsyncClient, normal_user_token: str
    ) -> None:
        response = await async_client.get(
            "/api/v1/tenants/99999",
            headers={"Authorization": f"Bearer {normal_user_token}"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    async def test_non_superuser_cannot_delete(
        self, async_client: AsyncClient, normal_user_token: str, test_user: dict
    ) -> None:
        response = await async_client.delete(
            f"/api/v1/tenants/{test_user['tenant_id']}",
            headers={"Authorization": f"Bearer {normal_user_token}"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
