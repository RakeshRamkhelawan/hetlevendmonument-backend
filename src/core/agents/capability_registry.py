"""
UnifiedCapabilityRegistry -- single authoritative registry for capability discovery.

ADR-027 s12, ADR-034 s5.5.
Merges: native agents, ALS skills, ToolBroker tools, ActivePieces flows.

Design (SP-AGT-004 Dag 2):
- In-memory L1 store per tenant (primary, always consistent within one worker).
- Optional ICacheBackend L2 (write-through on register; lazy-load on first discover miss).
- Cache backend injected via constructor -- this module has no direct database
  imports (ADR-034 Contract 3 invariant; adapter lives in agents/adapters/).
"""

from __future__ import annotations

import logging
import os
from collections import defaultdict

from src.core.agents.api import ICacheBackend
from src.core.shared.interfaces import AgentCapability
from src.core.utils.best_effort import best_effort

logger = logging.getLogger(__name__)

_TTL: int = int(os.getenv("UCR_REDIS_TTL_SECONDS") or "86400")


class UnifiedCapabilityRegistry:
    """Single authoritative registry for capability discovery (ADR-027 s12).

    Satisfies ICapabilityRegistry from src.core.agents.api.
    """

    def __init__(self, cache: ICacheBackend | None = None) -> None:
        self._store: dict[int, list[AgentCapability]] = defaultdict(list)
        self._cache = cache
        self._loaded: set[int] = set()

    def _register(self, tenant_id: int, capability: AgentCapability) -> None:
        self._store[tenant_id].append(capability)
        logger.info(
            "capability_registry.registered: tenant=%d cap=%s",
            tenant_id,
            capability.name,
        )

    async def register_agent(self, tenant_id: int, capability: AgentCapability) -> None:
        """Register capability in-memory (L1) and write-through to cache (L2)."""
        self._register(tenant_id, capability)
        if self._cache is not None:
            async with best_effort("ucr.cache_write", db_session=None):
                await self._cache.set(
                    self._redis_key(tenant_id, capability),
                    capability.model_dump_json(),
                    _TTL,
                )

    async def discover(self, query: str, tenant_id: int) -> list[AgentCapability]:
        if (
            self._cache is not None
            and not self._store.get(tenant_id)
            and tenant_id not in self._loaded
        ):
            self._loaded.add(tenant_id)
            ok = await self._load_from_cache(tenant_id)
            if not ok:
                self._loaded.discard(tenant_id)
        caps = self._store.get(tenant_id, [])
        if not query:
            return list(caps)
        q = query.lower()
        return [c for c in caps if q in c.name.lower() or q in c.description.lower()]

    async def _load_from_cache(self, tenant_id: int) -> bool:
        if self._cache is None:
            return True
        loaded_ok = False
        async with best_effort("ucr.cache_load", db_session=None):
            pattern = f"ucr:{tenant_id}:*"
            keys = await self._cache.keys(pattern)
            for key in keys:
                raw = await self._cache.get(key)
                if raw:
                    self._store[tenant_id].append(AgentCapability.model_validate_json(raw))
            loaded_ok = True
        return loaded_ok

    @staticmethod
    def _redis_key(tenant_id: int, capability: AgentCapability) -> str:
        return f"ucr:{tenant_id}:{capability.name}"
