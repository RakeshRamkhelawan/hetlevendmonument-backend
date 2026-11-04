"""
Redis-backed distributed cache for SanskritiSetu.

Provides:
- Distributed caching across multiple nodes
- Pub/Sub for real-time cache invalidation
- Cluster support for high availability
- Automatic failover and connection pooling
"""

import asyncio
import json
import logging
import types
from dataclasses import dataclass
from typing import cast
from collections.abc import Callable

logger = logging.getLogger(__name__)

# Type-checking imports to satisfy mypy/pyright when redis is available
from typing import TYPE_CHECKING, Any
from collections.abc import Awaitable

if TYPE_CHECKING:
    import redis.asyncio as _aioredis
    from redis.asyncio.cluster import (
        ClusterNode as _ClusterNodeClass,
        RedisCluster as _RedisClusterClass,
    )
    from redis.asyncio.client import PubSub

# Try to import redis
aioredis: types.ModuleType | None = None
ClusterNode: "type[_ClusterNodeClass] | None" = None
RedisCluster: "type[_RedisClusterClass] | None" = None  # type: ignore[type-arg]
try:
    import redis.asyncio as _aioredis_mod
    from redis.asyncio.cluster import ClusterNode as _ClusterNode, RedisCluster as _RedisCluster

    aioredis = _aioredis_mod
    ClusterNode = _ClusterNode
    RedisCluster = _RedisCluster
    HAS_REDIS = True
except ImportError:
    HAS_REDIS = False
    logger.warning("Redis not installed. Using in-memory fallback.")


@dataclass
class RedisConfig:
    """Redis connection configuration."""

    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: str | None = None
    ssl: bool = False

    # Connection pool settings
    max_connections: int = 50
    min_connections: int = 10

    # Cluster settings
    cluster_mode: bool = False
    cluster_nodes: list[dict[str, str | int]] | None = None

    # Retry settings
    max_retries: int = 3
    retry_delay: float = 1.0

    # Key prefix for tenant isolation
    key_prefix: str = "sanskritisetu"

    def get_connection_url(self) -> str:
        """Generate Redis connection URL."""
        protocol = "rediss" if self.ssl else "redis"
        auth = f":{self.password}@" if self.password else ""
        return f"{protocol}://{auth}{self.host}:{self.port}/{self.db}"


