"""Unit tests for Digital Twin Phase 3 Redis wiring.

Verifies that:
- TwinConsentManager uses Redis cache when available
- RedisRateLimiter uses Redis when available
- Graceful fallback when Redis is unavailable
"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.learning.consent.consent_manager import TwinConsentManager
from src.core.learning.rate_limiting.redis_rate_limiter import RedisRateLimiter


class FakeRedisWithPipeline:
    """Minimal fake Redis supporting pipeline for rate limiter tests."""

    def __init__(self):
        self._zsets: dict[str, dict[str, float]] = {}
        self.calls: list[dict] = []

    async def get(self, key: str) -> str | None:
        self.calls.append({"method": "get", "key": key})
        return None

    async def setex(self, key: str, seconds: int, value: str) -> bool:
        self.calls.append({"method": "setex", "key": key, "seconds": seconds, "value": value})
        return True

    async def delete(self, key: str) -> int:
        self.calls.append({"method": "delete", "key": key})
        return 1

    def pipeline(self):
        return FakePipeline(self)


class FakePipeline:
    """Fake Redis pipeline for rate limiter."""

    def __init__(self, redis: FakeRedisWithPipeline):
        self._redis = redis
        self._commands: list[tuple[str, tuple, dict]] = []

    def zremrangebyscore(self, key: str, min_score: float, max_score: float):
        self._commands.append(("zremrangebyscore", (key, min_score, max_score), {}))
        return self

    def zcard(self, key: str):
        self._commands.append(("zcard", (key,), {}))
        return self

    def zadd(self, key: str, mapping: dict[str, float]):
        self._commands.append(("zadd", (key, mapping), {}))
        return self

    def expire(self, key: str, seconds: int):
        self._commands.append(("expire", (key, seconds), {}))
        return self

    async def execute(self):
        results = []
        for cmd, args, kwargs in self._commands:
            if cmd == "zremrangebyscore":
                key, min_score, max_score = args
                if key in self._redis._zsets:
                    self._redis._zsets[key] = {
                        k: v for k, v in self._redis._zsets[key].items() if v > max_score
                    }
                results.append(0)
            elif cmd == "zcard":
                key = args[0]
                results.append(len(self._redis._zsets.get(key, {})))
            elif cmd == "zadd":
                key, mapping = args
                if key not in self._redis._zsets:
                    self._redis._zsets[key] = {}
                self._redis._zsets[key].update(mapping)
                results.append(len(mapping))
            elif cmd == "expire":
                results.append(1)
        return results


@pytest.mark.asyncio
async def test_consent_manager_uses_redis_cache(db_session: AsyncSession) -> None:
    """TwinConsentManager should cache consent status in Redis."""
    # Set tenant context so the ORM do_orm_execute hook (ADR-004) adds
    # AND 1=1 instead of AND 0=1 (fail-secure). Without this, _get_or_create_consent
    # always sees an empty SELECT result and tries to INSERT twice, hitting a
    # UNIQUE constraint on the second call when the hook is already registered
    # from a prior test in the suite.
    from src.core.database.tenant_query_filter import _bypass_tenant_filter

    bypass_token = _bypass_tenant_filter.set(True)
    try:
        fake_redis = FakeRedisWithPipeline()
        mgr = TwinConsentManager(db=db_session, cache=fake_redis)

        # First call via get_consent_status should hit DB and then cache
        # Default consent is disabled (GDPR opt-in)
        from src.core.learning.consent.consent_manager import TwinConsentStatus

        status = await mgr.get_consent_status("user_1", tenant_id=1)
        assert status == TwinConsentStatus.DISABLED

        # setex should have been called to populate cache with disabled status
        cache_calls = [c for c in fake_redis.calls if c["method"] == "setex"]
        assert len(cache_calls) == 1
        assert cache_calls[0]["key"] == "twin:consent:1:user_1"
        assert cache_calls[0]["value"] == "disabled"

        # is_tracking_enabled uses get_consent_categories (not cache), so it returns False
        enabled = await mgr.is_tracking_enabled("user_1", tenant_id=1)
        assert enabled is False
    finally:
        _bypass_tenant_filter.reset(bypass_token)


@pytest.mark.asyncio
async def test_rate_limiter_uses_redis() -> None:
    """RedisRateLimiter should use Redis for sliding window when available."""
    fake_redis = FakeRedisWithPipeline()
    limiter = RedisRateLimiter(redis_client=fake_redis)

    # First call should be allowed
    allowed = await limiter.is_allowed("user_1", "file_edit")
    assert allowed is True

    # Redis sorted set should have been populated
    assert "twin:rl:user_1:file_edit" in fake_redis._zsets


@pytest.mark.asyncio
async def test_rate_limiter_blocks_when_limit_exceeded() -> None:
    """RedisRateLimiter should block requests exceeding the limit."""
    fake_redis = FakeRedisWithPipeline()
    # Override limit to very low threshold for testing
    limiter = RedisRateLimiter(
        redis_client=fake_redis,
        limits={"default": (2, 60)},
    )

    # First 2 calls allowed
    assert await limiter.is_allowed("user_1", "file_edit") is True
    assert await limiter.is_allowed("user_1", "file_edit") is True

    # 3rd call should be blocked
    assert await limiter.is_allowed("user_1", "file_edit") is False


@pytest.mark.asyncio
async def test_rate_limiter_fail_open_when_redis_none() -> None:
    """RedisRateLimiter should allow all requests when Redis is None."""
    limiter = RedisRateLimiter(redis_client=None)

    for _ in range(100):
        assert await limiter.is_allowed("user_1", "file_edit") is True


@pytest.mark.asyncio
async def test_consent_manager_fallback_without_redis(db_session: AsyncSession) -> None:
    """TwinConsentManager should work without Redis (DB fallback)."""
    from src.core.database.tenant_query_filter import _bypass_tenant_filter

    bypass_token = _bypass_tenant_filter.set(True)
    try:
        mgr = TwinConsentManager(db=db_session, cache=None)
        enabled = await mgr.is_tracking_enabled("user_2", tenant_id=1)
        assert enabled is False
    finally:
        _bypass_tenant_filter.reset(bypass_token)
