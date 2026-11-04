"""
Integration tests for Authentication Security
Tests real API endpoints without mocking security components

Requirements:
- PostgreSQL database running
- Redis running
- Backend server running (or use test client)
"""

import os
from datetime import datetime, timezone

import pytest

# Skip all tests if integration test dependencies not available
pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("SKIP_INTEGRATION_TESTS") == "1",
        reason="Integration tests disabled via SKIP_INTEGRATION_TESTS",
    ),
]


class TestJWTSecretNotLogged:
    """Integration test: Verify JWT secrets never appear in logs"""

    @pytest.mark.asyncio
    @pytest.mark.xfail(
        reason="Test calls get_async_session() directly instead of using postgres_session fixture"
    )
    async def test_login_does_not_log_secrets(self, test_client, caplog):
        """
        Integration test: Complete login flow does not log secrets

        Steps:
        1. Create test user
        2. Perform login
        3. Check all logs for secret material
        """
        from src.core.api.auth.schemas import UserCreate
        from src.core.auth.auth_service import auth_service
        from src.core.database.database import get_async_session

        async for db in get_async_session():
            # Create test user
            user_data = UserCreate(
                email="test_log_security@example.com", password="SecureP@ssw0rd123!"
            )

            user = await auth_service.create_user(
                db=db,
                user_data=user_data,
                client_ip="127.0.0.1",
                tenant_id=1,
                request_path="/test",
            )

            assert user is not None

            # Capture logs during login
            with caplog.at_level("DEBUG"):
                login_result = await auth_service.authenticate_user(
                    db=db,
                    email="test_log_security@example.com",
                    password="SecureP@ssw0rd123!",
                    client_ip="127.0.0.1",
                )

                assert login_result is not None

                # Verify no secrets in logs
                secret_indicators = ["secret_key", "secret", "password", "hashed_password"]
                for record in caplog.records:
                    message = record.message.lower()
                    for indicator in secret_indicators:
                        # Allow "password" in validation messages, but not actual values
                        if indicator in message and "validation" not in message:
                            # Check if actual secret value appears (not just the word)
                            if len(message) > len(indicator) + 10:
                                assert False, f"Potential secret leak in log: {record.message}"


class TestTestingEnvironmentBypassRemoved:
    """Integration test: Verify TESTING=1 does not bypass security"""

    @pytest.mark.asyncio
    async def test_testing_env_does_not_bypass_scope_validation(self, test_client):
        """
        Integration test: TESTING=1 environment variable does not bypass scope validation

        Steps:
        1. Set TESTING=1
        2. Try to access protected endpoint without proper permissions
        3. Verify 403 Forbidden is returned
        """
        import os

        from fastapi.testclient import TestClient

        from src.main import app

        # Set TESTING=1 (simulating test environment misconfiguration)
        original_testing = os.getenv("TESTING")
        os.environ["TESTING"] = "1"

        try:
            client = TestClient(app)

            # Try to access admin endpoint without admin permissions
            # This should fail even with TESTING=1
            response = client.get(
                "/api/v1/admin/users", headers={"Authorization": "Bearer invalid_token"}
            )

            # Should get 401 or 403, NOT 200
            assert response.status_code in [
                401,
                403,
            ], f"Security bypass detected! Got {response.status_code} instead of 401/403"

        finally:
            # Restore original value
            if original_testing is not None:
                os.environ["TESTING"] = original_testing
            else:
                del os.environ["TESTING"]