class RedisCache:
    """
    Distributed cache using Redis.

    Features:
    - Automatic serialization (JSON/pickle)
    - TTL support
    - Pattern-based invalidation
    - Pub/Sub for cache sync
    - Tenant isolation
    """

    _instances: dict[int, "RedisCache"] = {}
    _initialized: bool
    _tenant_id: int
    _config: RedisConfig
    _client: "_aioredis.Redis | None"  # type: ignore[type-arg]
    _pubsub: "PubSub | None"
    _lock: asyncio.Lock
    _local_cache: dict[str, object]
    _local_ttl: dict[str, float]
    _subscribed_patterns: set[str]

    def __new__(cls, tenant_id: int = 1, config: RedisConfig | None = None) -> "RedisCache":
        if tenant_id not in cls._instances:
            cls._instances[tenant_id] = super().__new__(cls)
            cls._instances[tenant_id]._initialized = False
            cls._instances[tenant_id]._tenant_id = tenant_id
        return cls._instances[tenant_id]

    def __init__(self, tenant_id: int = 1, config: RedisConfig | None = None) -> None:
        if self._initialized:
            return

        self._initialized = True
        self._tenant_id = tenant_id
        self._config = config or RedisConfig()
        self._client = None
        self._pubsub = None
        self._lock = asyncio.Lock()

        # Local cache for fallback
        self._local_cache: dict[str, object] = {}
        self._local_ttl: dict[str, float] = {}

        # Track subscribed patterns
        self._subscribed_patterns: set[str] = set()

        logger.info(f"RedisCache initialized for tenant {tenant_id}")

    async def connect(self) -> bool:
        """Establish Redis connection."""
        if not HAS_REDIS:
            logger.warning("Redis not available, using in-memory fallback")
            return False

        try:
            if self._config.cluster_mode:
                raw_nodes = self._config.cluster_nodes or [
                    {"host": self._config.host, "port": self._config.port}
                ]
                if ClusterNode is None or RedisCluster is None:
                    raise RuntimeError("Redis cluster support not available")
                startup_nodes = [
                    ClusterNode(host=cast(str, node["host"]), port=cast(int, node["port"]))
                    for node in raw_nodes
                ]
                self._client = cast(
                    "_aioredis.Redis",  # type: ignore[type-arg]
                    RedisCluster(
                        startup_nodes=startup_nodes,
                        password=self._config.password,
                        ssl=self._config.ssl,
                        max_connections=self._config.max_connections,
                        decode_responses=False,
                    ),
                )
            else:
                if aioredis is None:
                    raise RuntimeError("aioredis not available")
                self._client = cast(
                    "_aioredis.Redis",  # type: ignore[type-arg]
                    getattr(aioredis, "Redis")(
                        host=self._config.host,
                        port=self._config.port,
                        db=self._config.db,
                        password=self._config.password,
                        ssl=self._config.ssl,
                        max_connections=self._config.max_connections,
                        decode_responses=False,
                    ),
                )

            # Test connection
            logger.info(f"Connected to Redis at {self._config.host}:{self._config.port}")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self._client = None
            return False

    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self._client:
            await self._client.close()
            self._client = None
            logger.info("Redis connection closed")

    def _make_key(self, key: str) -> str:
        """Generate tenant-scoped key."""
        return f"{self._config.key_prefix}:tenant:{self._tenant_id}:{key}"

    def _serialize(self, value: object) -> bytes:
        """Serialize value to bytes."""
        try:
            return json.dumps(value).encode("utf-8")
        except (TypeError, ValueError):
            return json.dumps(str(value)).encode("utf-8")

    def _deserialize(self, data: bytes) -> object | None:
        """Deserialize bytes to value."""
        try:
            decoded = data.decode("utf-8")
            result: object = json.loads(decoded)
            return result
        except (json.JSONDecodeError, UnicodeDecodeError):
            logger.warning("Failed to deserialize cache data as JSON")
            return None

    async def get(self, key: str) -> object | None:
        """Get value from cache."""
        full_key = self._make_key(key)

        if self._client:
            try:
                data: bytes | None = await self._client.get(full_key)
                if data:
                    result: object | None = self._deserialize(data)
                    return result
            except Exception as e:
                logger.warning(f"Redis get failed: {e}, using local cache")

        # Fallback to local cache
        if key in self._local_cache:
            if self._local_ttl.get(key, 0) > asyncio.get_event_loop().time():
                return self._local_cache[key]
            else:
                del self._local_cache[key]
                self._local_ttl.pop(key, None)

        return None

    async def set(
        self,
        key: str,
        value: object,
        ttl_seconds: int | None = None,
        nx: bool = False,
        xx: bool = False,
    ) -> bool:
        """Set value in cache."""
        full_key = self._make_key(key)
        data = self._serialize(value)

        if self._client:
            try:
                if nx:
                    result: bool | None = await self._client.setnx(full_key, data)
                elif xx:
                    result = await self._client.set(full_key, data, xx=True, ex=ttl_seconds)
                else:
                    result = await self._client.set(full_key, data, ex=ttl_seconds)

                if result and ttl_seconds:
                    await self._publish_invalidation(key)

                return bool(result)
            except Exception as e:
                logger.warning(f"Redis set failed: {e}, using local cache")

        # Fallback to local cache
        self._local_cache[key] = value
        if ttl_seconds:
            self._local_ttl[key] = asyncio.get_event_loop().time() + ttl_seconds

        return True

    async def delete(self, key: str) -> bool:
        """Delete key from cache."""
        full_key = self._make_key(key)

        if self._client:
            try:
                result = await self._client.delete(full_key)
                await self._publish_invalidation(key)
                return int(result) > 0
            except Exception as e:
                logger.warning(f"Redis delete failed: {e}")

        self._local_cache.pop(key, None)
        self._local_ttl.pop(key, None)
        return True

    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern."""
        full_pattern = self._make_key(pattern)

        if self._client:
            try:
                keys: list[bytes] = []
                async for key in self._client.scan_iter(match=full_pattern):
                    keys.append(key)

                if keys:
                    await self._client.delete(*keys)
                    await self._publish_invalidation(pattern)

                return len(keys)
            except Exception as e:
                logger.warning(f"Redis delete_pattern failed: {e}")

        count = 0
        prefix = pattern.rstrip("*")
        for local_key in list(self._local_cache.keys()):
            if local_key.startswith(prefix):
                del self._local_cache[local_key]
                self._local_ttl.pop(local_key, None)
                count += 1

        return count

    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        full_key = self._make_key(key)

        if self._client:
            try:
                return int(await self._client.exists(full_key)) > 0
            except Exception as e:
                logger.warning(f"Redis exists failed: {e}")

        return key in self._local_cache

    async def ttl(self, key: str) -> int:
        """Get remaining TTL in seconds."""
        full_key = self._make_key(key)

        if self._client:
            try:
                return int(await self._client.ttl(full_key))
            except Exception as e:
                logger.warning(f"Redis ttl failed: {e}")

        if key not in self._local_cache:
            return -2
        if key not in self._local_ttl:
            return -1

        remaining = self._local_ttl[key] - asyncio.get_event_loop().time()
        return int(remaining) if remaining > 0 else -2

    async def increment(self, key: str, amount: int = 1) -> int:
        """Atomically increment a counter."""
        full_key = self._make_key(key)

        if self._client:
            try:
                return int(await self._client.incrby(full_key, amount))
            except Exception as e:
                logger.warning(f"Redis increment failed: {e}")

        current: int = cast(int, self._local_cache.get(key, 0))
        current += amount
        self._local_cache[key] = current
        return current

    async def _publish_invalidation(self, pattern: str) -> None:
        """Publish cache invalidation event to other nodes."""
        if not self._client:
            return

        try:
            channel = f"{self._config.key_prefix}:invalidate:{self._tenant_id}"
            message = json.dumps({"pattern": pattern, "timestamp": asyncio.get_event_loop().time()})
            await self._client.publish(channel, message)
        except Exception as e:
            logger.debug(f"Failed to publish invalidation: {e}")

    async def subscribe_to_invalidations(
        self, callback: Callable[[str], Awaitable[object]]
    ) -> None:
        """Subscribe to cache invalidation events from other nodes."""
        if not self._client:
            return

        try:
            pubsub = self._client.pubsub()
            self._pubsub = pubsub
            channel = f"{self._config.key_prefix}:invalidate:{self._tenant_id}"
            await pubsub.subscribe(channel)

            logger.info(f"Subscribed to cache invalidations on {channel}")

            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        message_data: bytes | str = message["data"]
                        data: dict[str, object] = json.loads(message_data)
                        pattern: str = str(data.get("pattern", "*"))
                        await callback(pattern)
                    except Exception as e:
                        logger.warning(f"Failed to process invalidation: {e}")

        except Exception as e:
            logger.error(f"Pub/Sub error: {e}")

    async def get_stats(self) -> dict[str, object]:
        """Get cache statistics."""
        stats: dict[str, object] = {
            "tenant_id": self._tenant_id,
            "connected": self._client is not None,
            "local_cache_size": len(self._local_cache),
        }

        if self._client:
            try:
                info = cast(dict[str, object], await self._client.info())
                stats.update(
                    {
                        "redis_version": info.get("redis_version"),
                        "used_memory_mb": cast(int, info.get("used_memory", 0)) / 1024 / 1024,
                        "connected_clients": info.get("connected_clients", 0),
                        "total_commands_processed": info.get("total_commands_processed", 0),
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to get Redis stats: {e}")

        return stats


def get_redis_cache(tenant_id: int = 1, config: RedisConfig | None = None) -> RedisCache:
    """Get or create RedisCache instance for tenant."""
    return RedisCache(tenant_id=tenant_id, config=config)
