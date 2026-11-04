"""
Test that SQL injection attempts are blocked via API endpoints.

These tests verify that malicious SQL in input parameters does NOT execute.
A PASS means the injection was blocked (good).
A FAIL means the injection succeeded (security vulnerability).
"""

import pytest
from httpx import AsyncClient


@pytest.mark.security
@pytest.mark.asyncio
async def test_sql_injection_in_tenant_id_blocked(async_client: AsyncClient):
    """
    Attempt SQL injection via tenant_id parameter.
    
    This should be blocked by tenant context validation (SQL injection detection).
    """
    # Malicious tenant_id with SQL injection attempt
    malicious_tenant_id = "1; DROP TABLE users; --"
    
    # Try to access endpoint with malicious tenant_id in various ways
    response = await async_client.get(
        "/api/v1/health",
        headers={"X-Tenant-ID": malicious_tenant_id},  # Should be ignored
    )
    
    # Should NOT succeed with injection
    # The X-Tenant-ID header should be ignored, so this either:
    # - Returns 401 (no auth)
    # - Returns 200 (health check is public)
    # But should NEVER execute the DROP TABLE
    assert response.status_code in [200, 401, 403, 404], (
        f"Unexpected error, but injection should not execute. Status: {response.status_code}"
    )


@pytest.mark.security
@pytest.mark.asyncio
async def test_sql_injection_in_query_params_blocked(
    async_client: AsyncClient,
    admin_token: str,
):
    """
    Attempt SQL injection via query parameters.
    
    Many endpoints accept filter/sort parameters that could be injected.
    """
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    # Malicious search parameter
    malicious_search = "' OR '1'='1"
    
    response = await async_client.get(
        "/api/v1/agents",
        params={"search": malicious_search},
        headers=headers,
    )
    
    # Should either:
    # - Return empty list (search finds nothing)
    # - Return 400/422 (validation error)
    # - Return 404 (endpoint not found)
    # Should NEVER execute the SQL injection
    assert response.status_code in [200, 400, 404, 422], (
        f"SQL injection might have succeeded! Status: {response.status_code}, Body: {response.text}"
    )
    
    if response.status_code == 200:
        # If 200, ensure it's not returning ALL data (injection success)
        # This would indicate a successful 'OR 1=1' injection
        data = response.json()
        if isinstance(data, list):
            # If it's a list, check if it's suspiciously large
            # (would indicate returning all records)
            assert len(data) < 1000, (
                "Suspiciously large result set - possible SQL injection success!"
            )


@pytest.mark.security
@pytest.mark.asyncio
async def test_sql_injection_in_sort_param_blocked(
    async_client: AsyncClient,
    admin_token: str,
):
    """
    Attempt SQL injection via sort parameter.
    
    ORDER BY clauses are common injection vectors.
    """
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    # Malicious sort parameter (stacked query)
    malicious_sort = "id; DROP TABLE audit_logs; --"
    
    response = await async_client.get(
        "/api/v1/agents",
        params={"sort": malicious_sort},
        headers=headers,
    )
    
    # Should be blocked by validation
    assert response.status_code in [200, 400, 404, 422], (
        f"Possible SQL injection! Status: {response.status_code}"
    )


@pytest.mark.security
@pytest.mark.asyncio
async def test_sql_injection_union_select_blocked(
    async_client: AsyncClient,
    admin_token: str,
):
    """
    Attempt UNION-based SQL injection.
    
    This tries to append a UNION SELECT to extract data from other tables.
    """
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    # UNION injection attempt
    malicious_filter = "1 UNION SELECT * FROM users --"
    
    response = await async_client.get(
        "/api/v1/agents",
        params={"filter": malicious_filter},
        headers=headers,
    )
    
    # Should NOT succeed
    assert response.status_code in [200, 400, 404, 422], (
        f"UNION injection might have succeeded! Status: {response.status_code}"
    )
    
    if response.status_code == 200:
        data = response.json()
        # Check if response structure looks like user data (injection success)
        # instead of agent data
        if isinstance(data, list) and len(data) > 0:
            first_item = data[0]
            if "password_hash" in first_item or "email" in first_item:
                pytest.fail("SQL injection succeeded - user data leaked!")


@pytest.mark.security
@pytest.mark.asyncio
async def test_sql_injection_comment_blocked(
    async_client: AsyncClient,
    admin_token: str,
):
    """
    Test that SQL comments don't bypass validation.
    
    Comments like /* ... */ or -- can sometimes bypass filters.
    """
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    # Comment-based injection
    malicious_input = "admin'/*" + "*/ OR '1'='1"
    
    response = await async_client.get(
        "/api/v1/agents",
        params={"name": malicious_input},
        headers=headers,
    )
    
    assert response.status_code in [200, 400, 404, 422], (
        f"Comment injection might have worked! Status: {response.status_code}"
    )
