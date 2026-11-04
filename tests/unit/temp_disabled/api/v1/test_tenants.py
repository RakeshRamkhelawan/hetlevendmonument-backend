"""
Unit tests for Tenant CRUD endpoints (P5.1)
"""

import pytest
from fastapi import status
from fastapi.testclient import TestClient
from httpx import AsyncClient


@pytest.mark.asyncio
class TestTenantCRUD:
    """Test suite for Tenant CRUD operations."""

    async def test_create_tenant_success(self, async_client: AsyncClient, admin_token: str):
        """Happy path: Create a new tenant."""
        import uuid
        import time

        unique = f"unit-test-{int(time.time())}-{str(uuid.uuid4())[:8]}"
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

    async def test_create_tenant_duplicate_slug(self, async_client: AsyncClient, admin_token: str):
        """Unhappy path: Create tenant with duplicate slug."""
        import uuid
        unique = str(uuid.uuid4())[:8]
        slug = f"duplicate-slug-{unique}"
        # Create first tenant
        await async_client.post(
            "/api/v1/tenants/",
            json={"name": f"First Tenant {unique}", "slug": slug},
            headers={"Authorization": f"Bearer {admin_token}"},
        )

        # Try to create second with same slug
        response = await async_client.post(
            "/api/v1/tenants/",
            json={"name": f"Second Tenant {unique}", "slug": slug},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "already exists" in response.json()["detail"]

    async def test_list_tenants_pagination(self, async_client: AsyncClient, admin_token: str):
        """Happy path: List tenants with pagination."""
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

    async def test_get_tenant_by_id(self, async_client: AsyncClient, admin_token: str):
        """Happy path: Get tenant by ID."""
        import uuid
        unique = str(uuid.uuid4())[:8]
        # Create tenant first
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

    async def test_get_tenant_not_found(self, async_client: AsyncClient, admin_token: str):
        """Unhappy path: Get non-existent tenant."""
        response = await async_client.get(
            "/api/v1/tenants/99999",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    async def test_update_tenant(self, async_client: AsyncClient, admin_token: str):
        """Happy path: Update tenant."""
        import uuid
        unique = str(uuid.uuid4())[:8]
        # Create tenant first
        create_resp = await async_client.post(
            "/api/v1/tenants/",
            json={"name": f"Update Test {unique}", "slug": f"update-test-{unique}"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        tenant_id = create_resp.json()["id"]

        response = await async_client.put(
            f"/api/v1/tenants/{tenant_id}",
            json={"name": "Updated Name", "settings": {"key": "value"}},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["name"] == "Updated Name"
        assert data["settings"] == {"key": "value"}

    async def test_delete_tenant_soft_delete(self, async_client: AsyncClient, admin_token: str):
        """Happy path: Soft delete tenant."""
        import uuid
        unique = str(uuid.uuid4())[:8]
        # Create tenant first
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

        # Verify tenant is deactivated
        get_resp = await async_client.get(
            f"/api/v1/tenants/{tenant_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert get_resp.json()["is_active"] is False


class TestTenantPermissions:
    """Test suite for Tenant permission checks."""

    def test_non_superuser_cannot_create(self, client_no_bypass: TestClient, test_token: str):
        """Unhappy path: Regular user cannot create tenants."""
        response = client_no_bypass.post(
            "/api/v1/tenants/",
            json={"name": "Unauthorized", "slug": "unauthorized"},
            headers={"Authorization": f"Bearer {test_token}"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_user_can_only_see_own_tenant(
        self, client_no_bypass: TestClient, test_token: str, test_user
    ):
        """Happy path: User can see their own tenant."""
        response = client_no_bypass.get(
            f"/api/v1/tenants/{test_user.tenant_id}",
            headers={"Authorization": f"Bearer {test_token}"},
        )
        assert response.status_code == status.HTTP_200_OK

    def test_user_cannot_access_other_tenant(self, client_no_bypass: TestClient, test_token: str):
        """Unhappy path: User cannot access other tenants."""
        response = client_no_bypass.get(
            "/api/v1/tenants/99999",  # Different tenant ID
            headers={"Authorization": f"Bearer {test_token}"},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
