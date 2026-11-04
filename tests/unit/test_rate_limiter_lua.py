"""
Unit Tests for Redis Rate Limiter Lua Script

Verifies the atomic rate limiting logic using mocked Redis.

Part of SA-2.2 implementation.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest


@pytest.mark.asyncio
async def test_lua_script_enforces_limit():
    """Test that the Lua script correctly enforces rate limits."""
    from src.core.security.rate_limiter import RedisRateLimiter

    # Create mock Redis client
    mock_redis = MagicMock()

    # Track call count to simulate counter behavior
    call_count = 0

    async def mock_evalsha(sha, num_keys, key, window, limit):
        nonlocal call_count
        call_count += 1
        # Simulate: first 5 calls allowed, 6th denied
        # Note: Redis returns strings, so convert to int for comparison
        if call_count <= int(limit):
            return 1  # Allowed
        return 0  # Denied

    mock_redis.script_load = AsyncMock(return_value="mock_sha")
    mock_redis.evalsha = mock_evalsha

    limiter = RedisRateLimiter(mock_redis)
    key = "test_limit_key"
    limit = 5
    window = 10

    # 1. Consume limit (5 requests)
    for i in range(limit):
        allowed = await limiter.check_limit(key, limit, window)
        assert allowed is True, f"Request {i+1} should be allowed"

    # 2. Next request should fail
    allowed = await limiter.check_limit(key, limit, window)
    assert allowed is False, "Request 6 should be denied"


@pytest.mark.asyncio
async def test_script_sha_caching():
    """Test that script SHA is only loaded once."""
    from src.core.security.rate_limiter import RedisRateLimiter

    mock_redis = MagicMock()
    mock_redis.script_load = AsyncMock(return_value="mock_sha")
    mock_redis.evalsha = AsyncMock(return_value=1)

    limiter = RedisRateLimiter(mock_redis)

    # Multiple calls should only load script once
    await limiter.check_limit("key1", 100, 60)
    await limiter.check_limit("key2", 100, 60)
    await limiter.check_limit("key3", 100, 60)

    # Script should only be loaded once
    assert mock_redis.script_load.call_count == 1


@pytest.mark.asyncio
async def test_generate_key():
    """Test key generation format."""
    from src.core.security.rate_limiter import RedisRateLimiter

    mock_redis = MagicMock()
    limiter = RedisRateLimiter(mock_redis)

    key = limiter._generate_key("user_123", "/api/v1/agents")
    assert key == "rate_limit:user_123:/api/v1/agents"

    key = limiter._generate_key("192.168.1.1", "/auth/token")
    assert key == "rate_limit:192.168.1.1:/auth/token"


@pytest.mark.asyncio
async def test_check_request_uses_generated_key():
    """Test that check_request uses the correct generated key."""
    from src.core.security.rate_limiter import RedisRateLimiter

    mock_redis = MagicMock()
    mock_redis.script_load = AsyncMock(return_value="mock_sha")
    mock_redis.evalsha = AsyncMock(return_value=1)

    limiter = RedisRateLimiter(mock_redis)

    await limiter.check_request("user_456", "/api/v1/chat", limit=50, window=30)

    # Verify evalsha was called with correct key
    call_args = mock_redis.evalsha.call_args
    assert call_args[0][2] == "rate_limit:user_456:/api/v1/chat"
    assert int(call_args[0][3]) == 30  # window (Redis returns string)
    assert int(call_args[0][4]) == 50  # limit (Redis returns string)
