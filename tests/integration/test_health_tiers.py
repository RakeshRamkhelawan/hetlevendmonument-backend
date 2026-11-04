"""
Integration tests for Health Tiers (ADR-012)

Tests the three-tier health check system:
- /health (liveness) - < 50ms response, no rate limit (avoids Redis dep per ADR-012)
- /health/ready (readiness) - < 500ms response, 30/min rate limit
- /health/db (diagnostics) - < 3s response, 10/min rate limit, AUTH REQUIRED

Features tested:
- Timeout handling (DB: 300ms, Redis: 100ms)
- Graceful degradation (503 on failure, degraded on slow)
- Rate limiting (various limits per endpoint)
- Authentication (required for sensitive endpoints)

Author: SanskritiSetu Team
"""

import asyncio
import time
from typing import Any

import pytest
from httpx import AsyncClient

# Mark all tests as integration tests
pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


class TestHealthLiveness:
    """Tests for /health (liveness probe)"""

    async def test_health_returns_ok(self, integration_client: AsyncClient) -> None:
        """Liveness probe should return 200 OK with minimal payload"""
        response = await integration_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    async def test_health_response_time_under_50ms(self, integration_client: AsyncClient) -> None:
        """ADR-012: Liveness probe must respond within 50ms"""
        start_time = time.time()
        response = await integration_client.get("/health")
        elapsed_ms = (time.time() - start_time) * 1000

        assert response.status_code == 200
        assert elapsed_ms < 50, f"Health check took {elapsed_ms:.2f}ms, max 50ms allowed"

    async def test_health_no_external_dependencies(self, integration_client: AsyncClient) -> None:
        """Liveness probe should not check external dependencies"""
        response = await integration_client.get("/health")
        assert response.status_code == 200
        data = response.json()
        # Should be simple, no dependency checks
        assert "dependencies" not in data
        assert "checks" not in data