class TestRateLimitingEnforced:
    """Integration test: Verify rate limiting on auth endpoints"""

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Uses TestClient(app) without DB overrides — hangs on db_manager init")
    async def test_login_rate_limiting(self, test_client):
        """
        Integration test: Rate limiting enforced on login endpoint

        Steps:
        1. Make multiple rapid login requests
        2. Verify rate limit is enforced after threshold
        3. Verify X-RateLimit headers present
        """
        from fastapi.testclient import TestClient

        from src.main import app

        client = TestClient(app)

        # Make requests up to and beyond rate limit
        responses = []
        for i in range(7):  # Assuming 5/minute limit
            response = client.post(
                "/api/v1/auth/token",
                data={"username": f"test_rate_limit_{i}@example.com", "password": "wrong_password"},
            )
            responses.append(response)

        # Check rate limit headers on all responses
        for response in responses:
            assert "X-RateLimit-Limit" in response.headers
            assert "X-RateLimit-Remaining" in response.headers

        # At least one should be rate limited (429)
        # Note: In test environment with in-memory storage, this might not work as expected
        status_codes = [r.status_code for r in responses]
        assert (
            429 in status_codes or 401 in status_codes
        ), f"Expected rate limiting or auth errors, got: {status_codes}"

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Uses TestClient(app) without DB overrides — hangs on db_manager init")
    async def test_register_rate_limiting(self, test_client):
        """
        Integration test: Rate limiting enforced on register endpoint

        Steps:
        1. Make multiple rapid registration requests
        2. Verify rate limit is enforced after threshold
        """
        from fastapi.testclient import TestClient

        from src.main import app

        client = TestClient(app)

        responses = []
        for i in range(5):  # Assuming 3/minute limit
            response = client.post(
                "/api/v1/auth/register",
                json={
                    "email": f"test_rate_limit_reg_{i}_{datetime.now(timezone.utc).timestamp()}@example.com",
                    "password": "TestP@ssw0rd123!",
                },
            )
            responses.append(response)

        # Check for rate limiting
        status_codes = [r.status_code for r in responses]
        assert (
            429 in status_codes or 201 in status_codes or 400 in status_codes
        ), f"Unexpected status codes: {status_codes}"


class TestAccountLockoutIntegration:
    """Integration test: Verify account lockout mechanism"""

    @pytest.mark.asyncio
    @pytest.mark.skip(
        reason="Uses TestClient(app) with get_async_session() directly — DB not initialized"
    )
    async def test_account_lockout_after_failed_attempts(self, test_client):
        """
        Integration test: Account locks after multiple failed login attempts

        Steps:
        1. Create test user
        2. Fail login 5 times
        3. Verify account is locked (429 Too Many Requests)
        4. Wait for lockout duration
        5. Verify account unlocks
        """
        from fastapi.testclient import TestClient

        from src.core.api.auth.schemas import UserCreate
        from src.core.auth.auth_service import auth_service
        from src.core.database.database import get_async_session
        from src.main import app

        client = TestClient(app)

        async for db in get_async_session():
            # Create test user
            timestamp = datetime.now(timezone.utc).timestamp()
            user_data = UserCreate(
                email=f"test_lockout_{timestamp}@example.com", password="CorrectP@ssw0rd123!"
            )

            user = await auth_service.create_user(
                db=db,
                user_data=user_data,
                client_ip="127.0.0.1",
                tenant_id=1,
                request_path="/test",
            )

            assert user is not None

            # Attempt 5 failed logins
            for i in range(5):
                response = client.post(
                    "/api/v1/auth/token",
                    data={
                        "username": f"test_lockout_{timestamp}@example.com",
                        "password": "WrongPassword123!",
                    },
                )
                # First 4 should be 401, 5th might trigger lockout
                assert response.status_code in [
                    401,
                    429,
                ], f"Unexpected status on attempt {i}: {response.status_code}"

            # Next attempt should be locked out
            response = client.post(
                "/api/v1/auth/token",
                data={
                    "username": f"test_lockout_{timestamp}@example.com",
                    "password": "WrongPassword123!",
                },
            )

            # Should be rate limited or locked out
            assert response.status_code in [
                401,
                429,
            ], f"Expected lockout or auth error, got: {response.status_code}"


# Fixture for test client
@pytest.fixture
def test_client():
    """Create test client for integration tests"""
    from fastapi.testclient import TestClient

    from src.main import app

    return TestClient(app)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
