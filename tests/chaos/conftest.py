"""
Chaos Tests Configuration and Shared Fixtures

Provides Docker client fixture and utility functions for chaos testing.
Includes proper error handling and mock fallbacks when Docker is unavailable.
"""

import socket
import subprocess
from typing import AsyncGenerator, Generator, Optional
from unittest.mock import MagicMock

import pytest

# ============================================================================
# Docker Availability Checks
# ============================================================================


def is_docker_available() -> bool:
    """Check if Docker daemon is available and running."""
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=5,
            check=False,
        )
        return result.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return False


def is_docker_python_package_available() -> bool:
    """Check if docker Python package is installed."""
    try:
        import docker

        return True
    except ImportError:
        return False


def is_redis_available(host: str = "localhost", port: int = 6379) -> bool:
    """Check if Redis is available for integration tests."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except Exception:
        return False


# ============================================================================
# pytest Markers
# ============================================================================

requires_docker = pytest.mark.skipif(
    not is_docker_available(),
    reason="Docker daemon not available - start Docker Desktop",
)

requires_docker_package = pytest.mark.skipif(
    not is_docker_python_package_available(),
    reason="docker Python package not installed - run: pip install docker",
)

requires_redis = pytest.mark.skipif(
    not is_redis_available(),
    reason="Redis not available on localhost:6379",
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture(scope="session")
def docker_client() -> Generator:
    """
    Docker client fixture with proper error handling.

    Yields a docker.DockerClient if available, otherwise skips the test.
    Includes automatic cleanup after tests complete.

    Usage:
        def test_something(docker_client):
            containers = docker_client.containers.list()
            ...
    """
    if not is_docker_python_package_available():
        pytest.skip("docker Python package not installed - run: pip install docker")

    if not is_docker_available():
        pytest.skip("Docker daemon not available - start Docker Desktop")

    import docker
    from docker.errors import DockerException

    client: Optional[docker.DockerClient] = None
    try:
        client = docker.from_env()
        # Test connection
        client.ping()
        yield client
    except DockerException as e:
        pytest.skip(f"Docker connection failed: {e}")
    finally:
        if client:
            try:
                client.close()
            except Exception:
                pass  # Ignore cleanup errors


@pytest.fixture(scope="function")
def mock_docker_client():
    """
    Mock Docker client for tests that need Docker-like behavior without Docker.

    Returns a MagicMock that simulates Docker client behavior.
    Useful for unit tests that don't need actual container manipulation.
    """
    mock_client = MagicMock()

    # Setup mock containers
    mock_container = MagicMock()
    mock_container.name = "mock-redis"
    mock_container.status = "running"
    mock_container.id = "mock123"
    mock_container.short_id = "mock"

    mock_client.containers.list.return_value = [mock_container]
    mock_client.containers.get.return_value = mock_container

    return mock_client


@pytest.fixture(scope="function")
def redis_container_name() -> str:
    """
    Return the name of the Redis test container.

    Checks for common container names in order of preference:
    1. redis-test (standard test container)
    2. sanskritisetu-redis-test-1 (docker-compose test)
    3. sanskritisetu_redis (main project container)
    4. redis (generic)
    """
    common_names = [
        "redis-test",
        "sanskritisetuorg-redis-test-1",
        "sanskritisetu-redis-test-1",
        "sanskritisetu_redis",
        "redis",
    ]

    if not is_docker_available() or not is_docker_python_package_available():
        return "redis-test"  # Default fallback

    try:
        import docker

        client = docker.from_env()
        try:
            containers = client.containers.list(all=True)
            container_names = [c.name for c in containers]

            for name in common_names:
                if any(name in cname for cname in container_names):
                    return name

            # Return first redis-like container if found
            for cname in container_names:
                if "redis" in cname.lower():
                    return cname
        finally:
            client.close()
    except Exception:
        pass

    return "redis-test"  # Default fallback


@pytest.fixture(scope="function")
def get_test_container(docker_client):
    """
    Factory fixture to get a test container by name pattern.

    Returns a function that takes a name pattern and returns the matching
    container, or skips the test if not found.

    Usage:
        def test_something(get_test_container):
            redis = get_test_container("redis")
            redis.stop()
    """

    def _get_container(name_pattern: str):
        """Get container by name pattern."""
        try:
            containers = docker_client.containers.list(all=True, filters={"name": name_pattern})
            if containers:
                return containers[0]

            # Try partial match
            all_containers = docker_client.containers.list(all=True)
            for container in all_containers:
                if name_pattern.lower() in container.name.lower():
                    return container

            pytest.skip(f"No container found matching '{name_pattern}'")
        except Exception as e:
            pytest.skip(f"Failed to get container: {e}")

    return _get_container


# ============================================================================
# Test Utilities
# ============================================================================


class ContainerHelper:
    """Helper class for container operations in chaos tests."""

    def __init__(self, docker_client):
        self.client = docker_client

    def find_container(self, name_patterns: list) -> Optional:
        """Find container matching any of the given name patterns."""
        try:
            all_containers = self.client.containers.list(all=True)

            for pattern in name_patterns:
                # Exact match first
                for container in all_containers:
                    if pattern == container.name:
                        return container

                # Partial match
                for container in all_containers:
                    if pattern.lower() in container.name.lower():
                        return container

            return None
        except Exception:
            return None

    def safe_stop(self, container, timeout: int = 5) -> bool:
        """Safely stop a container, handling errors."""
        try:
            container.stop(timeout=timeout)
            return True
        except Exception as e:
            print(f"Warning: Failed to stop container: {e}")
            return False

    def safe_start(self, container) -> bool:
        """Safely start a container, handling errors."""
        try:
            container.start()
            return True
        except Exception as e:
            print(f"Warning: Failed to start container: {e}")
            return False


@pytest.fixture(scope="function")
def container_helper(docker_client):
    """Provide ContainerHelper instance."""
    return ContainerHelper(docker_client)


@pytest.fixture(scope="function")
async def integration_client() -> AsyncGenerator:
    """
    Async HTTP client for chaos tests against the running backend.

    Creates a lightweight httpx.AsyncClient pointing at localhost:8000.
    Tests using this fixture are skipped if the backend is not reachable.
    """
    try:
        import httpx
    except ImportError:
        pytest.skip("httpx not installed")

    # Quick connectivity check before yielding
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(2)
        result = sock.connect_ex(("localhost", 8000))
        sock.close()
        if result != 0:
            pytest.skip("Backend not available on localhost:8000")
    except Exception:
        pytest.skip("Backend not available on localhost:8000")

    async with httpx.AsyncClient(base_url="http://localhost:8000", timeout=30.0) as client:
        yield client
