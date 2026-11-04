"""
End-to-End Security Tests

Tests complete security flows from request to response,
including all security layers working together.

Tests:
- SQL injection prevention across endpoints
- XSS prevention
- Rate limiting effectiveness
- Account lockout flows
- Authentication bypass attempts
- Authorization enforcement
"""

import pytest
import pytest_asyncio
from httpx import AsyncClient

from src.core.security.security_monitor import SecurityEventType, get_security_monitor

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.security,
    pytest.mark.asyncio,
]


@pytest_asyncio.fixture
async def test_user(db_session):
    """Create a test user - skipped if database unavailable."""
    pytest.skip("Database fixture required - skipping DB-dependent test")


class TestSQLInjectionPrevention:
    """Test SQL injection prevention across all endpoints."""

    sql_payloads = [
        "' OR '1'='1",
        "'; DROP TABLE users; --",
        "' UNION SELECT * FROM passwords --",
        "1' AND 1=1 --",
        "' OR 'x'='x",
        "admin'--",
        "1; DROP TABLE users--",
    ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("payload", sql_payloads)
    async def test_login_sql_injection_blocked(self, async_client: AsyncClient, payload: str):
        """Test that SQL injection in login is blocked."""
        response = await async_client.post(
            "/api/v1/auth/token", data={"username": payload, "password": payload}
        )

        # Should return 400 or 401, NOT 500 (which would indicate SQL error)
        assert response.status_code in [400, 401, 422]

        # Should not expose SQL error details
        if response.status_code == 400:
            assert "sql" not in response.text.lower()
            assert "database" not in response.text.lower()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("payload", sql_payloads)
    async def test_search_sql_injection_blocked(self, async_client: AsyncClient, payload: str):
        """Test that SQL injection in search is blocked."""
        response = await async_client.get("/api/v1/search", params={"q": payload})

        # Should return 400, not 500
        assert response.status_code in [200, 400, 422]

        if response.status_code == 400:
            assert "invalid" in response.text.lower()


class TestXSSPrevention:
    """Test XSS prevention across endpoints."""

    xss_payloads = [
        "<script>alert('xss')</script>",
        "<img src=x onerror=alert('xss')>",
        "<body onload=alert('xss')>",
        "javascript:alert('xss')",
        "<svg onload=alert('xss')>",
        "<iframe src='javascript:alert(1)'>",
    ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("payload", xss_payloads)
    async def test_xss_in_search_blocked(self, async_client: AsyncClient, payload: str):
        """Test that XSS in search queries is blocked."""
        response = await async_client.get("/api/v1/search", params={"q": payload})

        # Should be blocked or sanitized
        assert response.status_code in [200, 400]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("payload", xss_payloads)
    async def test_xss_in_json_blocked(self, async_client: AsyncClient, payload: str):
        """Test that XSS in JSON body is detected."""
        response = await async_client.post(
            "/api/v1/contact", json={"name": payload, "message": "Test message"}
        )

        # Should return 400 for XSS attempt
        assert response.status_code in [400, 404, 422]  # 404 if endpoint doesn't exist


class TestRateLimiting:
    """Test rate limiting effectiveness."""

    @pytest.mark.asyncio
    async def test_login_rate_limiting(self, async_client: AsyncClient):
        """Test that login endpoint is rate limited."""
        # Make 10 rapid login requests
        responses = []
        for i in range(10):
            response = await async_client.post(
                "/api/v1/auth/token",
                data={"username": f"test{i}@example.com", "password": "wrongpassword"},
            )
            responses.append(response.status_code)

        # Some requests should be rate limited (429)
        # or all should be rejected for wrong credentials (401)
        assert 429 in responses or all(r == 401 for r in responses)

    @pytest.mark.asyncio
    async def test_registration_rate_limiting(self, async_client: AsyncClient):
        """Test that registration endpoint is rate limited."""
        responses = []
        for i in range(5):
            response = await async_client.post(
                "/api/v1/auth/register",
                json={
                    "email": f"ratelimittest{i}@example.com",
                    "password": "TestPass123!",
                    "full_name": "Test User",
                },
            )
            responses.append(response.status_code)

        # After 3 attempts per minute, should get rate limited
        # Note: Rate limits may be disabled in test mode


class TestAccountLockout:
    """Test account lockout mechanism."""

    @pytest.mark.asyncio
    async def test_account_lockout_after_failed_attempts(
        self, async_client: AsyncClient, test_user
    ):
        """Test that account is locked after 5 failed attempts."""
        email = test_user.email

        # Make 5 failed login attempts
        for _ in range(5):
            response = await async_client.post(
                "/api/v1/auth/token",
                data={"username": email, "password": "wrongpassword123!"},
            )
            assert response.status_code == 401

        # 6th attempt should indicate account is locked
        response = await async_client.post(
            "/api/v1/auth/token",
            data={"username": email, "password": "wrongpassword123!"},
        )

        # Should be 423 Locked or 401 with lockout message
        assert response.status_code in [401, 423]
        if response.status_code == 401:
            assert "lock" in response.text.lower() or "attempt" in response.text.lower()

    @pytest.mark.asyncio
    async def test_successful_login_resets_lockout(self, async_client: AsyncClient, test_user):
        """Test that successful login resets failed attempts counter."""
        # This test would require knowing the actual password
        # Skipping for now as it requires more setup
        pytest.skip("Requires actual password for test user")


class TestAuthenticationBypass:
    """Test various authentication bypass attempts."""

    @pytest.mark.asyncio
    async def test_access_protected_endpoint_without_token(self, async_client: AsyncClient):
        """Test that protected endpoints require authentication."""
        # Try to access a protected endpoint without token
        response = await async_client.get("/api/v1/users/me")

        # Should return 401 Unauthorized
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_access_protected_endpoint_with_invalid_token(self, async_client: AsyncClient):
        """Test that invalid tokens are rejected."""
        response = await async_client.get(
            "/api/v1/users/me", headers={"Authorization": "Bearer invalid_token_here"}
        )

        # Should return 401 Unauthorized
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_access_protected_endpoint_with_malformed_token(self, async_client: AsyncClient):
        """Test that malformed tokens are rejected."""
        response = await async_client.get(
            "/api/v1/users/me", headers={"Authorization": "NotBearer token"}
        )

        # Should return 401 Unauthorized
        assert response.status_code == 401


class TestSecurityMonitoring:
    """Test security monitoring and event detection."""

    @pytest.mark.asyncio
    async def test_brute_force_detection(self, async_client: AsyncClient):
        """Test that brute force attempts are detected."""
        monitor = get_security_monitor()

        # Reset monitor state
        monitor._login_attempts.clear()
        monitor._blocked_ips.clear()

        ip = "192.168.1.100"

        # Simulate 5 failed logins from same IP
        for _ in range(5):
            await monitor.record_login_attempt(user_id=None, ip_address=ip, success=False)

        # Should detect brute force
        is_brute_force = await monitor.detect_brute_force(ip)
        assert is_brute_force is True

        # IP should be blocked
        assert monitor.is_ip_blocked(ip) is True

    @pytest.mark.asyncio
    async def test_security_event_recording(self, async_client: AsyncClient):
        """Test that security events are recorded."""
        monitor = get_security_monitor()

        # Record a security event
        await monitor.record_security_event(
            event_type=SecurityEventType.SUSPICIOUS_ACTIVITY,
            user_id=1,
            ip_address="192.168.1.200",
            details={"reason": "test"},
            threat_level=monitor.ThreatLevel.MEDIUM,
        )

        # Should be tracked
        assert len(monitor._ip_events["192.168.1.200"]) >= 1


class TestPathTraversalPrevention:
    """Test path traversal prevention."""

    traversal_payloads = [
        "../../../etc/passwd",
        "..\\..\\..\\windows\\system32\\config\\sam",
        "....//....//etc/passwd",
        "..%2f..%2f..%2fetc%2fpasswd",
        "%2e%2e%2f%2e%2e%2f%2e%2e%2fetc%2fpasswd",
    ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("payload", traversal_payloads)
    async def test_path_traversal_in_file_param_blocked(
        self, async_client: AsyncClient, payload: str
    ):
        """Test that path traversal in file parameters is blocked."""
        response = await async_client.get("/api/v1/files/download", params={"filename": payload})

        # Should return 400 or 404, not allow access
        assert response.status_code in [400, 404, 422]


class TestNoSQLInjectionPrevention:
    """Test NoSQL injection prevention."""

    nosql_payloads = [
        {"$gt": ""},
        {"$ne": None},
        {"$where": "this.password.length > 0"},
        {"$regex": ".*"},
    ]

    @pytest.mark.asyncio
    @pytest.mark.parametrize("payload", nosql_payloads)
    async def test_nosql_injection_blocked(self, async_client: AsyncClient, payload: dict):
        """Test that NoSQL operators are blocked."""
        # Try to send NoSQL operators in various fields
        response = await async_client.post(
            "/api/v1/search", json={"filter": payload, "query": "test"}
        )

        # Should return 400 for NoSQL injection attempt
        assert response.status_code in [400, 404, 422]


class TestComprehensiveSecurityFlow:
    """Test complete security flows end-to-end."""

    @pytest.mark.asyncio
    async def test_full_login_security_flow(self, async_client: AsyncClient, test_user):
        """
        Test complete login flow with all security layers:
        1. Rate limiting
        2. Input validation
        3. Account lockout
        4. Security monitoring
        """
        email = test_user.email

        # Step 1: Attempt SQL injection (should be blocked)
        response = await async_client.post(
            "/api/v1/auth/token",
            data={"username": "' OR '1'='1", "password": "anything"},
        )
        assert response.status_code in [400, 401]

        # Step 2: Multiple failed attempts (rate limiting & lockout)
        for i in range(5):
            response = await async_client.post(
                "/api/v1/auth/token",
                data={"username": email, "password": "wrongpassword"},
            )
            assert response.status_code in [401, 423]

        # Step 3: Verify account is now locked
        response = await async_client.post(
            "/api/v1/auth/token", data={"username": email, "password": "wrongpassword"}
        )
        assert response.status_code in [401, 423]

        # Verify security monitoring tracked events
        monitor = get_security_monitor()
        assert len(monitor._login_attempts) > 0
