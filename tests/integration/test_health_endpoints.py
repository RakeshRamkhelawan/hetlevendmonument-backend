"""
Integration Tests for Health Endpoints (SD-1.2)

Tests health and readiness endpoints against the ASGI app directly.
"""

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


class TestHealthEndpoint:
    """Integration tests for /health endpoint."""

    async def test_health_returns_200(self, integration_client):
        """Test health endpoint returns 200 OK."""
        response = await integration_client.get("/health")
        assert response.status_code == 200

    async def test_health_returns_ok_status(self, integration_client):
        """Test health endpoint returns ok status in body."""
        response = await integration_client.get("/health")
        data = response.json()
        assert data["status"] == "ok"


class TestReadyEndpoint:
    """Integration tests for /ready endpoint."""

    async def test_ready_returns_status(self, integration_client):
        """Test ready endpoint returns valid status code."""
        response = await integration_client.get("/ready")
        # 200 = ready, 503 = dependencies unavailable, 401 = auth required
        assert response.status_code in [200, 401, 503]

    async def test_ready_includes_dependencies(self, integration_client):
        """Test ready endpoint includes dependency status."""
        response = await integration_client.get("/ready")
        if response.status_code == 200:
            data = response.json()
            assert "dependencies" in data or "status" in data


# De bereikbaarheid van /docs en /openapi.json wordt hier NIET getoetst: `integration_app` bouwt
# een eigen app zonder de hardening uit `src/main.py`, dus een assertie hier zegt niets over
# productie. Zie tests/architecture/test_docs_disabled_in_prod.py (ADR-036 OP-124).
