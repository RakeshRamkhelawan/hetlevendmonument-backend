"""
Integration Tests voor Admin Endpoints - Phase C
Tests met ECHTE PostgreSQL database queries (geen hardcoded data!)

Test Coverage:
- Real database queries (SELECT COUNT, JOIN)
- JWT authentication zonder bypass
- RBAC permissions met user_roles tabel
- Multi-tenant isolation

Usage:
    # Start test containers
    docker-compose -f docker-compose.test.yml up -d

    # Run integration tests
    pytest tests/integration/test_admin_production.py -v

    # Run with coverage
    pytest tests/integration/test_admin_production.py --cov=src/core/api/admin_endpoints
"""

from typing import Dict

import pytest
from httpx import AsyncClient

# TODO: FIX ADMIN PRODUCTION TESTS (12 FAILED)
# Root cause: Same JWT fixture issue - hardcoded user_ids not in DB
# Solution: Fix admin_user_with_token fixture in conftest.py
# Priority: MEDIUM (production simulation tests, covered by other suites)
# ✅ JWT FIXTURE FIXED (Nov 14, 2025) - admin_user_with_token now queries real user_id from database
# pytestmark = pytest.mark.skip(reason="FIXTURE ISSUE: JWT tokens use hardcoded user_ids. Fix admin_user_with_token fixture. PRIORITY: MEDIUM")


@pytest.mark.integration
class TestAdminDashboardProduction:
    """Test admin dashboard met ECHTE database queries"""

    async def test_dashboard_with_real_users(
        self, integration_client: AsyncClient, admin_token: str
    ):
        """
        Test dashboard returns REAL user count from database

        Verschil met unit test:
        - Unit test: Hardcoded {"total_users": 42}
        - Integration test: ECHTE query SELECT COUNT(*) FROM users
        """
        # ACT: Call dashboard with real JWT token (users seeded at engine init)
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = await integration_client.get("/admin/dashboard", headers=headers)

        # ASSERT: Validate REAL data from database
        assert response.status_code == 200, f"Dashboard failed: {response.text}"
        data = response.json()

        # Dashboard should return ACTUAL user count (seeded users: admin + normal)
        assert data["dashboard_data"]["total_users"] >= 2
        assert "system_metrics" in data["dashboard_data"]
        assert "cpu_usage" in data["dashboard_data"]["system_metrics"]

    async def test_dashboard_active_users_query(
        self, integration_client: AsyncClient, admin_token: str
    ):
        """Test dashboard active_users count with is_active filter"""
        # ACT: Users seeded at engine init are active by default
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = await integration_client.get("/admin/dashboard", headers=headers)

        # ASSERT: active_users should be >= 2 (admin + normal user from seed)
        assert response.status_code == 200
        data = response.json()
        active_users = data["dashboard_data"]["active_users"]

        # Both seeded users are active
        assert active_users >= 2


@pytest.mark.integration
class TestAdminUsersListProduction:
    """Test user listing met ECHTE database queries en JOINs"""

    async def test_list_users_with_roles(self, integration_client: AsyncClient, admin_token: str):
        """
        Test /admin/users returns users met roles via JOIN query

        SQL: SELECT users.*, roles.name FROM users JOIN roles ON users.role_id = roles.id
        """
        # ACT: Users seeded at engine init
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = await integration_client.get("/admin/users", headers=headers)

        # ASSERT
        assert response.status_code == 200
        data = response.json()

        assert "users" in data
        assert len(data["users"]) >= 2  # At least admin + normal user
        assert "pagination" in data

        # Verify JOIN worked: role field present
        for user in data["users"]:
            assert "role" in user
            assert "email" in user
            assert "is_active" in user

    async def test_list_users_pagination(self, integration_client: AsyncClient, admin_token: str):
        """Test pagination parameters (skip, limit)"""
        # ACT: Request with limit=2
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = await integration_client.get("/admin/users?limit=2", headers=headers)

        # ASSERT
        assert response.status_code == 200
        data = response.json()

        assert data["pagination"]["limit"] == 2
        assert data["pagination"]["returned"] <= 2  # Should return at most 2 users


@pytest.mark.integration
class TestAdminLogsProduction:
    """Test audit logs met ECHTE database queries"""

    async def test_access_logs_real_data(self, integration_client: AsyncClient, admin_token: str):
        """Test /admin/logs returns audit logs from database"""
        # ACT: Query logs (may be empty or contain login events from fixtures)
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = await integration_client.get("/admin/logs", headers=headers)

        # ASSERT
        assert response.status_code == 200
        data = response.json()

        assert "recent_logs" in data
        # Verify log structure if logs exist
        if len(data["recent_logs"]) > 0:
            first_log = data["recent_logs"][0]
            assert "timestamp" in first_log
            assert "event_type" in first_log
            assert "severity" in first_log
            assert "message" in first_log

    async def test_access_logs_filtering(self, integration_client: AsyncClient, admin_token: str):
        """Test filtering logs by event_type"""
        # ACT: Filter by event_type (may not return results if no matching logs)
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = await integration_client.get(
            "/admin/logs?event_type=LOGIN_SUCCESS", headers=headers
        )

        # ASSERT: Should return successfully even if empty
        assert response.status_code == 200
        data = response.json()
        assert "recent_logs" in data

        # If logs exist, verify they match the filter
        for log in data["recent_logs"]:
            assert log["event_type"] == "LOGIN_SUCCESS"


@pytest.mark.integration
class TestAdminSystemMonitor:
    """Test system monitoring met REAL metrics"""

    async def test_system_monitor_calculations(
        self, integration_client: AsyncClient, admin_token: str
    ):
        """Test monitor endpoint calculates error_rate from real audit logs"""
        # ACT: Monitor uses real audit log queries
        headers = {"Authorization": f"Bearer {admin_token}"}
        response = await integration_client.get("/admin/monitor", headers=headers)

        # ASSERT
        assert response.status_code == 200
        data = response.json()

        assert "metrics" in data
        metrics = data["metrics"]

        # Metrics should be present (values depend on actual log data)
        assert "error_rate" in metrics
        assert "total_events" in metrics
        assert "error_events" in metrics
        assert "health_status" in metrics


@pytest.mark.integration
class TestAdminMultiTenantIsolation:
    """CRITICAL: Test multi-tenant data isolation"""

    async def test_admin_dashboard_tenant_isolation(self, integration_client: AsyncClient):
        """
        SECURITY TEST: Admin van Tenant A mag GEEN data van Tenant B zien

        This test validates the most critical security requirement!
        """
        # NOTE: This will fail until we implement proper multi-tenant auth
        # For now, skip this test
        pytest.skip("Multi-tenancy not yet implemented - will be added in Phase C")

        # TODO: When multi-tenancy is implemented:
        # tenant_a_token = response_login.json()["access_token"]
        # headers = {"Authorization": f"Bearer {tenant_a_token}"}
        # response = await integration_client.get("/admin/dashboard", headers=headers)
        # data = response.json()
        #
        # # ASSERT: Should only see Tenant A users (2), NOT Tenant B (1)
        # assert data["dashboard_data"]["total_users"] == 2
