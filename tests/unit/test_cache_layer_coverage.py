"""
Comprehensive tests for src/core/caching/cache_layer.py
Coverage target: 100% of async caching layer
"""

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from src.core.caching.cache_layer import (
    AsyncCacheLayer,
    CacheConfig,
    cached,
    clear_cache,
    clear_cache_pattern,
    delete_cache,
    get_cache,
    get_cache_value,
    set_cache,
)


class TestCacheConfig:
    """Test CacheConfig dataclass"""

    def test_cache_config_defaults(self):
        """Test cache config default values"""
        config = CacheConfig()

        assert config.host == "localhost"
        assert config.port == 6379
        assert config.db == 0
        assert config.password is None
        assert config.socket_timeout == 5
        assert config.default_ttl == 3600
        assert config.max_connections == 10

    def test_cache_config_custom(self):
        """Test cache config custom values"""
        config = CacheConfig(
            host="redis-server", port=6380, db=1, password="secret", default_ttl=7200
        )

        assert config.host == "redis-server"
        assert config.port == 6380
        assert config.db == 1
        assert config.password == "secret"
        assert config.default_ttl == 7200


class TestAsyncCacheLayerInitialization:
    """Test AsyncCacheLayer initialization"""

    def test_initialization_default_config(self):
        """Test initialization with default config"""
        cache = AsyncCacheLayer()

        assert isinstance(cache.config, CacheConfig)
        assert cache.redis_client is None
        assert cache.connected is False

    def test_initialization_custom_config(self):
        """Test initialization with custom config"""
        config = CacheConfig(host="custom-host")
        cache = AsyncCacheLayer(config=config)

        assert cache.config == config
        assert cache.config.host == "custom-host"


class TestCacheConnection:
    """Test cache connection methods"""

    @pytest.mark.asyncio
    @patch("src.core.typing.create_async_redis_client")
    @patch("src.core.caching.cache_layer.get_settings")
    async def test_connect_success(self, mock_get_settings, mock_create_client):
        """Test successful cache connection.

        After cache_layer.py migration, connect() calls create_async_redis_client()
        from src.core.typing instead of redis.from_url() directly.
        """
        # Mock settings
        mock_settings = Mock()
        mock_settings.redis_url = "redis://localhost:6380"
        mock_get_settings.return_value = mock_settings

        # Mock the async redis client factory
        mock_client = AsyncMock()
        mock_client.ping = AsyncMock()
        mock_create_client.return_value = mock_client

        cache = AsyncCacheLayer()
        result = await cache.connect()

        assert result is True
        assert cache.connected is True
        assert cache.redis_client is not None
        mock_client.ping.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("src.core.caching.cache_layer.redis")
    @patch("src.core.caching.cache_layer.get_settings")
    async def test_connect_failure(self, mock_get_settings, mock_redis):
        """Test cache connection failure"""
        # Mock settings
        mock_settings = Mock()
        mock_settings.redis_url = "redis://localhost:6380  # Redis port updated from 6379 to 6380/0"
        mock_get_settings.return_value = mock_settings

        # STRUCTURAL FIX: Create real exception class for redis.ConnectionError
        # This prevents TypeError: catching classes that do not inherit from BaseException
        class MockRedisConnectionError(Exception):
            """Mock redis ConnectionError that properly inherits from BaseException"""

            pass

        # Configure mock redis module with proper exception class
        mock_redis.ConnectionError = MockRedisConnectionError
        mock_redis.from_url.side_effect = MockRedisConnectionError("Connection failed")

        cache = AsyncCacheLayer()
        result = await cache.connect()

        assert result is False
        assert cache.connected is False

    @pytest.mark.asyncio
    async def test_disconnect(self):
        """Test cache disconnection"""
        cache = AsyncCacheLayer()
        cache.redis_client = AsyncMock()
        cache.connected = True

        await cache.disconnect()

        cache.redis_client.aclose.assert_awaited_once()
        assert cache.connected is False


