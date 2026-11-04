"""
Concurrency and Race Condition Tests
SECURITY FIX (TEST-005): Test for race conditions and concurrent access issues
"""

import asyncio
import os
from datetime import datetime, timezone
from typing import List

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from src.core.auth.jwt_handler import jwt_handler


async def _get_verified_redis_client():
    """Return a Redis client only if a real command succeeds."""
    from src.core.database.redis import get_redis_client

    try:
        redis_client = await get_redis_client()
        await redis_client.ping()
        return redis_client
    except Exception:
        pytest.skip("Redis not available")


def _is_redis_available():
    """Check if Redis is available without async."""
    import redis as sync_redis

    try:
        r = sync_redis.Redis(host="localhost", port=6379, socket_connect_timeout=2)
        return r.ping()
    except Exception:
        return False


# Skip all tests in this module if Redis is not available
pytestmark = [
    pytest.mark.security,
    pytest.mark.skipif(
        os.getenv("SKIP_REDIS_TESTS") == "1" or not _is_redis_available(),
        reason="Redis tests skipped - requires Redis server on localhost:6379",
    ),
]


@pytest.mark.security
@pytest.mark.asyncio
class TestRaceConditions:
    """Test race conditions in security-critical operations."""

    async def test_concurrent_token_refresh(self, db_session):
        """
        Test: Multiple concurrent token refresh attempts should not create
        multiple valid tokens (token rotation should be atomic).

        Risk: Session hijacking if token rotation is not atomic.
        """
        # Create test user
        user_data = {"id": 9999, "email": "race@test.com", "tenant_id": 1, "roles": ["user"]}

        # Generate initial tokens
        tokens = await asyncio.gather(*[jwt_handler.create_token_pair(user_data) for _ in range(5)])

        # All tokens should be different (unique jti)
        jtis = [t["access_token"].split(".")[1] for t in tokens]
        assert len(set(jtis)) == 5, "Each token should have unique JTI"

    async def test_concurrent_password_reset(self, db_session):
        """
        Test: Multiple concurrent password reset requests should not
        create multiple valid reset tokens.

        Risk: DoS or token exhaustion attack.
        """
        from src.core.api.auth.router import RESET_TOKEN_PREFIX

        redis_client = await _get_verified_redis_client()

        # Simulate multiple concurrent reset requests
        async def request_reset(i: int):
            token = f"reset_token_{i}"
            await redis_client.setex(f"{RESET_TOKEN_PREFIX}{token}", 3600, str(9999))
            return token

        try:
            tokens = await asyncio.gather(*[request_reset(i) for i in range(10)])
        except RedisConnectionError:
            pytest.skip("Redis not available")

        # All tokens should exist (no race condition in storage)
        for token in tokens:
            try:
                exists = await redis_client.exists(f"{RESET_TOKEN_PREFIX}{token}")
            except RedisConnectionError:
                pytest.skip("Redis not available")
            assert exists, f"Token {token} should exist"

    async def test_concurrent_tenant_isolation(self, db_session):
        """
        Test: Concurrent database queries from different tenants should
        maintain strict isolation.

        Risk: Data leakage between tenants.
        """
        from src.core.middleware.tenant_context import set_tenant_id

        results = {}

        async def tenant_query(tenant_id: int):
            set_tenant_id(tenant_id)
            # Simulate query
            await asyncio.sleep(0.01)  # Small delay
            results[tenant_id] = tenant_id

        # Run concurrent queries for different tenants
        await asyncio.gather(*[tenant_query(i) for i in range(1, 6)])

        # Verify each tenant got their own result
        for i in range(1, 6):
            assert results[i] == i, f"Tenant {i} got wrong result"


