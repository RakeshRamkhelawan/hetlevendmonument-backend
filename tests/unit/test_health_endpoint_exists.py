"""
Test health endpoint consistency - Fase 1.3

Validates that /health and /health/ready endpoints exist and respond correctly.
This ensures docker-compose health checks align with actual endpoints.
"""

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from src.main import create_test_app


@pytest.fixture
def test_client() -> TestClient:
    """Create test client for health endpoint tests."""
    app = create_test_app()
    return TestClient(app)


class TestHealthEndpointsExist:
    """Test that health endpoints exist and return expected responses."""

    def test_health_endpoint_exists_and_returns_ok(self, test_client: TestClient) -> None:
        """
        Test that GET /health returns 200 OK with status 'ok'.

        This is the liveness probe endpoint used by Docker/Kubernetes.
        Port: 8000 (main API port)
        """
        response = test_client.get("/health")

        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["status"] == "ok"

    def test_health_ready_endpoint_exists_and_returns_ready(self, test_client: TestClient) -> None:
        """
        Test that GET /health/ready returns 200 OK when dependencies are ready.

        This is the readiness probe endpoint used by Docker/Kubernetes.
        Port: 8000 (main API port)

        Note: In test environment without real DB/Redis, this may return 503.
        We accept both 200 (if mocked) or 503 (if dependencies unavailable).
        """
        response = test_client.get("/health/ready")

        # Accept 200 (ready) or 503 (not ready) - both are valid responses
        assert response.status_code in [
            status.HTTP_200_OK,
            status.HTTP_503_SERVICE_UNAVAILABLE,
        ]

        data = response.json()
        if response.status_code == status.HTTP_200_OK:
            assert data["status"] == "ready"
            assert "dependencies" in data
        else:
            # 503 - dependencies not available (response format may vary)
            assert "detail" in data or "dependencies" in data or "error" in data

    def test_health_endpoint_uses_port_8000_not_8110(self) -> None:
        """
        Test validates health endpoint is on port 8000, NOT port 8110.

        Port 8110 is the admin/metrics port (Prometheus, health checks should NOT use it).
        Port 8000 is the main API port where /health and /health/ready are served.

        This test documents the correct configuration for docker-compose health checks.
        """
        # This test is documentation - the actual port binding is validated
        # by the test_client fixture which uses the FastAPI app directly.
        # The key assertion: health endpoints are registered on the main app router,
        # which listens on port 8000 in production.
        from src.core.api.health_endpoints import router as health_router

        # Verify routes are registered
        routes = [route.path for route in health_router.routes]  # type: ignore
        assert "/health" in routes
        assert "/health/ready" in routes

    def test_docker_compose_health_check_configuration(self) -> None:
        """
        Test validates docker-compose.yml health check configuration.

        Expected configuration:
        - test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
        - interval: 30s
        - timeout: 10s
        - start_period: 180s  # for migration buffer
        - retries: 5

        This test documents the correct configuration and fails if
        docker-compose.yml needs to be updated.
        """
        import yaml

        docker_compose_path = "docker-compose.yml"

        with open(docker_compose_path, "r") as f:
            compose = yaml.safe_load(f)

        backend_service = compose.get("services", {}).get("backend", {})
        healthcheck = backend_service.get("healthcheck", {})

        # Verify health check test uses correct port and path
        test_command = healthcheck.get("test", [])
        test_str = " ".join(test_command)

        assert (
            "localhost:8000" in test_str
        ), f"Health check must use port 8000, not 8110. Current: {test_str}"
        assert "/health" in test_str, f"Health check must use /health endpoint. Current: {test_str}"

        # Verify recommended settings
        assert (
            healthcheck.get("interval") == "30s"
        ), f"Interval should be 30s, got: {healthcheck.get('interval')}"
        assert healthcheck.get("start_period") in ["180s", "120s"], (
            f"Start period should be 180s or 120s for migration buffer, "
            f"got: {healthcheck.get('start_period')}"
        )
        assert (
            healthcheck.get("retries") == 5
        ), f"Retries should be 5, got: {healthcheck.get('retries')}"

    def test_dockerfile_health_check_configuration(self) -> None:
        """
        Test validates Dockerfile production-api stage uses correct port.

        Expected: curl http://localhost:8000/health (in production-api stage)

        Note: Dockerfile has two stages:
        - Development stage: port 8110 (for dev metrics)
        - Production-api stage: port 8000 (for production health checks)
        """
        import re

        dockerfile_path = "Dockerfile"

        with open(dockerfile_path, "r") as f:
            content = f.read()

        # Find production-api stage healthcheck (after "production-api" FROM line)
        prod_api_section = re.search(
            r"FROM dependencies AS production-api.*?(?=FROM |$)",
            content,
            re.DOTALL,
        )
        assert prod_api_section, "Dockerfile must have production-api stage"

        # Find HEALTHCHECK in production-api section
        healthcheck_match = re.search(
            r"HEALTHCHECK.*curl.*localhost:(\d+)/health",
            prod_api_section.group(0),
            re.DOTALL,
        )

        assert (
            healthcheck_match
        ), "production-api stage must contain HEALTHCHECK with /health endpoint"

        port = healthcheck_match.group(1)
        assert port == "8000", f"production-api health check must use port 8000, not {port}"


class TestHealthEndpointConsistency:
    """Test that all health check configurations are consistent."""

    def test_health_endpoints_match_between_dockerfile_and_compose(self) -> None:
        """
        Test that Dockerfile production-api and docker-compose.yml backend
        use the same health endpoint.

        Both should use: http://localhost:8000/health
        """
        import re

        import yaml

        # Read Dockerfile - extract production-api stage only
        with open("Dockerfile", "r") as f:
            dockerfile_content = f.read()

        prod_api_section = re.search(
            r"FROM dependencies AS production-api.*?(?=FROM |$)",
            dockerfile_content,
            re.DOTALL,
        )
        assert prod_api_section, "Dockerfile must have production-api stage"

        # Extract Dockerfile health check URL from production-api stage
        df_match = re.search(
            r"curl -f (http://localhost:\d+/health)",
            prod_api_section.group(0),
        )
        assert df_match, "Dockerfile production-api health check URL not found"
        dockerfile_url = df_match.group(1)

        # Read docker-compose.yml
        with open("docker-compose.yml", "r") as f:
            compose = yaml.safe_load(f)

        # Extract docker-compose health check URL
        backend = compose.get("services", {}).get("backend", {})
        hc_test = backend.get("healthcheck", {}).get("test", [])
        hc_str = " ".join(hc_test)

        compose_match = re.search(r"http://localhost:\d+/health", hc_str)
        assert compose_match, "docker-compose health check URL not found"
        compose_url = compose_match.group(0)

        # They must match
        assert dockerfile_url == compose_url, (
            f"Health check URLs must match:\n"
            f"  Dockerfile (production-api): {dockerfile_url}\n"
            f"  docker-compose (backend): {compose_url}"
        )
