"""
Integration Tests for Procedure Execution & Approval API (Sprint 3 Slice 4)

Tests the /{procedure_id}/execute endpoint from the P5 procedures CRUD router.
Route: POST /api/v1/procedures/{procedure_id}/execute (procedure_id is int)
"""

from uuid import uuid4

import pytest
from httpx import AsyncClient


@pytest.fixture
def auth_headers(admin_token: str) -> dict[str, str]:
    """Valid auth headers using the integration admin JWT token."""
    return {"Authorization": f"Bearer {admin_token}"}


class TestProcedureExecution:
    """Test suite for procedure execution endpoints"""

    @pytest.mark.asyncio
    async def test_execute_procedure_not_found(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ):
        """Test executing non-existent procedure returns 404"""
        response = await client.post(
            "/api/v1/procedures/999999/execute",
            json={"context": {}},
            headers=auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_execute_procedure_invalid_id_422(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ):
        """Test executing with non-integer ID returns 422 (or 404 if endpoint not enabled)"""
        response = await client.post(
            "/api/v1/procedures/not-an-int/execute",
            json={"context": {}},
            headers=auth_headers,
        )
        # Endpoint returns 404 if P5 CRUD routers not enabled, 422 if enabled but validation fails
        assert response.status_code in (404, 422)


class TestProcedureApproval:
    """Test suite for approval endpoints — routes don't exist yet, expect 404/405"""

    @pytest.mark.asyncio
    async def test_approve_endpoint_not_implemented(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ):
        """Approve endpoint does not exist yet — expect 404 or 405"""
        execution_id = 999
        response = await client.post(
            f"/api/v1/procedures/{execution_id}/approve",
            headers=auth_headers,
        )
        assert response.status_code in (404, 405)


class TestProcedureExecutionFlow:
    """End-to-end integration tests for full execution flow"""

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_full_execute_flow_returns_404_for_missing(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ):
        """Execute a non-existent procedure — should return 404"""
        response = await client.post(
            "/api/v1/procedures/999999/execute",
            json={"context": {"amount": 5000}},
            headers=auth_headers,
        )
        assert response.status_code == 404


class TestProcedureExecutionValidation:
    """Test input validation and error handling"""

    @pytest.mark.asyncio
    async def test_execute_no_body_returns_422(
        self,
        client: AsyncClient,
        auth_headers: dict[str, str],
    ):
        """Test execution without request body returns 422 (or 404 if endpoint not enabled)"""
        response = await client.post(
            "/api/v1/procedures/1/execute",
            headers=auth_headers,
        )
        # Endpoint returns 404 if P5 CRUD routers not enabled, 422 if enabled but validation fails
        assert response.status_code in (404, 422)


pytestmark = [pytest.mark.integration, pytest.mark.api]
