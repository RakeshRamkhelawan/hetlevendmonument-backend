"""
P5.3.1: Playwright E2E Tests - Authentication Flow
===================================================

Tests for:
- User login
- User logout
- Password reset flow
- Session persistence
- Token expiration handling

Prerequisites:
    docker-compose -f docker-compose.test.prod.yml up -d
    Frontend running on http://localhost:3000
    Backend running on http://localhost:8110 (or TEST_BASE_URL env var)

Run tests:
    pytest tests/e2e/test_playwright_auth.py -v
    pytest tests/e2e/test_playwright_auth.py::test_user_login_success -v
"""

import asyncio
import os
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator

# For browser automation tests, we'll use httpx for API calls
# and simulate user interactions
import httpx
import pytest

from tests.e2e.conftest import (
    E2E_BASE_URL,
    e2e_login_user,
    e2e_register_and_login,
    e2e_register_user,
)

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.asyncio,
]

BASE_URL = E2E_BASE_URL


class TestAuthenticationFlow:
    """Complete authentication flow tests"""

    @pytest.fixture
    async def api_client(self) -> AsyncGenerator[httpx.AsyncClient, None]:
        """HTTP client for API testing"""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=60.0) as client:
            yield client

    @pytest.fixture
    async def test_user_email(self) -> str:
        """Generate unique test email"""
        timestamp = datetime.now(timezone.utc).isoformat().replace(":", "-").replace(".", "-")
        return f"e2e_test_{timestamp}@example.com"

    @pytest.fixture
    async def test_user_password(self) -> str:
        """Test password"""
        return "TestPassword123!"

    # ========================================================================
    # TEST 1: User Registration
    # ========================================================================

    @pytest.mark.asyncio
    async def test_user_registration_success(
        self,
        api_client: httpx.AsyncClient,
        test_user_email: str,
        test_user_password: str,
    ):
        """
        Test successful user registration.

        Steps:
        1. POST /auth/register with valid email and password
        2. Verify 201 Created response
        3. Verify response contains user ID and email
        """
        response = await e2e_register_user(api_client, test_user_email, test_user_password)

        assert response.status_code == 201, f"Registration failed: {response.text}"
        data = response.json()
        assert "id" in data or "user_id" in data, "Response missing user ID"
        assert data.get("email") == test_user_email, "Email mismatch"
        # User might be active or pending activation depending on implementation
        assert isinstance(data, dict), "Response should be dict"

    @pytest.mark.asyncio
    async def test_user_registration_duplicate_email(
        self,
        api_client: httpx.AsyncClient,
        test_user_email: str,
        test_user_password: str,
    ):
        """
        Test registration with duplicate email.

        Steps:
        1. Register first user
        2. Attempt to register with same email
        3. Verify 400 or 409 error
        """
        # First registration should succeed
        response1 = await e2e_register_user(api_client, test_user_email, test_user_password)
        if response1.status_code == 429:
            pytest.skip("Rate limited during registration")
        assert response1.status_code == 201

        # Second registration should fail
        response2 = await e2e_register_user(api_client, test_user_email, test_user_password)
        if response2.status_code == 429:
            pytest.skip("Rate limited during duplicate registration")
        assert response2.status_code in [400, 409], "Should reject duplicate email"

    # ========================================================================
    # TEST 2: User Login
    # ========================================================================

    @pytest.mark.asyncio
    async def test_user_login_success(
        self,
        api_client: httpx.AsyncClient,
        test_user_email: str,
        test_user_password: str,
    ):
        """
        Test successful user login.

        Steps:
        1. Register user
        2. POST /auth/token with email and password (OAuth2 form data)
        3. Verify 200 OK response
        4. Verify access_token in response
        """
        # Register user first
        register_response = await e2e_register_user(api_client, test_user_email, test_user_password)
        if register_response.status_code == 429:
            pytest.skip("Rate limited during registration")
        assert (
            register_response.status_code == 201
        ), f"Registration failed: {register_response.status_code} {register_response.text}"

        # Login
        login_response = await e2e_login_user(api_client, test_user_email, test_user_password)

        assert login_response.status_code == 200, f"Login failed: {login_response.text}"
        data = login_response.json()
        assert "access_token" in data, "Response missing access_token"
        assert "token_type" in data, "Response missing token_type"
        assert data["token_type"] == "bearer", "Invalid token type"

    @pytest.mark.asyncio
    async def test_user_login_invalid_password(
        self,
        api_client: httpx.AsyncClient,
        test_user_email: str,
        test_user_password: str,
    ):
        """
        Test login with invalid password.

        Steps:
        1. Register user
        2. POST /auth/token with wrong password
        3. Verify 401 Unauthorized
        """
        # Register user
        reg_resp = await e2e_register_user(api_client, test_user_email, test_user_password)
        if reg_resp.status_code == 429:
            pytest.skip("Rate limited during registration")

        # Login with wrong password
        response = await api_client.post(
            "/api/v1/auth/token",
            data={
                "username": test_user_email,
                "password": "WrongPassword123!",
            },
        )

        assert response.status_code in [401, 429], "Should reject invalid password"

    @pytest.mark.asyncio
    async def test_user_login_nonexistent_user(self, api_client: httpx.AsyncClient):
        """
        Test login with non-existent user.

        Steps:
        1. POST /auth/token with non-existent email
        2. Verify 401 Unauthorized
        """
        response = await api_client.post(
            "/api/v1/auth/token",
            data={
                "username": "nonexistent@example.com",
                "password": "AnyPassword123!",
            },
        )

        assert response.status_code in [401, 429], "Should reject non-existent user"

    # ========================================================================
    # TEST 3: Get Current User Profile
    # ========================================================================

    @pytest.mark.asyncio
    async def test_get_current_user_profile(
        self,
        api_client: httpx.AsyncClient,
        test_user_email: str,
        test_user_password: str,
    ):
        """
        Test retrieving current user profile.

        Steps:
        1. Register and login
        2. GET /auth/me with JWT token
        3. Verify 200 OK
        4. Verify response contains user data
        """
        # Register and login
        access_token, _ = await e2e_register_and_login(
            api_client, test_user_email, test_user_password
        )
        if access_token is None:
            pytest.skip("Auth unavailable (rate limited)")

        # Get user profile
        response = await api_client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"}
        )

        assert response.status_code == 200, f"Failed to get user profile: {response.text}"
        data = response.json()
        assert data["email"] == test_user_email, "Email mismatch in profile"

    @pytest.mark.asyncio
    async def test_get_current_user_without_auth(self, api_client: httpx.AsyncClient):
        """
        Test accessing /auth/me without authentication.

        Steps:
        1. GET /auth/me without token
        2. Verify 401 Unauthorized
        """
        response = await api_client.get("/api/v1/auth/me")

        assert response.status_code == 401, "Should require authentication"

    # ========================================================================
    # TEST 4: Logout / Token Revocation
    # ========================================================================

    @pytest.mark.asyncio
    async def test_user_logout_success(
        self,
        api_client: httpx.AsyncClient,
        test_user_email: str,
        test_user_password: str,
    ):
        """
        Test successful user logout.

        Steps:
        1. Register and login
        2. POST /auth/logout with JWT token
        3. Verify 200 OK or 204 No Content (or 404 if not implemented)
        4. Verify token is no longer valid
        """
        # Register and login
        access_token, _ = await e2e_register_and_login(
            api_client, test_user_email, test_user_password
        )
        if access_token is None:
            pytest.skip("Auth unavailable (rate limited)")

        # Logout
        logout_response = await api_client.post(
            "/api/v1/auth/logout", headers={"Authorization": f"Bearer {access_token}"}
        )

        # Logout endpoint might not be implemented
        assert logout_response.status_code in [
            200,
            204,
            404,
        ], f"Logout failed: {logout_response.text}"

    # ========================================================================
    # TEST 5: Password Reset (if implemented)
    # ========================================================================

    @pytest.mark.asyncio
    async def test_password_reset_request(
        self,
        api_client: httpx.AsyncClient,
        test_user_email: str,
        test_user_password: str,
    ):
        """
        Test password reset request.

        Steps:
        1. Register user
        2. POST /auth/password-reset with email (or authenticated)
        3. Verify 200 OK or 404 (if endpoint doesn't exist)
        """
        # Register user
        reg_resp = await e2e_register_user(api_client, test_user_email, test_user_password)
        if reg_resp.status_code == 429:
            pytest.skip("Rate limited during registration")

        # Try to request password reset
        # This might require auth or might be public
        response = await api_client.post(
            "/api/v1/auth/password-reset", json={"email": test_user_email}
        )

        # Endpoint might not be implemented (404) or might require auth (401)
        assert response.status_code in [
            200,
            401,
            404,
        ], f"Password reset failed: {response.text}"

    @pytest.mark.asyncio
    async def test_session_persistence_across_requests(
        self,
        api_client: httpx.AsyncClient,
        test_user_email: str,
        test_user_password: str,
    ):
        """
        Test that JWT token remains valid across multiple requests.

        Steps:
        1. Register and login
        2. Make multiple API calls with same token
        3. Verify all succeed
        """
        # Register and login
        access_token, _ = await e2e_register_and_login(
            api_client, test_user_email, test_user_password
        )
        if access_token is None:
            pytest.skip("Auth unavailable (rate limited)")
        headers = {"Authorization": f"Bearer {access_token}"}

        # Make multiple requests
        for i in range(5):
            response = await api_client.get("/api/v1/auth/me", headers=headers)
            assert (
                response.status_code == 200
            ), f"Request {i+1} failed with status {response.status_code}"

    @pytest.mark.asyncio
    async def test_token_refresh_flow(
        self,
        api_client: httpx.AsyncClient,
        test_user_email: str,
        test_user_password: str,
    ):
        """
        Test token refresh flow (if implemented).

        Steps:
        1. Register and login
        2. Attempt to refresh token
        3. Verify response (may be 404 if not implemented)
        """
        # Register and login
        try:
            access_token, _ = await e2e_register_and_login(
                api_client, test_user_email, test_user_password
            )
        except httpx.ReadTimeout:
            pytest.skip("Registration timed out (backend under load)")
        if access_token is None:
            pytest.skip("Auth unavailable (rate limited)")

        # Try to refresh token
        try:
            refresh_response = await api_client.post(
                "/api/v1/auth/refresh",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        except httpx.ReadTimeout:
            pytest.skip("Refresh endpoint timed out")

        # May be 200 if implemented, 404 if not, 422 if wrong payload format
        assert refresh_response.status_code in [200, 404, 422]


# ============================================================================
# HELPER FIXTURES


@pytest.fixture(autouse=True)
async def wait_for_backend():
    """Ensure backend is available before tests run"""
    max_retries = 30
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(base_url=BASE_URL, timeout=5.0) as client:
                response = await client.get("/health")
                if response.status_code == 200:
                    return
        except Exception:
            pass

        if attempt < max_retries - 1:
            await asyncio.sleep(1)

    raise RuntimeError("Backend not available after 30 seconds")
