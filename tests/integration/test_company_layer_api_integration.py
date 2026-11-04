"""Company Layer API Integration Tests - Fase 2.4

Integration tests for Company Layer REST API endpoints with real database.
Tests FastAPI routers end-to-end with authentication and tenant isolation.

Pattern: FastAPI Dependency Override with PostgreSQL test database
Reference: https://fastapi.tiangolo.com/advanced/testing-dependencies/

Environment: PostgreSQL 15+ (Docker) + FastAPI TestClient
Execution: pytest tests/integration/test_company_layer_api_integration.py -v -m integration
"""

import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Mark all tests as integration tests
pytestmark = [
    pytest.mark.integration,
    pytest.mark.asyncio,
    pytest.mark.requires_postgres,
]


# ==============================================================================
# FASTAPI TEST CLIENT FIXTURE
# ==============================================================================


@pytest_asyncio.fixture(scope="function")
async def company_test_client(
    integration_app,
    postgres_session,
) -> AsyncGenerator[AsyncClient, None]:
    """Create async test client with auth and database overrides.

    Uses FastAPI dependency override to bypass JWT authentication
    and use the test database session.
    """
    from fastapi import Depends

    from src.core.api.v1.company.department_individual_router import (
        get_department_service as get_individual_department_service,
    )
    from src.core.api.v1.company.department_router import get_department_service
    from src.core.api.v1.company.router import get_company_service
    from src.core.auth.dependencies import get_current_user
    from src.core.database.database import get_async_session, get_db
    from src.core.database.session import get_db_session

    # Override auth to return mock user
    async def override_get_current_user():
        from src.core.auth.auth_service import UserResponse

        return UserResponse(
            id=1,
            email="admin@example.com",
            tenant_id=1,
            is_active=True,
            roles=[],
        )

    # Override database to use test session
    async def override_get_async_session():
        yield postgres_session

    async def override_get_db():
        yield postgres_session

    # Override company service to use test session directly
    from contextlib import asynccontextmanager

    class _MockDBManager:
        def __init__(self, session):
            self._session = session

        @asynccontextmanager
        async def get_session(self):
            yield self._session

    def override_get_company_service(current_user=Depends(get_current_user)):
        from src.core.company.company_service import CompanyService
        from src.core.container import TenantContext

        tenant_context = TenantContext(
            tenant_id=current_user.tenant_id,
            tenant_slug=None,
            bypass_filter=False,
        )
        return CompanyService(
            db_manager=_MockDBManager(postgres_session),
            tenant_context=tenant_context,
        )

    def override_get_department_service(current_user=Depends(get_current_user)):
        from src.core.company.department_service import DepartmentService
        from src.core.container import TenantContext

        tenant_context = TenantContext(
            tenant_id=current_user.tenant_id,
            tenant_slug=None,
            bypass_filter=False,
        )
        return DepartmentService(
            db_manager=_MockDBManager(postgres_session),
            tenant_context=tenant_context,
        )

    integration_app.dependency_overrides[get_current_user] = override_get_current_user
    integration_app.dependency_overrides[get_async_session] = override_get_async_session
    integration_app.dependency_overrides[get_db] = override_get_db
    integration_app.dependency_overrides[get_db_session] = override_get_db
    integration_app.dependency_overrides[get_company_service] = override_get_company_service
    integration_app.dependency_overrides[get_department_service] = override_get_department_service
    integration_app.dependency_overrides[
        get_individual_department_service
    ] = override_get_department_service

    transport = ASGITransport(app=integration_app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    # Clean up only our overrides
    for dep in [
        get_current_user,
        get_async_session,
        get_db,
        get_db_session,
        get_company_service,
        get_department_service,
        get_individual_department_service,
    ]:
        integration_app.dependency_overrides.pop(dep, None)


def create_test_jwt_token() -> str:
    """Create a valid JWT token for testing.

    The token is signed with the same secret used by the test environment.
    """
    import os
    from datetime import datetime, timedelta, timezone

    from jose import jwt

    # Use the same secret as conftest.py
    secret = os.environ.get(
        "JWT_SECRET_KEY", "test-secret-key-for-integration-tests-32chars-minimum"
    )

    payload = {
        "sub": "1",
        "user_id": 1,
        "tenant_id": 1,
        "email": "admin@example.com",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }

    return jwt.encode(payload, secret, algorithm="HS256")


@pytest.fixture(scope="function")
def auth_headers(admin_token: str) -> dict[str, str]:
    """Create auth headers with valid JWT token.

    The token passes TenantMiddleware validation.
    """
    return {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json",
        "X-Tenant-ID": "1",
    }


# ==============================================================================
# TEST SUITE: Company API Endpoints
# ==============================================================================


class TestCompanyAPIEndpoints:
    """Integration tests for Company REST API endpoints."""

    async def test_create_company_success(
        self,
        company_test_client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test POST /api/v1/companies creates a company."""
        payload = {
            "name": "Test Company",
            "mission": "Test mission",
            "company_type": "enterprise",
            "sector": "technology",
        }

        response = await company_test_client.post(
            "/api/v1/companies",
            json=payload,
            headers=auth_headers,
        )

        print(f"[DEBUG] Response status: {response.status_code}")
        print(f"[DEBUG] Response body: {response.text}")

        if response.status_code != 201:
            print(f"[ERROR] Expected 201 but got {response.status_code}")
            print(f"[ERROR] Response headers: {dict(response.headers)}")

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Test Company"
        assert data["mission"] == "Test mission"
        assert data["status"] == "active"
        assert "id" in data

    async def test_list_companies(
        self,
        company_test_client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test GET /api/v1/companies returns companies."""
        # First create a company (using valid company_type enum)
        create_response = await company_test_client.post(
            "/api/v1/companies",
            json={"name": "Company A", "company_type": "mkb", "sector": "tech"},
            headers=auth_headers,
        )

        print(f"[DEBUG] Create response status: {create_response.status_code}")
        print(f"[DEBUG] Create response body: {create_response.text}")

        assert (
            create_response.status_code == 201
        ), f"Failed to create company: {create_response.text}"

        response = await company_test_client.get(
            "/api/v1/companies",
            headers=auth_headers,
        )

        print(f"[DEBUG] List response status: {response.status_code}")
        print(f"[DEBUG] List response body: {response.text}")

        assert response.status_code == 200
        data = response.json()

        # API returns {"companies": [], "total": 0} format
        companies = data.get("companies", [])
        assert len(companies) >= 1, f"Expected at least 1 company, got {len(companies)}"

    async def test_get_company_by_id(
        self,
        company_test_client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test GET /api/v1/companies/{id} returns specific company."""
        # Create a company
        create_response = await company_test_client.post(
            "/api/v1/companies",
            json={"name": "Specific Company", "company_type": "enterprise", "sector": "tech"},
            headers=auth_headers,
        )
        company_id = create_response.json()["id"]

        response = await company_test_client.get(
            f"/api/v1/companies/{company_id}",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == company_id
        assert data["name"] == "Specific Company"

    async def test_get_company_not_found(
        self,
        company_test_client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test GET /api/v1/companies/{id} returns 404 for unknown ID."""
        fake_id = str(uuid.uuid4())

        response = await company_test_client.get(
            f"/api/v1/companies/{fake_id}",
            headers=auth_headers,
        )

        assert response.status_code == 404

    async def test_update_company_success(
        self,
        company_test_client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test PUT /api/v1/companies/{id} updates a company."""
        # Create a company
        create_response = await company_test_client.post(
            "/api/v1/companies",
            json={"name": "Old Name", "company_type": "mkb", "sector": "tech"},
            headers=auth_headers,
        )
        company_id = create_response.json()["id"]

        # Update it
        response = await company_test_client.put(
            f"/api/v1/companies/{company_id}",
            json={"name": "New Name", "mission": "Updated mission"},
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "New Name"
        assert data["mission"] == "Updated mission"

    async def test_delete_company_soft(
        self,
        company_test_client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test DELETE /api/v1/companies/{id} soft deletes a company."""
        # Create a company
        create_response = await company_test_client.post(
            "/api/v1/companies",
            json={"name": "To Delete", "company_type": "mkb", "sector": "tech"},
            headers=auth_headers,
        )
        company_id = create_response.json()["id"]

        # Delete it
        response = await company_test_client.delete(
            f"/api/v1/companies/{company_id}",
            headers=auth_headers,
        )

        assert response.status_code == 200

        # Verify it's soft deleted (404 on GET)
        get_response = await company_test_client.get(
            f"/api/v1/companies/{company_id}",
            headers=auth_headers,
        )
        assert get_response.status_code == 404


# ==============================================================================
# TEST SUITE: Department API Endpoints
# ==============================================================================


class TestDepartmentAPIEndpoints:
    """Integration tests for Department REST API endpoints."""

    async def test_create_department_success(
        self,
        company_test_client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test POST /api/v1/departments?company_id=xxx creates a department."""
        # First create a company
        company_response = await company_test_client.post(
            "/api/v1/companies",
            json={"name": "Parent Company", "company_type": "enterprise", "sector": "tech"},
            headers=auth_headers,
        )
        company_id = company_response.json()["id"]

        payload = {
            "name": "Engineering",
            "board_role": "technical_lead",
        }

        response = await company_test_client.post(
            f"/api/v1/companies/{company_id}/departments",
            json=payload,
            headers=auth_headers,
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Engineering"
        assert data["company_id"] == company_id

    async def test_get_org_chart(
        self,
        company_test_client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test GET /api/v1/departments/org-chart returns hierarchy."""
        # Create company and department
        company_response = await company_test_client.post(
            "/api/v1/companies",
            json={"name": "Org Company", "company_type": "enterprise", "sector": "tech"},
            headers=auth_headers,
        )
        company_id = company_response.json()["id"]

        await company_test_client.post(
            f"/api/v1/companies/{company_id}/departments",
            json={"name": "Root Dept"},
            headers=auth_headers,
        )

        response = await company_test_client.get(
            f"/api/v1/companies/{company_id}/departments",
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        # API returns {"departments": [...], "tree_structure": {...}} format
        assert "departments" in data
        assert "tree_structure" in data
        assert len(data["departments"]) >= 1

    async def test_update_department(
        self,
        company_test_client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test PUT /api/v1/departments/{id} updates a department."""
        # Create company and department
        company_response = await company_test_client.post(
            "/api/v1/companies",
            json={"name": "Update Company", "company_type": "enterprise", "sector": "tech"},
            headers=auth_headers,
        )
        company_id = company_response.json()["id"]

        dept_response = await company_test_client.post(
            f"/api/v1/companies/{company_id}/departments",
            json={"name": "Old Dept Name"},
            headers=auth_headers,
        )
        dept_id = dept_response.json()["id"]
        version = dept_response.json()["version"]

        # Update department
        response = await company_test_client.put(
            f"/api/v1/departments/{dept_id}",
            json={
                "name": "New Dept Name",
                "expected_version": version,
            },
            headers=auth_headers,
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "New Dept Name"

    async def test_update_department_version_conflict(
        self,
        company_test_client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test optimistic locking returns 409 on version conflict."""
        # Create company and department
        company_response = await company_test_client.post(
            "/api/v1/companies",
            json={"name": "Conflict Company", "company_type": "enterprise", "sector": "tech"},
            headers=auth_headers,
        )
        company_id = company_response.json()["id"]

        dept_response = await company_test_client.post(
            f"/api/v1/companies/{company_id}/departments",
            json={"name": "Conflict Dept"},
            headers=auth_headers,
        )
        dept_id = dept_response.json()["id"]

        # Try to update with wrong version
        response = await company_test_client.put(
            f"/api/v1/departments/{dept_id}",
            json={
                "name": "New Name",
                "expected_version": 999,  # Wrong version
            },
            headers=auth_headers,
        )

        assert response.status_code == 409

    async def test_delete_department(
        self,
        company_test_client: AsyncClient,
        auth_headers: dict[str, str],
    ) -> None:
        """Test DELETE /api/v1/departments/{id} deletes a department."""
        # Create company and department
        company_response = await company_test_client.post(
            "/api/v1/companies",
            json={"name": "Delete Company", "company_type": "enterprise", "sector": "tech"},
            headers=auth_headers,
        )
        company_id = company_response.json()["id"]

        dept_response = await company_test_client.post(
            f"/api/v1/companies/{company_id}/departments",
            json={"name": "To Delete"},
            headers=auth_headers,
        )
        dept_id = dept_response.json()["id"]

        # Delete it
        response = await company_test_client.delete(
            f"/api/v1/departments/{dept_id}",
            headers=auth_headers,
        )

        assert response.status_code == 200

        # Verify deletion (GET should return 404)
        get_response = await company_test_client.get(
            f"/api/v1/departments/{dept_id}",
            headers=auth_headers,
        )
        assert get_response.status_code == 404