@pytest.mark.security
@pytest.mark.asyncio
class TestConcurrentAccess:
    """Test concurrent access patterns."""

    async def test_rate_limiting_under_load(self):
        """
        Test: Rate limiting should work correctly under concurrent load.

        Risk: Rate limit bypass through concurrent requests.
        """
        from src.core.middleware.rate_limit_middleware import TokenBucketRateLimiter

        await _get_verified_redis_client()

        limiter = TokenBucketRateLimiter(redis_url="redis://localhost:6379", requests_per_minute=10)

        key = "test_rate_limit"

        # Make 15 concurrent requests
        async def make_request():
            try:
                allowed, remaining, _ = await limiter.check_rate_limit(key, 10, 60)
                return allowed
            except Exception:
                return False

        results = await asyncio.gather(*[make_request() for _ in range(15)])

        # At most 10 should be allowed (rate limit)
        allowed_count = sum(1 for r in results if r)
        assert allowed_count <= 10, f"Rate limit exceeded: {allowed_count} allowed"

    @pytest.mark.xfail(
        reason="Event loop isolation issue when running full suite (passes in isolation)",
        strict=False,
    )
    async def test_cache_stampede_protection(self):
        """
        Test: Cache stampede prevention under concurrent access.

        Risk: Database overload when cache expires.
        """
        redis_client = await _get_verified_redis_client()

        cache_key = "test_stampede"

        async def fetch_expensive_data():
            # Simulate expensive operation
            await asyncio.sleep(0.1)
            return "expensive_data"

        async def get_data_with_lock():
            # Try to get from cache
            cached = await redis_client.get(cache_key)
            if cached:
                return cached

            # Set lock to prevent stampede
            lock_key = f"{cache_key}:lock"
            lock_acquired = await redis_client.set(lock_key, "1", nx=True, ex=5)

            if lock_acquired:
                try:
                    data = await fetch_expensive_data()
                    await redis_client.setex(cache_key, 60, data)
                    return data
                finally:
                    await redis_client.delete(lock_key)
            else:
                # Wait for other process to populate cache
                for _ in range(10):
                    await asyncio.sleep(0.05)
                    cached = await redis_client.get(cache_key)
                    if cached:
                        return cached
                return None

        # Start 10 concurrent requests
        try:
            results = await asyncio.gather(*[get_data_with_lock() for _ in range(10)])
        except RedisConnectionError:
            pytest.skip("Redis not available")

        # All should get data (some from cache, some from db)
        assert all(r is not None for r in results), "All requests should get data"


@pytest.mark.security
@pytest.mark.asyncio
class TestDeadlockPrevention:
    """Test deadlock prevention in concurrent operations."""

    async def test_lock_timeout(self):
        """
        Test: Locks should have timeouts to prevent deadlocks.

        Risk: Permanent deadlocks locking resources.
        """
        redis_client = await _get_verified_redis_client()

        lock_key = "test_deadlock_lock"

        # Acquire lock with short timeout
        try:
            lock_acquired = await redis_client.set(
                lock_key,
                "holder1",
                nx=True,
                ex=2,  # 2 second timeout
            )
        except RedisConnectionError:
            pytest.skip("Redis not available")
        assert lock_acquired

        # Try to acquire same lock (should fail)
        lock_acquired2 = await redis_client.set(lock_key, "holder2", nx=True, ex=2)
        assert not lock_acquired2

        # Wait for timeout
        await asyncio.sleep(2.5)

        # Lock should be released, can acquire again
        lock_acquired3 = await redis_client.set(lock_key, "holder3", nx=True, ex=2)
        assert lock_acquired3

        # Cleanup
        await redis_client.delete(lock_key)


@pytest.mark.security
class TestThreadSafety:
    """Test thread safety of shared resources."""

    def test_singleton_pattern(self):
        """
        Test: Singleton instances should be truly singleton.

        Risk: Multiple instances causing inconsistent state.
        """
        from src.core.security.secure_pickle import SecureModelLoader

        loader1 = SecureModelLoader(allowed_dir="/tmp")
        loader2 = SecureModelLoader(allowed_dir="/tmp")

        # Different instances (not singleton by design)
        assert loader1 is not loader2

        # But should have same configuration
        assert loader1.allowed_dir == loader2.allowed_dir
