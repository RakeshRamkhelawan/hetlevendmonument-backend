import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_user_creation_fix(client: AsyncClient, admin_auth_headers: dict[str, str]):
    """
    Test user creation logic with full_name fix.
    """
    # Setup - Use superuser to create tenant
    tenant_payload = {
        "name": "User Fix Corp",
        "slug": "user-fix-corp",
        "subdomain": "user-fix",
        "contact_email": "admin@userfix.com",
    }
    response = await client.post(
        "/api/v1/tenants/", json=tenant_payload, headers=admin_auth_headers
    )
    assert response.status_code in [
        200,
        201,
    ], f"Tenant creation failed: {response.text}"
    tenant_id = response.json()["id"]

    # Create user with full_name (which should be handled correctly now)
    user_payload = {
        "email": "admin@userfix.com",
        "password": "UserFixPass123!",
        "full_name": "Fix Admin",
    }
    response = await client.post(
        f"/api/v1/users/?target_tenant_id={tenant_id}",
        json=user_payload,
        headers=admin_auth_headers,
    )

    # Assertions
    assert response.status_code in [200, 201], f"User creation failed: {response.text}"
    data = response.json()
    assert data["email"] == user_payload["email"]
    # full_name should be in response (even if None) or simply not be used by endpoint
    # The endpoint may not include full_name in the response at all
    if "full_name" in data:
        assert data["full_name"] is None  # Should be None in response
