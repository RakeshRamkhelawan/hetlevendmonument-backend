"""Redis-backed per-agent load tracking with TTL."""

from __future__ import annotations

import logging
import math
import os
from typing import Any

from src.core.typing import AsyncRedisClient

logger = logging.getLogger(__name__)

_LOAD_KEY_TEMPLATE = "agent:load:{tenant_id}:{agent_id}"
_LOAD_TTL_SECONDS = 30


class AgentLoadTracker:
    """Tracks current load for agents in Redis with a 30-second TTL.

    Each instance is scoped to a single tenant. Keys are namespaced as
    agent:load:{tenant_id}:{agent_id} to enforce tenant isolation.
    """

    def __init__(self, tenant_id: int) -> None:
        self._tenant_id = tenant_id
        self._client: AsyncRedisClient | None = None

    def _key(self, agent_id: str) -> str:
        return _LOAD_KEY_TEMPLATE.format(tenant_id=self._tenant_id, agent_id=agent_id)

    async def _get_client(self) -> AsyncRedisClient | None:
        if self._client is not None:
            return self._client
        try:
            from src.core.typing import create_aioredis_compat_client

            redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
            self._client = await create_aioredis_compat_client(
                redis_url, decode_responses=False
            )
            return self._client
        except Exception as exc:
            logger.warning("AgentLoadTracker: Redis unavailable: %s", exc)
            return None

    async def set_load(self, agent_id: str, load: float) -> None:
        if not math.isfinite(load):
            logger.warning(
                "AgentLoadTracker.set_load: ignoring non-finite load=%s for %s", load, agent_id
            )
            return
        clamped = max(0.0, min(1.0, load))
        try:
            client = await self._get_client()
            if client is None:
                return
            await client.setex(self._key(agent_id), _LOAD_TTL_SECONDS, str(clamped))
        except Exception as exc:
            logger.warning("AgentLoadTracker.set_load failed: %s", exc)

    async def get_load(self, agent_id: str) -> float | None:
        try:
            client = await self._get_client()
            if client is None:
                return None
            value = await client.get(self._key(agent_id))
            if value is None:
                return None
            return float(value)
        except Exception as exc:
            logger.warning("AgentLoadTracker.get_load failed: %s", exc)
            return None

    async def get_loads(self, agent_ids: list[str]) -> dict[str, float | None]:
        """Fetch loads for multiple agents in a single MGET round-trip."""
        if not agent_ids:
            return {}
        try:
            client = await self._get_client()
            if client is None:
                return {aid: None for aid in agent_ids}
            keys = [self._key(aid) for aid in agent_ids]
            values = await client.mget(keys)
            return {aid: (float(v) if v is not None else None) for aid, v in zip(agent_ids, values)}
        except Exception as exc:
            logger.warning("AgentLoadTracker.get_loads failed: %s", exc)
            return {aid: None for aid in agent_ids}

    async def clear_load(self, agent_id: str) -> None:
        try:
            client = await self._get_client()
            if client is None:
                return
            await client.delete(self._key(agent_id))
        except Exception as exc:
            logger.warning("AgentLoadTracker.clear_load failed: %s", exc)
