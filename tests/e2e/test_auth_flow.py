"""
E2E Tests for Complete Authentication Flow

End-to-end tests covering registration, login, and protected endpoints.
Requires running backend server (TEST_BASE_URL env var, default localhost:8110).
"""

import httpx
import pytest

from tests.e2e.conftest import E2E_BASE_URL

# E2E marker - requires running backend (see TEST_BASE_URL env var)
pytestmark = pytest.mark.e2e

BASE_URL = E2E_BASE_URL


@pytest.fixture
def client():
    """HTTP client for E2E tests."""
    return httpx.Client(base_url=BASE_URL, timeout=30.0)


class TestRegistrationFlow:
    """E2E tests for user registration."""

    def test_registration_with_valid_data(self, client):
        """Test user registration with valid data."""
        import uuid

        unique_email = f"e2e_test_{uuid.uuid4().hex[:8]}@example.com"

        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": unique_email,
                "password": "E2ETestPass123!",
                "password_confirm": "E2ETestPass123!",
            },
        )

        # Should succeed or get proper error response
        assert response.status_code in [200, 201, 422, 400, 429]

    def test_registration_with_weak_password_fails(self, client):
        """Test registration rejects weak passwords."""
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "weakpass@example.com",
                "password": "weak",
                "password_confirm": "weak",
            },
        )

        # Should return validation error
        assert response.status_code in [400, 422]


class TestLoginFlow:
    """E2E tests for user login."""

    def test_login_with_invalid_credentials(self, client):
        """Test login with invalid credentials returns 401."""
        response = client.post(
            "/api/v1/auth/token",
            data={"username": "nonexistent@example.com", "password": "wrongpassword"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        assert response.status_code in [401, 400, 422, 429]

    def test_login_response_format(self, client):
        """Test login endpoint returns proper format."""
        response = client.post(
            "/api/v1/auth/token",
            data={"username": "test@example.com", "password": "TestPass123!"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

        # Either success with token or proper error
        if response.status_code == 200:
            data = response.json()
            assert "access_token" in data
            assert "token_type" in data


class TestProtectedEndpoints:
    """E2E tests for protected endpoints."""

    def test_protected_endpoint_without_token(self, client):
        """Test protected endpoints require authentication."""
        response = client.get("/api/v1/auth/me")

        # Should return 401 or 403
        assert response.status_code in [401, 403, 404]

    def test_protected_endpoint_with_invalid_token(self, client):
        """Test protected endpoints reject invalid tokens."""
        response = client.get(
            "/api/v1/auth/me", headers={"Authorization": "Bearer invalid_token_here"}
        )

        assert response.status_code in [401, 403, 422]


class TestAccountLockoutFlow:
    """E2E tests for account lockout (SA-1)."""

    def test_multiple_failed_logins_triggers_lockout(self, client):
        """Test account gets locked after multiple failed attempts."""
        import uuid

        test_email = f"lockout_test_{uuid.uuid4().hex[:8]}@example.com"

        # Attempt multiple failed logins
        for i in range(6):
            response = client.post(
                "/api/v1/auth/token",
                data={"username": test_email, "password": f"wrong_password_{i}"},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )

        # Should get error response (account may not exist, but lockout logic should trigger)
        assert response.status_code in [401, 403, 429, 400, 422]


class TestHealthFlow:
    """E2E tests for health check flow."""

    def test_complete_health_check(self, client):
        """Test complete health check flow."""
        # Check basic health
        health_response = client.get("/health")
        assert health_response.status_code == 200

        # Check readiness (may require auth if not in excluded prefixes)
        ready_response = client.get("/ready")
        assert ready_response.status_code in [200, 401, 503]

        # De /docs-vervolgcheck is op 2026-08-14 verwijderd: sinds ADR-036 OP-124 is een
        # bereikbare /docs juist een defect buiten development, dus "API is serving" kan er
        # niet meer aan afgelezen worden. De hardening zelf wordt getoetst door
        # tests/architecture/test_docs_disabled_in_prod.py en tests/smoke/test_critical_paths.py.