class TestCacheSet:
    """Test cache set method"""

    @pytest.mark.asyncio
    async def test_set_not_connected(self):
        """Test set when not connected"""
        cache = AsyncCacheLayer()
        cache.connected = False

        result = await cache.set("key1", "value1")

        assert result is False

    @pytest.mark.asyncio
    async def test_set_success(self):
        """Test successful cache set"""
        cache = AsyncCacheLayer()
        cache.connected = True
        cache.redis_client = AsyncMock()
        cache.redis_client.setex = AsyncMock(return_value=True)

        result = await cache.set("key1", "value1", ttl=300)

        assert result is True
        cache.redis_client.setex.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_set_default_ttl(self):
        """Test set with default TTL"""
        cache = AsyncCacheLayer()
        cache.connected = True
        cache.redis_client = AsyncMock()
        cache.redis_client.setex = AsyncMock(return_value=True)

        await cache.set("key1", "value1")

        # Verify default TTL was used
        call_args = cache.redis_client.setex.call_args
        assert call_args[0][1] == cache.config.default_ttl

    @pytest.mark.asyncio
    async def test_set_complex_value(self):
        """Test set with complex value"""
        cache = AsyncCacheLayer()
        cache.connected = True
        cache.redis_client = AsyncMock()
        cache.redis_client.setex = AsyncMock(return_value=True)

        complex_value = {"name": "test", "data": [1, 2, 3], "nested": {"key": "value"}}
        result = await cache.set("key1", complex_value)

        assert result is True

    @pytest.mark.asyncio
    async def test_set_serialization_failure(self):
        """Test set with non-serializable value"""
        cache = AsyncCacheLayer()
        cache.connected = True
        cache.redis_client = AsyncMock()

        # Create non-serializable object
        def non_serializable(x):
            return x

        result = await cache.set("key1", non_serializable)

        assert result is False


class TestCacheGet:
    """Test cache get method"""

    @pytest.mark.asyncio
    async def test_get_not_connected(self):
        """Test get when not connected"""
        cache = AsyncCacheLayer()
        cache.connected = False

        result = await cache.get("key1")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_success(self):
        """Test successful cache get"""
        cache = AsyncCacheLayer()
        cache.connected = True
        cache.redis_client = AsyncMock()
        cache.redis_client.get = AsyncMock(return_value=json.dumps("value1"))

        result = await cache.get("key1")

        assert result == "value1"
        cache.redis_client.get.assert_awaited_once_with("key1")

    @pytest.mark.asyncio
    async def test_get_miss(self):
        """Test cache miss"""
        cache = AsyncCacheLayer()
        cache.connected = True
        cache.redis_client = AsyncMock()
        cache.redis_client.get = AsyncMock(return_value=None)

        result = await cache.get("key1")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_complex_value(self):
        """Test get with complex value"""
        cache = AsyncCacheLayer()
        cache.connected = True
        complex_value = {"name": "test", "data": [1, 2, 3]}
        cache.redis_client = AsyncMock()
        cache.redis_client.get = AsyncMock(return_value=json.dumps(complex_value))

        result = await cache.get("key1")

        assert result == complex_value

    @pytest.mark.asyncio
    async def test_get_deserialization_failure(self):
        """Test get with invalid JSON"""
        cache = AsyncCacheLayer()
        cache.connected = True
        cache.redis_client = AsyncMock()
        cache.redis_client.get = AsyncMock(return_value="invalid json{")

        result = await cache.get("key1")

        assert result is None


class TestCacheDelete:
    """Test cache delete method"""

    @pytest.mark.asyncio
    async def test_delete_not_connected(self):
        """Test delete when not connected"""
        cache = AsyncCacheLayer()
        cache.connected = False

        result = await cache.delete("key1")

        assert result is False

    @pytest.mark.asyncio
    async def test_delete_success(self):
        """Test successful cache delete"""
        cache = AsyncCacheLayer()
        cache.connected = True
        cache.redis_client = AsyncMock()
        cache.redis_client.delete = AsyncMock(return_value=1)

        result = await cache.delete("key1")

        assert result is True
        cache.redis_client.delete.assert_awaited_once_with("key1")


class TestCacheExists:
    """Test cache exists method"""

    @pytest.mark.asyncio
    async def test_exists_not_connected(self):
        """Test exists when not connected"""
        cache = AsyncCacheLayer()
        cache.connected = False

        result = await cache.exists("key1")

        assert result is False

    @pytest.mark.asyncio
    async def test_exists_true(self):
        """Test exists returns true"""
        cache = AsyncCacheLayer()
        cache.connected = True
        cache.redis_client = AsyncMock()
        cache.redis_client.exists = AsyncMock(return_value=1)

        result = await cache.exists("key1")

        assert result is True

    @pytest.mark.asyncio
    async def test_exists_false(self):
        """Test exists returns false"""
        cache = AsyncCacheLayer()
        cache.connected = True
        cache.redis_client = AsyncMock()
        cache.redis_client.exists = AsyncMock(return_value=0)

        result = await cache.exists("key1")

        assert result is False


class TestCacheClearPattern:
    """Test cache clear_pattern method"""

    @pytest.mark.asyncio
    async def test_clear_pattern_not_connected(self):
        """Test clear_pattern when not connected"""
        cache = AsyncCacheLayer()
        cache.connected = False

        result = await cache.clear_pattern("prefix:*")

        assert result == 0

    @pytest.mark.asyncio
    async def test_clear_pattern_success(self):
        """Test successful pattern clear"""
        cache = AsyncCacheLayer()
        cache.connected = True
        cache.redis_client = AsyncMock()
        cache.redis_client.keys = AsyncMock(return_value=["key1", "key2", "key3"])
        cache.redis_client.delete = AsyncMock(return_value=3)

        result = await cache.clear_pattern("prefix:*")

        assert result == 3
        cache.redis_client.keys.assert_awaited_once_with("prefix:*")

    @pytest.mark.asyncio
    async def test_clear_pattern_no_matches(self):
        """Test clear_pattern with no matching keys"""
        cache = AsyncCacheLayer()
        cache.connected = True
        cache.redis_client = AsyncMock()
        cache.redis_client.keys = AsyncMock(return_value=[])

        result = await cache.clear_pattern("prefix:*")

        assert result == 0


