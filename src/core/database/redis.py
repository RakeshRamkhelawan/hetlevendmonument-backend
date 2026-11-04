"""
Redis[Any] Client Factory - Rate Limiting Infrastructure  # TODO(TYPE): replace Any with concrete type

Provides async Redis[Any] connection pool management for rate limiting  # TODO(TYPE): replace Any with concrete type
and other Redis[Any]-dependent services with automatic retry and recovery.  # TODO(TYPE): replace Any with concrete type

Part of SA-2.1 implementation.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
import time
from typing import Any, TypeVar, Union, cast
from collections.abc import Awaitable

import redis.asyncio as redis

from src.config import get_redis_url

_T = TypeVar("_T")


async def ensure_async(value: Awaitable[_T] | _T) -> _T:
    """Await a value that may or may not be awaitable.

    redis-py command mixins (ListCommands, SetCommands, HashCommands, etc.)
    type their return values as ``Union[Awaitable[T], T]`` because the same
    method definitions serve both the sync and async Redis clients.  When
    using the async client, the value is always an awaitable at runtime, but
    the static type is the union.  This helper lets callers ``await`` such
    values without Pyright complaining that the non-awaitable branch of the
    union is not awaitable.
    """
    if inspect.isawaitable(value):
        return await value
    return value  # pragma: no cover - async client always returns awaitables


logger = logging.getLogger(__name__)

# Connectiepool, met de event loop waar hij bij hoort (ADR-036 OP-156).
#
# Een asyncpg/redis-pool hoort bij de loop die draaide toen hij werd aangemaakt: de sockets
# erin zijn aan die loop geregistreerd. Werd de pool alleen in een module-globale variabele
# bewaard, dan kreeg elke VOLGENDE loop een pool die aan een dode loop vastzat.
# Gereproduceerd in drie regels: `asyncio.run(get_redis_client())` slaagt, de tweede
# aanroep geeft `RuntimeError: Event loop is closed`.
#
# pytest-asyncio maakt per test een nieuwe loop, dus in de suite kwam dit boven als
# `got Future attached to a different loop` in een WILLEKEURIGE andere test -- op
# 2026-08-17 in drie van de vier volledige runs, waarmee het elke merge blokkeerde.
#
# Het bestaande herstelpad (`_redis_pool = None` bij een mislukte ping) ving dit niet: dat
# kijkt alleen naar `redis.ConnectionError` en `redis.TimeoutError`, en een loop-mismatch
# is een `RuntimeError`.
_redis_pool: redis.ConnectionPool | None = None  # type: ignore[type-arg]
_redis_pool_loop: asyncio.AbstractEventLoop | None = None
# Ook het slot is loop-gebonden: `asyncio.Lock` onthoudt bij het eerste gebruik welke loop
# draaide en weigert daarna elke andere. Het wordt dus samen met de pool vervangen.
_redis_pool_lock = asyncio.Lock()


def _vervang_de_pool_bij_een_nieuwe_loop() -> None:
    """Gooi pool en slot weg zodra we in een ANDERE event loop draaien.

    Bewust GEEN `await pool.disconnect()`: die verbindingen horen bij een loop die niet
    meer draait, dus ze zijn niet meer netjes te sluiten. Het besturingssysteem ruimt ze op
    wanneer het proces eindigt. Wachten op een dode loop zou hier vastlopen.

    De controle staat VOOR het verwerven van het slot, want dat slot is zelf het object dat
    vervangen moet worden -- eerst verwerven zou meteen de fout geven die we voorkomen.
    """
    global _redis_pool, _redis_pool_loop, _redis_pool_lock

    huidige = asyncio.get_running_loop()
    if _redis_pool is not None and _redis_pool_loop is not huidige:
        logger.debug("Nieuwe event loop gedetecteerd: Redis-pool en slot worden vervangen")
        _redis_pool = None
        _redis_pool_loop = None
        _redis_pool_lock = asyncio.Lock()


_redis_offline_until: float = 0.0


def _is_production() -> bool:
    return os.getenv("ENVIRONMENT", "development").lower() == "production"


async def get_redis_client() -> redis.Redis:  # type: ignore[type-arg]
    """
    Get a Redis client from the connection pool with automatic retry and pool reset.
    Creates the pool on first access, resets on connection failure.

    Returns:
        redis.Redis: Async Redis client instance

    Raises:
        redis.ConnectionError: If unable to connect to Redis[Any] after retry  # TODO(TYPE): replace Any with concrete type
    """
    global _redis_pool, _redis_pool_loop, _redis_offline_until

    _vervang_de_pool_bij_een_nieuwe_loop()

    is_prod = _is_production()
    if not is_prod and time.time() < _redis_offline_until:
        raise redis.ConnectionError("Redis is offline (circuit breaker cooldown active)")

    async with _redis_pool_lock:
        if not is_prod and time.time() < _redis_offline_until:
            raise redis.ConnectionError("Redis is offline (circuit breaker cooldown active)")

        # Try to use existing pool
        if _redis_pool is not None:
            try:
                client = redis.Redis(connection_pool=_redis_pool)
                if is_prod:
                    await client.ping()
                else:
                    await asyncio.wait_for(client.ping(), timeout=0.2)
                return client
            except (redis.ConnectionError, redis.TimeoutError, asyncio.TimeoutError) as e:
                logger.warning(
                    f"Redis[Any] connection failed, resetting pool: {e}"
                )  # TODO(TYPE): replace Any with concrete type
                # Close broken pool
                try:
                    await _redis_pool.disconnect()
                except Exception:
                    pass
                _redis_pool = None
                if not is_prod:
                    _redis_offline_until = time.time() + 60.0
                raise redis.ConnectionError(f"Redis connection failed: {e}") from e

        # Create new pool if needed
        if _redis_pool is None:
            try:
                connect_timeout = 2 if is_prod else 0.2
                _redis_pool = redis.ConnectionPool.from_url(
                    get_redis_url(),
                    encoding="utf-8",
                    decode_responses=True,
                    max_connections=100,
                    retry_on_timeout=is_prod,
                    socket_keepalive=True,
                    socket_connect_timeout=connect_timeout,
                    socket_timeout=connect_timeout,
                )
                _redis_pool_loop = asyncio.get_running_loop()
                client = redis.Redis(connection_pool=_redis_pool)
                if is_prod:
                    await client.ping()
                else:
                    await asyncio.wait_for(client.ping(), timeout=0.2)
                logger.info(
                    "Redis[Any] connection pool created successfully"
                )  # TODO(TYPE): replace Any with concrete type
                return client
            except Exception as e:
                if not is_prod:
                    _redis_offline_until = time.time() + 60.0
                logger.warning(
                    f"Failed to create Redis[Any] pool: {e}"
                )  # TODO(TYPE): replace Any with concrete type
                if _redis_pool:
                    try:
                        await _redis_pool.disconnect()
                    except Exception:
                        pass
                _redis_pool = None
                raise redis.ConnectionError(f"Failed to create Redis pool: {e}") from e

        return redis.Redis(connection_pool=_redis_pool)


async def close_redis() -> None:
    """
    Close the Redis[Any] connection pool safely.  # TODO(TYPE): replace Any with concrete type
    Call this during application shutdown.
    """
    global _redis_pool, _redis_pool_loop
    async with _redis_pool_lock:
        if _redis_pool:
            try:
                await _redis_pool.disconnect()
                logger.info(
                    "Redis[Any] connection pool closed successfully"
                )  # TODO(TYPE): replace Any with concrete type
            except Exception as e:
                logger.warning(
                    f"Error closing Redis[Any] pool: {e}"
                )  # TODO(TYPE): replace Any with concrete type
            finally:
                _redis_pool = None
                _redis_pool_loop = None


def reset_redis_pool() -> None:
    """Reset the global Redis[Any] connection pool for testing.

    Safe to call from test fixtures. No-op if pool is None.
    """
    global _redis_pool, _redis_pool_loop, _redis_offline_until
    _redis_pool = None
    _redis_pool_loop = None
    _redis_offline_until = 0.0
