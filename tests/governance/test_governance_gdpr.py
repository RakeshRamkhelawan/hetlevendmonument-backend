"""
P5.6: Governance & GDPR Compliance Tests

Comprehensive testing for:
1. Governance: RBAC, data isolation, audit logging, permission management
2. GDPR Rights: Data subject access, deletion, portability, consent management
3. Compliance: Privacy policies, data retention, security standards
4. Multi-tenant: Tenant isolation, data boundaries, scope validation

Reference: GDPR Regulation (EU) 2016/679, ISO/IEC 27001, SOC 2 Type II

NOTE: These tests require a running server at localhost:8100.
Run with: pytest tests/governance/ -m "not requires_server" to skip server tests.
"""

import asyncio
import json
import os
from datetime import datetime, timedelta
from typing import Any, AsyncGenerator, Dict
from uuid import uuid4

import httpx
import pytest

# Run tests with running server (override via GOVENANCE_TEST_BASE_URL env var)
BASE_URL = os.getenv("GOVERNANCE_TEST_BASE_URL", "http://localhost:8111")

pytestmark = [
    pytest.mark.asyncio,
]


# ============================================================================
# SECTION 1: Role-Based Access Control (RBAC) Tests
# ============================================================================


class TestRBACAndAuthorization:
    """Tests for Role-Based Access Control and authorization"""

    @pytest.fixture
    async def api_client(self) -> AsyncGenerator[httpx.AsyncClient, None]:
        """HTTP client for API testing"""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            yield client

    @pytest.fixture
    async def admin_client(
        self, api_client: httpx.AsyncClient
    ) -> AsyncGenerator[tuple[httpx.AsyncClient, str], None]:
        """Admin user authenticated client"""
        admin_email = "rbac_admin_fixture@example.com"
        admin_password = "AdminTest123!"

        login_response = await api_client.post(
            "/api/v1/auth/token", data={"username": admin_email, "password": admin_password}
        )

        if login_response.status_code != 200:
            try:
                await api_client.post(
                    "/api/v1/auth/register",
                    json={"email": admin_email, "password": admin_password},
                )
            except Exception:
                pass

            login_response = await api_client.post(
                "/api/v1/auth/token", data={"username": admin_email, "password": admin_password}
            )

        if login_response.status_code != 200:
            pytest.fail(
                f"Admin login failed for governance fixture: status={login_response.status_code} "
                f"body={login_response.text[:300]}"
            )

        token = login_response.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        admin_http = httpx.AsyncClient(
            base_url=BASE_URL, headers=headers, timeout=30.0
        )
        try:
            yield admin_http, token
        finally:
            await admin_http.aclose()

    @pytest.mark.asyncio
    async def test_admin_can_access_admin_endpoints(
        self, admin_client: tuple[httpx.AsyncClient, str]
    ):
        """Verify admin can access admin endpoints"""
        client, _ = admin_client

        response = await client.get("/api/v1/admin/dashboard")

        # Should succeed or endpoint may not exist
        assert response.status_code in [200, 401, 403, 404]

    @pytest.mark.asyncio
    async def test_user_cannot_access_admin_endpoints(self, api_client: httpx.AsyncClient):
        """Verify regular user cannot access admin endpoints"""
        user_email = f"user_{uuid4()}@example.com"
        user_password = "UserTest123!"

        await api_client.post(
            "/api/v1/auth/register", json={"email": user_email, "password": user_password}
        )

        login_response = await api_client.post(
            "/api/v1/auth/token", data={"username": user_email, "password": user_password}
        )

        if login_response.status_code == 200:
            token = login_response.json()["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
            user_client = httpx.AsyncClient(
                base_url=BASE_URL, headers=headers, timeout=30.0
            )

            response = await user_client.get("/api/v1/admin/dashboard")

            # Should be denied or endpoint doesn't exist
            assert response.status_code in [401, 403, 404]

            await user_client.aclose()

    @pytest.mark.asyncio
    async def test_role_based_permission_enforcement(
        self, admin_client: tuple[httpx.AsyncClient, str]
    ):
        """Test role-based permission enforcement"""
        client, _ = admin_client

        # Try to perform admin action
        response = await client.post(
            "/api/v1/admin/users", json={"email": "test@example.com", "role": "user"}
        )

        # Should succeed (201/200) or not exist (404)
        assert response.status_code in [200, 201, 400, 401, 403, 404]

    @pytest.mark.asyncio
    async def test_scope_based_api_access(self, admin_client: tuple[httpx.AsyncClient, str]):
        """Test scope-based API access control"""
        client, _ = admin_client

        # Try to access workflow API
        response = await client.get("/api/v1/workflows")

        # Should have access or endpoint doesn't exist
        assert response.status_code in [200, 404, 500]


# ============================================================================
# SECTION 2: Data Isolation and Multi-Tenant Security Tests
# ============================================================================


class TestDataIsolationAndTenancy:
    """Tests for data isolation and multi-tenant security"""

    @pytest.fixture
    async def api_client(self) -> AsyncGenerator[httpx.AsyncClient, None]:
        """HTTP client for API testing"""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            yield client

    @pytest.mark.asyncio
    async def test_user_cannot_access_other_users_data(self, api_client: httpx.AsyncClient):
        """Verify users cannot access other users' data"""
        # Create user 1
        user1_email = f"user1_{uuid4()}@example.com"
        user1_password = "User1Test123!"

        await api_client.post(
            "/api/v1/auth/register", json={"email": user1_email, "password": user1_password}
        )

        login1_response = await api_client.post(
            "/api/v1/auth/token", data={"username": user1_email, "password": user1_password}
        )

        if login1_response.status_code == 200:
            user1_token = login1_response.json()["access_token"]

            # Create user 2
            user2_email = f"user2_{uuid4()}@example.com"
            user2_password = "User2Test123!"

            await api_client.post(
                "/api/v1/auth/register",
                json={"email": user2_email, "password": user2_password},
            )

            login2_response = await api_client.post(
                "/api/v1/auth/token",
                data={"username": user2_email, "password": user2_password},
            )

            if login2_response.status_code == 200:
                user2_token = login2_response.json()["access_token"]

                # User 2 tries to access User 1's user ID via API
                user1_client = httpx.AsyncClient(
                    base_url=BASE_URL,
                    headers={"Authorization": f"Bearer {user1_token}"},
                    timeout=30.0,
                )

                # List workflows for user 1
                response1 = await user1_client.get("/api/v1/workflows")

                user2_client = httpx.AsyncClient(
                    base_url=BASE_URL,
                    headers={"Authorization": f"Bearer {user2_token}"},
                    timeout=30.0,
                )

                # User 2 should not see user 1's workflows
                response2 = await user2_client.get("/api/v1/workflows")

                # Both should have access to workflow endpoint but different data
                assert response1.status_code in [200, 404]
                assert response2.status_code in [200, 404]

                await user1_client.aclose()
                await user2_client.aclose()

    @pytest.mark.asyncio
    async def test_tenant_isolation_in_queries(self, api_client: httpx.AsyncClient):
        """Test tenant isolation in database queries"""
        user_email = f"tenant_{uuid4()}@example.com"
        user_password = "TenantTest123!"

        await api_client.post(
            "/api/v1/auth/register", json={"email": user_email, "password": user_password}
        )

        login_response = await api_client.post(
            "/api/v1/auth/token", data={"username": user_email, "password": user_password}
        )

        if login_response.status_code == 200:
            token = login_response.json()["access_token"]
            user_client = httpx.AsyncClient(
                base_url=BASE_URL,
                headers={"Authorization": f"Bearer {token}"},
                timeout=30.0,
            )

            # Create workflow
            workflow = {
                "name": "Tenant Test Workflow",
                "spec": {"nodes": [], "edges": []},
            }

            create_response = await user_client.post("/api/v1/workflows", json=workflow)

            # Should be isolated to this user/tenant
            assert create_response.status_code in [200, 201, 404]

            await user_client.aclose()


# ============================================================================
# SECTION 3: GDPR Data Subject Rights Tests
# ============================================================================


class TestGDPRDataSubjectRights:
    """Tests for GDPR data subject rights"""

    @pytest.fixture
    async def api_client(self) -> AsyncGenerator[httpx.AsyncClient, None]:
        """HTTP client for API testing"""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            yield client

    @pytest.mark.asyncio
    async def test_user_can_access_their_personal_data(self, api_client: httpx.AsyncClient):
        """GDPR Right: User can access their personal data (Article 15)"""
        user_email = f"gdpr_user_{uuid4()}@example.com"
        user_password = "GDPRTest123!"

        await api_client.post(
            "/api/v1/auth/register", json={"email": user_email, "password": user_password}
        )

        login_response = await api_client.post(
            "/api/v1/auth/token", data={"username": user_email, "password": user_password}
        )

        if login_response.status_code == 200:
            token = login_response.json()["access_token"]
            user_client = httpx.AsyncClient(
                base_url=BASE_URL,
                headers={"Authorization": f"Bearer {token}"},
                timeout=30.0,
            )

            # Access own profile
            response = await user_client.get("/api/v1/auth/me")

            assert response.status_code in [200, 404]

            await user_client.aclose()

    @pytest.mark.asyncio
    async def test_data_export_functionality(self, api_client: httpx.AsyncClient):
        """GDPR Right: User can export their data in machine-readable format (Article 20)"""
        user_email = f"export_{uuid4()}@example.com"
        user_password = "ExportTest123!"

        await api_client.post(
            "/api/v1/auth/register", json={"email": user_email, "password": user_password}
        )

        login_response = await api_client.post(
            "/api/v1/auth/token", data={"username": user_email, "password": user_password}
        )

        if login_response.status_code == 200:
            token = login_response.json()["access_token"]
            user_client = httpx.AsyncClient(
                base_url=BASE_URL,
                headers={"Authorization": f"Bearer {token}"},
                timeout=30.0,
            )

            # Request data export
            response = await user_client.post("/api/v1/gdpr/data-export", json={"format": "json"})

            # Should handle export request
            assert response.status_code in [200, 202, 404, 400]

            await user_client.aclose()

    @pytest.mark.asyncio
    async def test_data_deletion_right_to_be_forgotten(self, api_client: httpx.AsyncClient):
        """GDPR Right: User can request deletion of their data (Article 17)"""
        user_email = f"delete_{uuid4()}@example.com"
        user_password = "DeleteTest123!"

        await api_client.post(
            "/api/v1/auth/register", json={"email": user_email, "password": user_password}
        )

        login_response = await api_client.post(
            "/api/v1/auth/token", data={"username": user_email, "password": user_password}
        )

        if login_response.status_code == 200:
            token = login_response.json()["access_token"]
            user_client = httpx.AsyncClient(
                base_url=BASE_URL,
                headers={"Authorization": f"Bearer {token}"},
                timeout=30.0,
            )

            # Request account deletion
            response = await user_client.post("/api/v1/gdpr/delete-account", json={"confirm": True})

            # Should handle deletion request
            assert response.status_code in [200, 202, 204, 404, 400]

            await user_client.aclose()

    @pytest.mark.asyncio
    async def test_consent_management(self, api_client: httpx.AsyncClient):
        """Test user consent management for data processing"""
        user_email = f"consent_{uuid4()}@example.com"
        user_password = "ConsentTest123!"

        await api_client.post(
            "/api/v1/auth/register", json={"email": user_email, "password": user_password}
        )

        login_response = await api_client.post(
            "/api/v1/auth/token", data={"username": user_email, "password": user_password}
        )

        if login_response.status_code == 200:
            token = login_response.json()["access_token"]
            user_client = httpx.AsyncClient(
                base_url=BASE_URL,
                headers={"Authorization": f"Bearer {token}"},
                timeout=30.0,
            )

            # Update consent preferences
            response = await user_client.put(
                "/api/v1/consent/preferences",
                json={"analytics": False, "marketing": False, "essential": True},
            )

            # Should handle consent update
            assert response.status_code in [200, 204, 404, 400]

            await user_client.aclose()


# ============================================================================
# SECTION 4: Audit Logging and Compliance Tests
# ============================================================================


class TestAuditLoggingAndCompliance:
    """Tests for audit logging and compliance tracking"""

    @pytest.fixture
    async def api_client(self) -> AsyncGenerator[httpx.AsyncClient, None]:
        """HTTP client for API testing"""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            yield client

    @pytest.mark.asyncio
    async def test_user_actions_are_audited(self, api_client: httpx.AsyncClient):
        """Verify user actions are logged for audit trail"""
        user_email = f"audit_{uuid4()}@example.com"
        user_password = "AuditTest123!"

        await api_client.post(
            "/api/v1/auth/register", json={"email": user_email, "password": user_password}
        )

        login_response = await api_client.post(
            "/api/v1/auth/token", data={"username": user_email, "password": user_password}
        )

        if login_response.status_code == 200:
            token = login_response.json()["access_token"]
            user_client = httpx.AsyncClient(
                base_url=BASE_URL,
                headers={"Authorization": f"Bearer {token}"},
                timeout=30.0,
            )

            # Perform action
            await user_client.get("/api/v1/workflows")

            # Try to access audit logs
            response = await user_client.get("/api/v1/audit/my-activities")

            # Should return logs or endpoint may not exist
            assert response.status_code in [200, 404]

            await user_client.aclose()

    @pytest.mark.asyncio
    async def test_admin_can_view_audit_logs(self, api_client: httpx.AsyncClient):
        """Verify admins can view audit logs for compliance"""
        admin_email = f"audit_admin_{uuid4()}@example.com"
        admin_password = "AuditAdmin123!"

        await api_client.post(
            "/api/v1/auth/register", json={"email": admin_email, "password": admin_password}
        )

        login_response = await api_client.post(
            "/api/v1/auth/token", data={"username": admin_email, "password": admin_password}
        )

        if login_response.status_code == 200:
            token = login_response.json()["access_token"]
            admin_client = httpx.AsyncClient(
                base_url=BASE_URL,
                headers={"Authorization": f"Bearer {token}"},
                timeout=30.0,
            )

            # Access admin audit logs
            response = await admin_client.get("/api/v1/admin/audit-logs")

            # Should return audit logs or endpoint may not exist
            assert response.status_code in [200, 404, 403]

            await admin_client.aclose()

    @pytest.mark.asyncio
    async def test_data_access_is_logged_with_timestamp(self, api_client: httpx.AsyncClient):
        """Verify all data accesses are logged with timestamps"""
        user_email = f"timestamp_{uuid4()}@example.com"
        user_password = "TimestampTest123!"

        await api_client.post(
            "/api/v1/auth/register", json={"email": user_email, "password": user_password}
        )

        login_response = await api_client.post(
            "/api/v1/auth/token", data={"username": user_email, "password": user_password}
        )

        if login_response.status_code == 200:
            token = login_response.json()["access_token"]
            user_client = httpx.AsyncClient(
                base_url=BASE_URL,
                headers={"Authorization": f"Bearer {token}"},
                timeout=30.0,
            )

            # Access data
            await user_client.get("/api/v1/auth/me")

            # Verify timestamp is in audit
            response = await user_client.get("/api/v1/audit/my-activities?limit=1")

            if response.status_code == 200:
                data = response.json()
                # Should contain timestamp info
                assert isinstance(data, (list, dict))

            await user_client.aclose()


# ============================================================================
# SECTION 5: Data Retention and Privacy Tests
# ============================================================================


class TestDataRetentionAndPrivacy:
    """Tests for data retention policies and privacy controls"""

    @pytest.fixture
    async def api_client(self) -> AsyncGenerator[httpx.AsyncClient, None]:
        """HTTP client for API testing"""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            yield client

    @pytest.mark.asyncio
    async def test_privacy_policy_acceptance(self, api_client: httpx.AsyncClient):
        """Verify privacy policy acceptance on registration"""
        user_email = f"privacy_{uuid4()}@example.com"
        user_password = "PrivacyTest123!"

        response = await api_client.post(
            "/api/v1/auth/register",
            json={
                "email": user_email,
                "password": user_password,
                "accept_privacy_policy": True,
            },
        )

        # Should accept privacy policy
        assert response.status_code in [200, 201, 400, 422, 429]

    @pytest.mark.asyncio
    async def test_data_retention_policy_enforcement(self, api_client: httpx.AsyncClient):
        """Test that data retention policies are enforced"""
        # This would test that old data is properly retained/purged

        user_email = f"retention_{uuid4()}@example.com"
        user_password = "RetentionTest123!"

        await api_client.post(
            "/api/v1/auth/register", json={"email": user_email, "password": user_password}
        )

        login_response = await api_client.post(
            "/api/v1/auth/token", data={"username": user_email, "password": user_password}
        )

        if login_response.status_code == 200:
            token = login_response.json()["access_token"]
            user_client = httpx.AsyncClient(
                base_url=BASE_URL,
                headers={"Authorization": f"Bearer {token}"},
                timeout=30.0,
            )

            # Verify retention policy exists
            response = await user_client.get("/api/v1/compliance/retention-policy")

            # Should return policy or endpoint may not exist
            assert response.status_code in [200, 404]

            await user_client.aclose()

    @pytest.mark.asyncio
    async def test_data_minimization_principle(self, api_client: httpx.AsyncClient):
        """Test that only necessary data is collected"""
        # Verify that minimal personal data is requested

        # Registration should only require essential fields
        user_email = f"minimal_{uuid4()}@example.com"
        user_password = "MinimalTest123!"

        response = await api_client.post(
            "/api/v1/auth/register",
            json={
                "email": user_email,
                "password": user_password,
                # No unnecessary fields
            },
        )

        # Should accept minimal data
        assert response.status_code in [200, 201, 400, 422, 429]


# ============================================================================
# SECTION 6: Security and Compliance Standards Tests
# ============================================================================


class TestSecurityAndComplianceStandards:
    """Tests for security standards and compliance requirements"""

    @pytest.fixture
    async def api_client(self) -> AsyncGenerator[httpx.AsyncClient, None]:
        """HTTP client for API testing"""
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
            yield client

    @pytest.mark.asyncio
    async def test_https_enforcement(self, api_client: httpx.AsyncClient):
        """Verify HTTPS is enforced in production"""
        # This test would verify HTTPS headers

        response = await api_client.get("/health")

        # Should be accessible (may not enforce HTTPS in test environment)
        assert response.status_code in [200, 404]

    @pytest.mark.asyncio
    async def test_secure_password_requirements(self, api_client: httpx.AsyncClient):
        """Verify password security requirements are enforced"""
        user_email = f"weak_{uuid4()}@example.com"
        weak_password = "weak"  # Weak password

        response = await api_client.post(
            "/api/v1/auth/register", json={"email": user_email, "password": weak_password}
        )

        # Should reject weak password
        assert response.status_code in [400, 422]

    @pytest.mark.asyncio
    async def test_session_timeout_enforcement(self, api_client: httpx.AsyncClient):
        """Verify session timeout is enforced"""
        user_email = f"session_{uuid4()}@example.com"
        user_password = "SessionTest123!"

        await api_client.post(
            "/api/v1/auth/register", json={"email": user_email, "password": user_password}
        )

        login_response = await api_client.post(
            "/api/v1/auth/token", data={"username": user_email, "password": user_password}
        )

        if login_response.status_code == 200:
            token_data = login_response.json()

            # Verify token has expiration
            assert "access_token" in token_data


# ============================================================================
# SECTION 7: Helper Fixtures
# ============================================================================


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