class TestCacheStats:
    """Test cache get_stats method"""

    @pytest.mark.asyncio
    async def test_get_stats_not_connected(self):
        """Test get_stats when not connected"""
        cache = AsyncCacheLayer()
        cache.connected = False

        stats = await cache.get_stats()

        assert stats["connected"] is False

    @pytest.mark.asyncio
    async def test_get_stats_success(self):
        """Test successful stats retrieval"""
        cache = AsyncCacheLayer()
        cache.connected = True
        cache.redis_client = AsyncMock()
        cache.redis_client.info = AsyncMock(
            return_value={
                "redis_version": "7.0.0",
                "used_memory": 1024000,
                "connected_clients": 5,
                "keyspace_hits": 100,
                "keyspace_misses": 10,
            }
        )

        stats = await cache.get_stats()

        assert stats["connected"] is True
        assert stats["redis_version"] == "7.0.0"
        assert stats["keyspace_hits"] == 100


class TestConvenienceFunctions:
    """Test convenience functions"""

    @pytest.mark.asyncio
    @patch("src.core.caching.cache_layer.get_cache")
    async def test_set_cache(self, mock_get_cache):
        """Test set_cache convenience function"""
        mock_cache = AsyncMock()
        mock_cache.set = AsyncMock(return_value=True)
        mock_get_cache.return_value = mock_cache

        result = await set_cache("key1", "value1", ttl=300)

        assert result is True
        mock_cache.set.assert_awaited_once_with("key1", "value1", 300)

    @pytest.mark.asyncio
    @patch("src.core.caching.cache_layer.get_cache")
    async def test_get_cache_value(self, mock_get_cache):
        """Test get_cache_value convenience function"""
        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value="value1")
        mock_get_cache.return_value = mock_cache

        result = await get_cache_value("key1")

        assert result == "value1"
        mock_cache.get.assert_awaited_once_with("key1")

    @pytest.mark.asyncio
    @patch("src.core.caching.cache_layer.get_cache")
    async def test_delete_cache(self, mock_get_cache):
        """Test delete_cache convenience function"""
        mock_cache = AsyncMock()
        mock_cache.delete = AsyncMock(return_value=True)
        mock_get_cache.return_value = mock_cache

        result = await delete_cache("key1")

        assert result is True

    @pytest.mark.asyncio
    @patch("src.core.caching.cache_layer.get_cache")
    async def test_clear_cache_pattern_function(self, mock_get_cache):
        """Test clear_cache_pattern convenience function"""
        mock_cache = AsyncMock()
        mock_cache.clear_pattern = AsyncMock(return_value=5)
        mock_get_cache.return_value = mock_cache

        result = await clear_cache_pattern("prefix:*")

        assert result == 5

    @pytest.mark.asyncio
    @patch("src.core.caching.cache_layer.clear_cache_pattern")
    async def test_clear_cache(self, mock_clear_pattern):
        """Test clear_cache convenience function"""
        mock_clear_pattern.return_value = 10

        result = await clear_cache()

        mock_clear_pattern.assert_awaited_once_with("*")


class TestCachedDecorator:
    """Test cached decorator"""

    @pytest.mark.asyncio
    @patch("src.core.caching.cache_layer.get_cache")
    async def test_cached_decorator_cache_miss(self, mock_get_cache):
        """Test cached decorator on cache miss"""
        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value=None)
        mock_cache.set = AsyncMock(return_value=True)
        mock_get_cache.return_value = mock_cache

        call_count = 0

        @cached(ttl=300, key_prefix="test")
        async def test_func(arg1):
            nonlocal call_count
            call_count += 1
            return f"result-{arg1}"

        result = await test_func("value1")

        assert result == "result-value1"
        assert call_count == 1
        mock_cache.set.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("src.core.caching.cache_layer.get_cache")
    async def test_cached_decorator_cache_hit(self, mock_get_cache):
        """Test cached decorator on cache hit"""
        mock_cache = AsyncMock()
        mock_cache.get = AsyncMock(return_value="cached-result")
        mock_get_cache.return_value = mock_cache

        call_count = 0

        @cached(ttl=300, key_prefix="test")
        async def test_func(arg1):
            nonlocal call_count
            call_count += 1
            return f"result-{arg1}"

        result = await test_func("value1")

        assert result == "cached-result"
        assert call_count == 0  # Function not called
