"""
Test: B-003b/B-003c/B-004 Infrastructure configuration fixes.
Verifies docker-compose.dev.yml, Dockerfile, and entrypoint script.
"""

import pytest
import yaml
from pathlib import Path


@pytest.mark.unit
class TestDockerComposeDevConfig:
    """B-003c: docker-compose.dev.yml must have start_period=60s and depends_on conditions."""

    def test_backend_start_period_is_60s(self) -> None:
        compose_path = Path("docker-compose.dev.yml")
        compose = yaml.safe_load(compose_path.read_text())
        backend = compose["services"]["backend"]
        assert backend["healthcheck"]["start_period"] == "60s"

    def test_backend_depends_on_has_conditions(self) -> None:
        compose_path = Path("docker-compose.dev.yml")
        compose = yaml.safe_load(compose_path.read_text())
        backend = compose["services"]["backend"]
        deps = backend["depends_on"]
        assert isinstance(deps, dict)
        assert deps["postgres"]["condition"] == "service_healthy"
        assert deps["redis"]["condition"] == "service_healthy"


@pytest.mark.unit
class TestDockerfileHealthcheck:
    """B-004: Dockerfile healthcheck must use port 8000 (container internal)."""

    def test_dev_healthcheck_uses_port_8000(self) -> None:
        dockerfile_path = Path("Dockerfile")
        content = dockerfile_path.read_text()
        # Find the development stage healthcheck
        dev_section = content.split("FROM worker-base AS development")[1]
        assert "localhost:8000/health" in dev_section
        assert "localhost:8110/health" not in dev_section


@pytest.mark.unit
class TestEntrypointRedisWait:
    """B-003b: entrypoint-dev.sh must wait for Redis before starting."""

    def test_entrypoint_contains_redis_wait(self) -> None:
        entrypoint_path = Path("scripts/entrypoint-dev.sh")
        content = entrypoint_path.read_text()
        assert "redis-cli" in content
        assert "redis_wait" in content
        assert "Redis ready" in content

    def test_entrypoint_redis_wait_has_timeout(self) -> None:
        entrypoint_path = Path("scripts/entrypoint-dev.sh")
        content = entrypoint_path.read_text()
        assert "redis_max_wait=30" in content
