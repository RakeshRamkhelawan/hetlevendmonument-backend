"""Typed protocols for third-party libraries without complete stubs.

This module provides Protocol classes that describe the interfaces of
untyped third-party libraries (redis, etc.) so that mypy and pyright
can type-check our code correctly without relying on incomplete stubs.
"""

from __future__ import annotations

from typing import Protocol, Any, cast
from collections.abc import AsyncIterator
import builtins


class AsyncPubSub(Protocol):
    """Protocol for Redis async PubSub client."""

    async def subscribe(
        self, *channels: str
    ) -> Any: ...  # TODO(TYPE): replace Any with concrete type
    async def unsubscribe(
        self, *channels: str
    ) -> Any: ...  # TODO(TYPE): replace Any with concrete type
    def listen(
        self,
    ) -> AsyncIterator[dict[str, Any]]: ...  # TODO(TYPE): replace Any with concrete type
    async def close(self) -> None: ...


class AsyncRedisClient(Protocol):
    """Protocol for Redis async client (redis.asyncio.Redis).

    Covers all methods used across the SanskritiSetu codebase.
    Designed for decode_responses=True (str values, not bytes).
    """

    # String operations
    async def get(self, key: str) -> str | None: ...
    async def set(
        self,
        key: str,
        value: str,
        *,
        ex: int | None = None,
        px: int | None = None,
        nx: bool = False,
        xx: bool = False,
    ) -> bool | None: ...
    async def setex(self, key: str, seconds: int, value: str) -> bool: ...
    async def getdel(self, key: str) -> str | None: ...
    async def getex(self, key: str, *, ex: int | None = None) -> str | None: ...
    async def mget(self, keys: list[str]) -> list[str | None]: ...
    async def mset(self, mapping: dict[str, str]) -> bool: ...

    # Key operations
    async def delete(self, *keys: str) -> int: ...
    async def exists(self, *keys: str) -> int: ...
    async def expire(self, key: str, seconds: int) -> bool: ...
    async def ttl(self, key: str) -> int: ...
    async def scan(
        self, cursor: int = 0, *, match: str | None = None, count: int | None = None
    ) -> tuple[int, list[str]]: ...
    async def keys(self, pattern: str) -> list[str]: ...

    # Hash operations
    async def hget(self, key: str, field: str) -> str | None: ...
    async def hset(
        self,
        key: str,
        field: str | None = None,
        value: str | None = None,
        *,
        mapping: dict[str, str] | None = None,
    ) -> int: ...
    async def hdel(self, key: str, *fields: str) -> int: ...
    async def hgetall(self, key: str) -> dict[str, str]: ...
    async def hmget(self, key: str, fields: list[str]) -> list[str | None]: ...

    # Set operations
    async def sadd(self, key: str, *members: str) -> int: ...
    async def srem(self, key: str, *members: str) -> int: ...
    async def smembers(self, key: str) -> builtins.set[str]: ...
    async def sismember(self, key: str, member: str) -> bool: ...
    async def scard(self, key: str) -> int: ...

    # List operations
    async def lpush(self, key: str, *values: str) -> int: ...
    async def rpush(self, key: str, *values: str) -> int: ...
    async def lrange(self, key: str, start: int, end: int) -> list[str]: ...
    async def ltrim(self, key: str, start: int, end: int) -> bool: ...
    async def lpop(self, key: str) -> str | None: ...
    async def rpop(self, key: str) -> str | None: ...
    async def llen(self, key: str) -> int: ...

    # Pub/Sub
    def pubsub(self, **kwargs: Any) -> AsyncPubSub: ...
    async def publish(self, channel: str, message: str) -> int: ...

    # Counter
    async def incr(self, key: str, amount: int = 1) -> int: ...
    async def decr(self, key: str, amount: int = 1) -> int: ...

    # Streams
    def xadd(
        self, stream: str, fields: dict[str, Any], *, id: str = "*", maxlen: int | None = None
    ) -> str: ...  # TODO(TYPE): replace Any with concrete type
    def blpop(
        self, keys: list[str] | tuple[str, ...], timeout: float = 0
    ) -> tuple[str, str] | None: ...

    # Pipeline
    def pipeline(
        self, transaction: bool = True
    ) -> Any: ...  # TODO(TYPE): replace Any with concrete type

    # Connection
    async def ping(self) -> bool: ...
    async def close(self) -> None: ...
    async def aclose(self) -> None: ...
    async def flushdb(self) -> bool: ...
    async def info(
        self, section: str | None = None
    ) -> dict[str, Any]: ...  # TODO(TYPE): replace Any with concrete type


class SyncRedisClient(Protocol):
    """Protocol for synchronous Redis client (redis.Redis)."""

    def get(self, key: str) -> str | None: ...
    def set(
        self,
        key: str,
        value: str,
        *,
        ex: int | None = None,
        px: int | None = None,
        nx: bool = False,
        xx: bool = False,
    ) -> bool | None: ...
    def setex(self, key: str, seconds: int, value: str) -> bool: ...
    def delete(self, *keys: str) -> int: ...
    def exists(self, *keys: str) -> int: ...
    def expire(self, key: str, seconds: int) -> bool: ...
    def ping(self) -> bool: ...
    def close(self) -> None: ...

    # Streams
    def xadd(
        self, stream: str, fields: dict[str, Any], *, id: str = "*", maxlen: int | None = None
    ) -> str: ...  # TODO(TYPE): replace Any with concrete type
    def blpop(
        self, keys: list[str] | tuple[str, ...], timeout: float = 0
    ) -> tuple[str, str] | None: ...


# Factories


async def create_async_redis_client(
    url: str, *, decode_responses: bool = True, **kwargs: Any
) -> AsyncRedisClient:
    """Create an async Redis client with proper typing."""
    import redis.asyncio

    return cast(
        AsyncRedisClient, redis.asyncio.from_url(url, decode_responses=decode_responses, **kwargs)
    )


def create_sync_redis_client(
    url: str, *, decode_responses: bool = True, **kwargs: Any
) -> SyncRedisClient:
    """Create a sync Redis client with proper typing."""
    import redis

    return cast(
        SyncRedisClient,
        redis.from_url(  # type: ignore[call-overload]
            url, decode_responses=decode_responses, **kwargs
        ),
    )


# Backwards compatibility for code still using aioredis
async def create_aioredis_compat_client(
    url: str, *, decode_responses: bool = True, **kwargs: Any
) -> AsyncRedisClient:
    """Backwards-compatible factory for legacy aioredis usage.

    aioredis was merged into redis-py 4.2+. This factory redirects to
    redis.asyncio while maintaining the old call signature.
    """
    return await create_async_redis_client(url, decode_responses=decode_responses, **kwargs)
