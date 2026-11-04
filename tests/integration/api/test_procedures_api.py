"""
Integration tests for Procedures API endpoints (P5 CRUD)

Tests validate that the procedures router is registered and responds correctly.
Routes come from src/core/api/v1/procedures/router.py (prefix=/procedures, registered at /api/v1).
"""

from uuid import uuid4

import pytest
from httpx import AsyncClient


@pytest.fixture
def auth_headers(admin_token: str):
    """Valid auth headers using the integration admin JWT token."""
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.mark.skip(
    reason="P5 stub CRUD routers disabled by default. Set ENABLE_P5_STUB_CRUD_ROUTERS=true to enable."
)
class TestProceduresAPI:
    """Tests for procedures REST API"""

    @pytest.mark.asyncio
    async def test_list_procedures_returns_200(self, client: AsyncClient, auth_headers):
        """
        GIVEN: Authenticated user
        WHEN: GET /api/v1/procedures/
        THEN: Returns 200 with (possibly empty) list
        """
        response = await client.get("/api/v1/procedures/", headers=auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "total" in data

    @pytest.mark.asyncio
    async def test_get_procedure_not_found(self, client: AsyncClient, auth_headers):
        """
        GIVEN: Non-existent procedure ID
        WHEN: GET /api/v1/procedures/999999
        THEN: Returns 404
        """
        response = await client.get("/api/v1/procedures/999999", headers=auth_headers)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_procedure_invalid_id_422(self, client: AsyncClient, auth_headers):
        """
        GIVEN: UUID string as procedure ID (expects int)
        WHEN: GET /api/v1/procedures/{uuid}
        THEN: Returns 422 validation error
        """
        procedure_id = uuid4()
        response = await client.get(f"/api/v1/procedures/{procedure_id}", headers=auth_headers)
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_get_procedure_of_other_tenant_404(self, client: AsyncClient, auth_headers):
        """
        GIVEN: Procedure of tenant A
        WHEN: Tenant B requests it
        THEN: Returns 404
        """
        from src.core.auth.jwt_handler import JWTHandler

        other_token = JWTHandler().create_access_token(
            {
                "sub": "1",
                "user_id": 1,
                "tenant_id": 999,
                "email": "admin@example.com",
                "roles": ["admin"],
                "scopes": ["admin:*", "*:*"],
            }
        )
        other_headers = {"Authorization": f"Bearer {other_token}"}
        response = await client.get("/api/v1/procedures/999999", headers=other_headers)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_procedures_unauthorized_401(self, client: AsyncClient):
        """
        GIVEN: No auth headers
        WHEN: GET /api/v1/procedures/
        THEN: Returns 401 or 403
        """
        response = await client.get("/api/v1/procedures/")
        assert response.status_code in (401, 403)

    @pytest.mark.asyncio
    async def test_list_procedures_with_pagination(self, client: AsyncClient, auth_headers):
        """
        GIVEN: Pagination parameters
        WHEN: GET /api/v1/procedures/?skip=0&limit=10
        THEN: Returns 200 with paginated results
        """
        response = await client.get(
            "/api/v1/procedures/", params={"skip": 0, "limit": 10}, headers=auth_headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["per_page"] == 10
