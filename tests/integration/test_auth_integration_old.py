"""
Integration tests for the authentication system.
Validates the unified /api/v1/auth endpoints.
"""

import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from httpx import AsyncClient

# Global test data
TEST_USER = {
    "username": "test_auth_user",
    "email": "test_auth@example.com",
    "password": "SecurePassword123!",
}

import os

# The secret key for testing (matches what's used in the app under testing)
# In integration tests, we must use the key the app expects.
TEST_SECRET_KEY = os.getenv(
    "JWT_SECRET_KEY", "test-secret-key-for-integration-tests-32chars-minimum"
)
ALGORITHM = "HS256"


@pytest.mark.skip(
    reason="Fixture scope mismatch (session app vs function engine) causes periodic loop errors. Use test_auth_comprehensive_flow_fixed.py for stable E2E validation."
)
@pytest.mark.asyncio
async def test_auth_comprehensive_flow(integration_client: AsyncClient):
    """
    Test individual auth components in sequence with SQLite robustness.
    1. Register
    2. Small delay for SQLite WAL visibility
    3. Login (/token)
    4. Access /me
    """
    import asyncio

    unique_suffix = str(uuid.uuid4())[:8]
    email = f"flow_{unique_suffix}@example.com"
    username = f"user_{unique_suffix}"

    # 1. Register
    reg_resp = await integration_client.post(
        "/api/v1/auth/register",
        json={
            "username": username,
            "email": email,
            "password": TEST_USER["password"],
        },
    )
    assert reg_resp.status_code == 201, f"Registration failed: {reg_resp.text}"

    # SQLITE ROBUSTNESS FIX
    # Small delay for WAL visibility. The router already commits internally.
    await asyncio.sleep(0.05)

    # 2. Login via /api/v1/auth/token (OAuth2 standard)
    login_resp = await integration_client.post(
        "/api/v1/auth/token",
        data={
            "username": email,
            "password": TEST_USER["password"],
            "grant_type": "password",
        },
    )
    assert login_resp.status_code == 200, f"Login via /token failed: {login_resp.text}"
    token_data = login_resp.json()
    assert "access_token" in token_data
    access_token = token_data["access_token"]

    # 3. Access protected /api/v1/auth/me
    headers = {"Authorization": f"Bearer {access_token}"}
    me_resp = await integration_client.get("/api/v1/auth/me", headers=headers)
    assert me_resp.status_code == 200, f"Me endpoint failed with token: {me_resp.text}"
    me_data = me_resp.json()
    assert me_data["email"] == email


@pytest.mark.asyncio
async def test_protected_endpoint_no_token(integration_client: AsyncClient):
    """Test that protected endpoint rejects requests without token."""
    response = await integration_client.get("/api/v1/auth/me")
    assert response.status_code in (
        401,
        403,
    ), f"Should reject unauthenticated, got {response.status_code}: {response.text}"


@pytest.mark.asyncio
async def test_jwt_expired_token(integration_client: AsyncClient):
    """Test that expired tokens are rejected."""
    # Create an expired token manually
    expired_payload = {
        "sub": "test@example.com",
        "user_id": 999,
        "tenant_id": 1,
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),
    }

    expired_token = jwt.encode(expired_payload, TEST_SECRET_KEY, algorithm=ALGORITHM)
    headers = {"Authorization": f"Bearer {expired_token}"}
    response = await integration_client.get("/api/v1/auth/me", headers=headers)

    # Should reject (401 is returned by verify_token returning None)
    assert response.status_code in (
        401,
        403,
    ), f"Expired token should be 401/403, got {response.status_code}: {response.text}"


@pytest.mark.asyncio
async def test_jwt_invalid_signature(integration_client: AsyncClient):
    """Test that tokens with invalid signature are rejected."""
    payload = {
        "sub": "test@example.com",
        "user_id": 999,
        "tenant_id": 1,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }

    # Wrong secret
    invalid_token = jwt.encode(payload, "wrong-secret-key", algorithm=ALGORITHM)
    headers = {"Authorization": f"Bearer {invalid_token}"}
    response = await integration_client.get("/api/v1/auth/me", headers=headers)

    assert response.status_code in (
        401,
        403,
    ), f"Invalid signature should be 401/403, got {response.status_code}: {response.text}"


@pytest.mark.asyncio
async def test_register_rate_limit(integration_client: AsyncClient):
    """Test that registration rate limiting works."""
    import asyncio

    status_codes = []
    for i in range(10):
        uid = str(uuid.uuid4())[:8]
        resp = await integration_client.post(
            "/api/v1/auth/register",
            json={
                "username": f"rl_{uid}",
                "email": f"rl_{uid}@ex.com",
                "password": "Pass123!",
            },
        )
        status_codes.append(resp.status_code)
        if resp.status_code == 429:
            break
        await asyncio.sleep(0.01)

    assert 429 in status_codes, f"Rate limit (429) was never triggered. Codes: {status_codes}"


@pytest.mark.asyncio
@pytest.mark.xfail(reason="SQLite concurrency issues in test environment")
async def test_concurrent_registration(integration_client: AsyncClient):
    """Test that concurrent registration requests (SQLite might struggle here)."""
    import asyncio

    async def reg():
        uid = str(uuid.uuid4())[:8]
        return await integration_client.post(
            "/api/v1/auth/register",
            json={
                "username": f"c_{uid}",
                "email": f"c_{uid}@ex.com",
                "password": "Pass123!",
            },
        )

    results = await asyncio.gather(*(reg() for _ in range(5)), return_exceptions=True)
    # Check that at least some succeeded or we got a controlled error
    successes = [r for r in results if not isinstance(r, Exception) and r.status_code == 201]
    assert len(successes) > 0, "No concurrent registrations succeeded"


@pytest.mark.asyncio
async def test_health_check(integration_client: AsyncClient):
    """Sanity check that the API is alive."""
    # Note: Health check might be at /health or /api/v1/auth/health
    # We'll try a common one
    response = await integration_client.get("/api/v1/auth/me")
    # Even if 401, it shows the route exists
    assert response.status_code != 404
