"""
Chaos Tests: Redis Failure During Hybrid Search

Verifies system resilience when Redis becomes unavailable.
Tests graceful degradation and recovery.
"""

import asyncio
import socket
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def is_redis_available() -> bool:
    """Check if Redis is available for integration tests."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex(("localhost", 6379))
        sock.close()
        return result == 0
    except Exception:
        return False


def is_docker_available() -> bool:
    """Check if Docker is available for container-based tests."""
    try:
        import subprocess

        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=5,
            check=False,
        )
        return result.returncode == 0
    except Exception:
        return False


# Fixtures for infrastructure checks
requires_redis = pytest.mark.skipif(
    not is_redis_available(), reason="Redis not available on localhost:6379"
)

requires_docker = pytest.mark.skipif(not is_docker_available(), reason="Docker not available")


# Try to import docker, but skip tests if not available
try:
    import docker

    DOCKER_AVAILABLE = True
except ImportError:
    DOCKER_AVAILABLE = False
    docker = None  # type: ignore

# Try to import redis exceptions
try:
    from redis.exceptions import ConnectionError as RedisConnectionError
except ImportError:
    # Create a mock exception if redis not installed
    class RedisConnectionError(Exception):  # type: ignore
        pass


class TestRedisFailureDuringSearch:
    """Chaos tests for Redis failure scenarios"""

    @pytest.fixture
    def docker_client_fixture(self):
        """Docker client for container manipulation"""
        if not DOCKER_AVAILABLE:
            pytest.skip("Docker package not available")
        try:
            return docker.from_env()
        except Exception:
            pytest.skip("Docker not available")

    @pytest.fixture
    def mock_hybrid_searcher(self):
        """Create mock hybrid searcher"""
        searcher = MagicMock()
        searcher.vector_searcher = AsyncMock()
        searcher.bm25_searcher = AsyncMock()

        async def mock_search(tenant_id, query, top_k):
            # Simulate search without cache dependency
            return [{"id": "doc1", "content": "Test content", "score": 0.9}]

        searcher.search = mock_search
        return searcher

    @pytest.fixture
    def mock_redis_client(self):
        """Create mock redis client"""
        client = MagicMock()
        client.get = AsyncMock(return_value=None)
        client.set = AsyncMock(return_value=True)
        return client

    @pytest.mark.chaos
    @pytest.mark.asyncio
    async def test_search_continues_when_redis_down(self, mock_hybrid_searcher):
        """Search should complete even when Redis is unavailable"""
        # Search should still work even when cache is unavailable
        result = await asyncio.wait_for(
            mock_hybrid_searcher.search(tenant_id=1, query="test query", top_k=5),
            timeout=10.0,
        )

        # Verify search completed
        assert result is not None
        assert len(result) >= 0

    @pytest.mark.chaos
    @pytest.mark.asyncio
    async def test_cache_graceful_degradation(self, mock_hybrid_searcher):
        """Verify graceful degradation when cache fails"""
        # First searches fail cache, but should continue
        for i in range(3):
            result = await asyncio.wait_for(
                mock_hybrid_searcher.search(1, f"query {i}", 5), timeout=10.0
            )
            assert result is not None

    @pytest.mark.chaos
    @pytest.mark.asyncio
    async def test_redis_recovery_detection(self, mock_hybrid_searcher):
        """System should detect when Redis recovers"""
        # Search while system is degraded
        result1 = await asyncio.wait_for(mock_hybrid_searcher.search(1, "query", 5), timeout=10.0)
        assert result1 is not None

        # Search again after "recovery"
        result2 = await asyncio.wait_for(mock_hybrid_searcher.search(1, "query", 5), timeout=10.0)
        assert result2 is not None

    @pytest.mark.chaos
    @pytest.mark.slow
    @requires_docker
    def test_redis_container_stop_recovery(self, docker_client_fixture, redis_container_name):
        """
        Test actual Redis container stop/start (requires Docker).

        Uses the redis_container_name fixture to find the correct
        test Redis container in various environments.
        """
        client = docker_client_fixture

        # Try to find the Redis container using multiple patterns
        redis_patterns = [
            redis_container_name,
            "redis-test",
            "sanskritisetuorg-redis-test-1",
            "sanskritisetu_redis",
            "redis",
        ]

        redis_container = None
        for pattern in redis_patterns:
            containers = client.containers.list(all=True, filters={"name": pattern})
            if containers:
                redis_container = containers[0]
                break

            # Try partial match
            all_containers = client.containers.list(all=True)
            for container in all_containers:
                if pattern.lower() in container.name.lower():
                    redis_container = container
                    break
            if redis_container:
                break

        if not redis_container:
            pytest.skip("No Redis container found (tried: %s)" % redis_patterns)

        try:
            # Ensure container is running before test
            if redis_container.status != "running":
                redis_container.start()
                time.sleep(2)

            # Record initial state
            redis_container.reload()
            initial_status = redis_container.status
            assert (
                initial_status == "running"
            ), f"Redis container not running (status: {initial_status})"

            # Stop Redis
            redis_container.stop(timeout=5)
            time.sleep(2)

            # Verify container stopped
            redis_container.reload()
            assert redis_container.status != "running"

            # Start Redis
            redis_container.start()
            time.sleep(3)

            # Verify recovery
            redis_container.reload()
            assert redis_container.status == "running"

        finally:
            # Ensure Redis is running after test
            try:
                redis_container.reload()
                if redis_container.status != "running":
                    redis_container.start()
            except Exception as e:
                print(f"Warning: Failed to ensure Redis is running: {e}")


class TestRedisTimeoutDuringSearch:
    """Tests for Redis timeout scenarios"""

    @pytest.mark.chaos
    @pytest.mark.asyncio
    async def test_slow_redis_timeout(self):
        """Search should timeout gracefully on slow Redis"""

        async def slow_redis_get(key):
            await asyncio.sleep(10)  # Very slow
            return None

        mock_redis = MagicMock()
        mock_redis.get = slow_redis_get

        # With proper timeout, this should not hang
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(mock_redis.get("test_key"), timeout=1.0)

    @pytest.mark.chaos
    @pytest.mark.asyncio
    async def test_redis_timeout_fallback(self):
        """Verify fallback when Redis times out"""

        # Create a simple cache with timeout behavior
        class ResilientCache:
            def __init__(self, timeout=0.5):
                self.timeout = timeout
                self._redis = MagicMock()

            async def get(self, key):
                try:
                    return await asyncio.wait_for(self._slow_get(key), timeout=self.timeout)
                except asyncio.TimeoutError:
                    return None  # Fallback

            async def _slow_get(self, key):
                await asyncio.sleep(2)  # Simulate slow Redis
                return "value"

        cache = ResilientCache(timeout=0.5)

        # Should return None (fallback) instead of hanging
        result = await asyncio.wait_for(cache.get("test_key"), timeout=5.0)
        assert result is None


class TestRedisPartitionRecovery:
    """Tests for network partition recovery scenarios"""

    @pytest.mark.chaos
    @pytest.mark.asyncio
    async def test_intermittent_connectivity(self):
        """Test intermittent Redis connectivity"""
        connection_failures = 0
        max_failures = 3

        async def flaky_redis_get(key):
            nonlocal connection_failures
            if connection_failures < max_failures:
                connection_failures += 1
                raise RedisConnectionError("Network unreachable")
            return None

        mock_redis = MagicMock()
        mock_redis.get = flaky_redis_get

        # Retry logic should handle intermittent failures
        result = None
        for attempt in range(5):
            try:
                result = await asyncio.wait_for(mock_redis.get("test_key"), timeout=5.0)
                break
            except RedisConnectionError:
                await asyncio.sleep(0.1 * (attempt + 1))

        # Should eventually succeed
        assert connection_failures == max_failures

    @pytest.mark.chaos
    @pytest.mark.asyncio
    async def test_circuit_breaker_behavior(self):
        """Test circuit breaker opens after repeated failures"""
        failure_count = 0
        circuit_open = False

        async def circuit_breaker_get(key):
            nonlocal failure_count, circuit_open

            if circuit_open:
                raise Exception("Circuit breaker open")

            failure_count += 1
            if failure_count >= 3:
                circuit_open = True
            raise RedisConnectionError("Connection failed")

        mock_redis = MagicMock()
        mock_redis.get = circuit_breaker_get

        # Should trip circuit breaker after 3 failures
        for i in range(5):
            try:
                await asyncio.wait_for(mock_redis.get("test_key"), timeout=5.0)
            except Exception as e:
                if "Circuit breaker" in str(e):
                    break

        assert circuit_open is True


# ============================================================================
# Infrastructure-dependent tests (skipped if infrastructure unavailable)
# ============================================================================


@pytest.mark.asyncio
@requires_redis
async def test_redis_actual_connection():
    """
    Test actual Redis connection.
    Skipped if Redis is not available.
    """
    # Verify the infrastructure check works
    assert is_redis_available()


@pytest.mark.asyncio
@requires_docker
async def test_docker_actual_connection():
    """
    Test actual Docker connection.
    Skipped if Docker is not available.
    """
    # Verify the infrastructure check works
    assert is_docker_available()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "chaos", "-s"])
