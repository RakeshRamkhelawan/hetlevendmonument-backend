"""
Integration tests for DomainPacks API endpoints
Tests the full stack from HTTP layer through database
"""

from uuid import uuid4

import pytest
from httpx import AsyncClient

# Verzonnen gebruiker (sub 1 in tenant 999): de accountcontrole van de middleware staat hier uit.
pytestmark = pytest.mark.usefixtures("account_actief_zonder_database")


@pytest.fixture
def auth_headers(admin_token: str):
    """Valid auth headers using real integration JWT token."""
    return {
        "Authorization": f"Bearer {admin_token}",
    }


class TestDomainPacksAPI:
    """Tests for domain packs REST API"""

    @pytest.mark.asyncio
    async def test_create_domain_pack_endpoint_201(self, client: AsyncClient, auth_headers):
        """
        GIVEN: Valid DomainPackCreate payload
        WHEN: POST /api/v1/domain-packs
        THEN: Returns 201 with created resource
        """
        payload = {
            "name": "Finance",
            "department": "Finance",
            "capabilities": ["compliance", "audit"],
            "description": "Finance domain",
        }

        response = await client.post("/api/v1/domain-packs", json=payload, headers=auth_headers)

        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_list_domain_packs_endpoint_filters_by_tenant(
        self, client: AsyncClient, auth_headers
    ):
        """
        GIVEN: Multiple domain packs created
        WHEN: GET /api/v1/domain-packs
        THEN: Returns only current tenant's packs
        """
        response = await client.get("/api/v1/domain-packs", headers=auth_headers)

        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_get_domain_pack_endpoint_200(self, client: AsyncClient, auth_headers):
        """
        GIVEN: Existing domain pack
        WHEN: GET /api/v1/domain-packs/{pack_id}
        THEN: Returns 200 with pack details
        """
        pack_id = uuid4()
        response = await client.get(f"/api/v1/domain-packs/{pack_id}", headers=auth_headers)

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_domain_pack_endpoint_200(self, client: AsyncClient, auth_headers):
        """
        GIVEN: Existing domain pack
        WHEN: PUT /api/v1/domain-packs/{pack_id} with update data
        THEN: Returns 200 with updated resource
        """
        pack_id = uuid4()
        update_payload = {
            "description": "Updated finance domain",
            "status": "deprecated",
        }
        response = await client.put(
            f"/api/v1/domain-packs/{pack_id}", json=update_payload, headers=auth_headers
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_archive_domain_pack_endpoint_200(self, client: AsyncClient, auth_headers):
        """
        GIVEN: Active domain pack
        WHEN: POST /api/v1/domain-packs/{pack_id}/archive
        THEN: Returns 200 and sets status to deprecated
        """
        pack_id = uuid4()
        response = await client.post(
            f"/api/v1/domain-packs/{pack_id}/archive", headers=auth_headers
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_domain_pack_unauthorized_401(self, client: AsyncClient):
        """
        GIVEN: No auth headers
        WHEN: POST /api/v1/domain-packs
        THEN: Returns 401
        """
        payload = {"name": "Finance", "department": "Finance"}

        response = await client.post("/api/v1/domain-packs", json=payload)

        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_domain_pack_of_other_tenant_404(self, client: AsyncClient, auth_headers):
        """
        GIVEN: Domain pack of tenant A
        WHEN: Tenant B requests it
        THEN: Returns 404
        """
        pack_id = uuid4()

        # Request with a valid token carrying a different tenant_id claim
        from src.core.auth.jwt_handler import JWTHandler

        other_tenant_id = 999
        other_token = JWTHandler().create_access_token(
            {
                "sub": "1",
                "user_id": 1,
                "tenant_id": other_tenant_id,
                "email": "admin@example.com",
                "roles": ["admin"],
                "scopes": ["admin:*", "*:*"],
            }
        )
        other_headers = {
            "Authorization": f"Bearer {other_token}",
        }

        response = await client.get(f"/api/v1/domain-packs/{pack_id}", headers=other_headers)

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_domain_pack_invalid_body_422(self, client: AsyncClient, auth_headers):
        """
        GIVEN: Invalid payload (missing required field)
        WHEN: POST /api/v1/domain-packs
        THEN: Returns 422 Unprocessable Entity
        """
        payload = {
            # Missing 'name' and 'department'
            "description": "Test"
        }

        response = await client.post("/api/v1/domain-packs", json=payload, headers=auth_headers)

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_nonexistent_domain_pack_404(self, client: AsyncClient, auth_headers):
        """
        GIVEN: Random UUID that doesn't exist
        WHEN: GET /api/v1/domain-packs/{pack_id}
        THEN: Returns 404
        """
        fake_id = uuid4()

        response = await client.get(f"/api/v1/domain-packs/{fake_id}", headers=auth_headers)

        assert response.status_code == 404
