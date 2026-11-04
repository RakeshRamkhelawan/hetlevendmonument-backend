"""Redis adapter for ICacheBackend -- UCR L2 persistence (SP-AGT-004 Dag 2).

This file is the ONLY place in src.core.agents that may import src.core.database.
All other agent_runtime modules receive cache access via ICacheBackend injection.
"""

from __future__ import annotations

from src.core.database.redis import get_redis_client


class RedisCapabilityCache:
    """Concrete ICacheBackend backed by the shared Redis pool.

    Satisfies ICacheBackend from src.core.agents.api.
    Pool uses decode_responses=True so all keys/values are str, not bytes.
    """

    async def set(self, key: str, value: str, ttl: int) -> None:
        client = await get_redis_client()
        await client.setex(key, ttl, value)

    async def get(self, key: str) -> str | None:
        client = await get_redis_client()
        result = await client.get(key)
        return str(result) if result is not None else None

    async def keys(self, pattern: str) -> list[str]:
        client = await get_redis_client()
        result: list[str] = []
        async for key in client.scan_iter(match=pattern):
            result.append(key)
        return result