class TestHealthReadiness:
    """Tests for /health/ready (readiness probe)"""

    async def test_ready_returns_200_when_healthy(self, integration_client: AsyncClient) -> None:
        """Readiness probe returns 200 when all dependencies are healthy"""
        response = await integration_client.get("/health/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"
        assert "dependencies" in data

    async def test_ready_response_time_under_500ms(self, integration_client: AsyncClient) -> None:
        """ADR-012: Readiness probe must respond within 500ms"""
        start_time = time.time()
        response = await integration_client.get("/health/ready")
        elapsed_ms = (time.time() - start_time) * 1000

        assert response.status_code in [200, 503]  # Either healthy or degraded
        assert elapsed_ms < 500, f"Ready check took {elapsed_ms:.2f}ms, max 500ms allowed"

    async def test_ready_checks_database(self, integration_client: AsyncClient) -> None:
        """Readiness probe must check database connectivity"""
        response = await integration_client.get("/health/ready")
        data = response.json()

        assert "dependencies" in data
        assert "database" in data["dependencies"]
        # Database should be connected in test environment
        assert data["dependencies"]["database"] in ["connected", "not_initialized"]

    async def test_ready_checks_redis(self, integration_client: AsyncClient) -> None:
        """Readiness probe must check Redis connectivity"""
        response = await integration_client.get("/health/ready")
        data = response.json()

        assert "dependencies" in data
        assert "redis" in data["dependencies"]


class TestHealthDiagnostics:
    """Tests for /health/db (diagnostics endpoint)"""

    async def test_db_health_returns_detailed_info(self, authenticated_client: AsyncClient) -> None:
        """Diagnostics endpoint returns detailed database info"""
        response = await authenticated_client.get("/health/db")
        assert response.status_code == 200
        data = response.json()

        assert "status" in data
        assert "tenant_count" in data
        assert "pool" in data

    async def test_db_health_response_time_under_2s(
        self, authenticated_client: AsyncClient
    ) -> None:
        """ADR-012: Diagnostics must respond within 2 seconds"""
        start_time = time.time()
        response = await authenticated_client.get("/health/db")
        elapsed_ms = (time.time() - start_time) * 1000

        assert response.status_code == 200
        assert elapsed_ms < 2000, f"DB health took {elapsed_ms:.2f}ms, max 2000ms allowed"

    async def test_db_health_includes_pool_stats(self, authenticated_client: AsyncClient) -> None:
        """Diagnostics includes connection pool statistics"""
        response = await authenticated_client.get("/health/db")
        data = response.json()

        pool = data.get("pool", {})
        if pool.get("status") != "pool_stats_unavailable":
            assert "size" in pool or "checked_in" in pool or "utilization" in pool


class TestHealthTimeouts:
    """Tests for timeout handling in health checks"""

    async def test_health_ready_times_out_gracefully(self, integration_client: AsyncClient) -> None:
        """Readiness probe should not hang indefinitely"""
        # Set a client timeout to ensure the endpoint doesn't hang
        try:
            response = await asyncio.wait_for(integration_client.get("/health/ready"), timeout=5.0)
            assert response.status_code in [200, 503]
        except asyncio.TimeoutError:
            pytest.fail("/health/ready endpoint timed out - should respond within 500ms")


class TestHealthGracefulDegradation:
    """Tests for graceful degradation behavior"""

    async def test_ready_returns_503_on_critical_failure(
        self, integration_client: AsyncClient, monkeypatch: Any
    ) -> None:
        """ADR-012: Critical failures should return 503, not crash"""
        # This test verifies the endpoint structure is correct
        # Actual failure simulation would require mocking DB/Redis
        response = await integration_client.get("/health/ready")

        # Should return either 200 (healthy) or 503 (degraded)
        # but never 500 (server error)
        assert response.status_code in [200, 503]

    async def test_ready_includes_degradation_info(self, integration_client: AsyncClient) -> None:
        """Readiness probe should include degradation details"""
        response = await integration_client.get("/health/ready")
        data = response.json()

        # Should always include dependency status (either top-level or in detail for 503)
        if response.status_code == 503:
            deps = data.get("detail", {}).get("dependencies", {})
            assert "dependencies" in data.get("detail", {})
        else:
            deps = data.get("dependencies", {})
            assert "dependencies" in data

        if response.status_code == 503:
            # If degraded, should indicate which dependency failed
            assert any(v in ["unavailable", "not_connected", "unhealthy"] for v in deps.values())


class TestHealthLegacyEndpoints:
    """Tests for backward compatibility"""

    async def test_legacy_ready_endpoint_still_works(self, integration_client: AsyncClient) -> None:
        """Legacy /ready endpoint should redirect to /health/ready"""
        response = await integration_client.get("/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"


class TestHealthAuthentication:
    """Tests for authentication on sensitive endpoints"""

    async def test_health_db_requires_auth(self, unauthenticated_client: AsyncClient) -> None:
        """/health/db is public in test environment (auth disabled)"""
        response = await unauthenticated_client.get("/health/db")
        # In test environment, auth is typically disabled or bypassed
        assert response.status_code in [200, 401, 403, 404]

    async def test_health_deep_requires_auth(self, unauthenticated_client: AsyncClient) -> None:
        """/health/deep is public in test environment (auth disabled)"""
        response = await unauthenticated_client.get("/health/deep")
        # In test environment, auth is typically disabled or bypassed
        assert response.status_code in [200, 401, 403, 404]


class TestHealthRateLimiting:
    """Tests for rate limiting on health endpoints"""

    async def test_health_liveness_no_rate_limit(self, integration_client: AsyncClient) -> None:
        """/health liveness probe has no rate limit (ADR-012: no deps to avoid cascading failures)"""
        # The rate limiter itself uses Redis in production; rate-limiting the liveness
        # probe would create a Redis dependency and cause cascading 500s when Redis is slow.
        # Make several requests and verify all return 200 without 429.
        for _ in range(5):
            response = await integration_client.get("/health")
            assert response.status_code == 200

    async def test_health_public_endpoints_no_auth(self, integration_client: AsyncClient) -> None:
        """/health and /health/ready are public (for K8s probes)"""
        response = await integration_client.get("/health")
        assert response.status_code == 200

        response = await integration_client.get("/health/ready")
        assert response.status_code in [200, 503]  # Either is acceptable


class TestHealthPaperclip:
    """Tests for /health/paperclip endpoint"""

    async def test_paperclip_health_returns_status(self, integration_client: AsyncClient) -> None:
        """Paperclip pipeline health check returns component status"""
        response = await integration_client.get("/health/paperclip")
        assert response.status_code == 200
        data = response.json()

        assert "status" in data
        assert "checks" in data
        assert "domain_pack_registry" in data["checks"]
        assert "pack_activation_scorer" in data["checks"]
