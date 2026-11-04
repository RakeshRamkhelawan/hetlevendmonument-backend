"""
Unit Tests for Redis Connection

Verifies Redis client factory and basic connectivity.

Part of SA-2.1 implementation.

2026-09-27 (week-1 herstel): de tests patchten de hele `redis`-module met een
MagicMock, waardoor ook `redis.ConnectionError` een MagicMock werd --
`raise redis.ConnectionError(...)` gaf dan `TypeError: exceptions must derive
from BaseException` zodra de code de fouttak bereikte (wat altijd gebeurde,
want `client.ping()` op een MagicMock is niet awaitable). Nu: echte
ConnectionError behouden en de client is een AsyncMock met awaitbare ping().
"""

import redis as real_redis
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _patched_redis() -> tuple[MagicMock, AsyncMock]:
    """Return (contextmanager-gepatchte-module, mock_pool, mock_client).

    Behoudt de echte redis.ConnectionError zodat de fouttak in
    get_redis_client een echte exception kan raisen.
    """
    mock_pool = MagicMock()
    mock_pool.disconnect = AsyncMock()
    mock_client = AsyncMock()
    return mock_pool, mock_client


@pytest.mark.asyncio
async def test_redis_client_creation():
    """Test that get_redis_client returns a Redis client."""
    from src.core.database.redis import close_redis, get_redis_client

    # Mock the redis module to avoid actual connection
    with patch("src.core.database.redis.redis") as mock_redis:
        mock_redis.ConnectionError = real_redis.ConnectionError
        mock_pool, mock_client = _patched_redis()
        mock_redis.ConnectionPool.from_url.return_value = mock_pool
        mock_redis.Redis.return_value = mock_client

        # Reset global pool
        import src.core.database.redis as redis_module

        redis_module._redis_pool = None

        client = await get_redis_client()

        # Verify pool was created
        mock_redis.ConnectionPool.from_url.assert_called_once()
        # Verify client was created with pool
        mock_redis.Redis.assert_called_once_with(connection_pool=mock_pool)
        assert client == mock_client

        await close_redis()


@pytest.mark.asyncio
async def test_redis_pool_reuse():
    """Test that the connection pool is reused across calls."""
    with patch("src.core.database.redis.redis") as mock_redis:
        mock_redis.ConnectionError = real_redis.ConnectionError
        mock_pool, mock_client = _patched_redis()
        mock_redis.ConnectionPool.from_url.return_value = mock_pool
        mock_redis.Redis.return_value = mock_client

        import src.core.database.redis as redis_module

        redis_module._redis_pool = None

        # First call creates pool
        await redis_module.get_redis_client()
        # Second call reuses pool
        await redis_module.get_redis_client()

        # Pool should only be created once
        assert mock_redis.ConnectionPool.from_url.call_count == 1

        await redis_module.close_redis()


@pytest.mark.asyncio
async def test_close_redis():
    """Test that close_redis properly disconnects the pool."""
    with patch("src.core.database.redis.redis") as mock_redis:
        mock_redis.ConnectionError = real_redis.ConnectionError
        mock_pool, mock_client = _patched_redis()
        mock_redis.ConnectionPool.from_url.return_value = mock_pool
        mock_redis.Redis.return_value = AsyncMock()

        import src.core.database.redis as redis_module

        redis_module._redis_pool = None

        # Create pool
        await redis_module.get_redis_client()

        # Close pool
        await redis_module.close_redis()

        mock_pool.disconnect.assert_called_once()
        assert redis_module._redis_pool is None
