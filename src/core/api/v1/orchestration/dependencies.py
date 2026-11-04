"""Orchestration domain dependencies (ADR-033, ADR-034).

Router-bestanden importeren hieruit in plaats van direct uit
src.core.governance of src.core.agents (ADR-034: enige sanctioned import-locatie).
"""

import functools
import inspect
import logging
from typing import Any, Callable

from fastapi import Depends

from src.core.agents.agent_health_monitor_agent import AgentHealthMonitorAgent
from src.core.agents.agent_health_monitor_agent import HealthStatus as AgentHealthMonitorStatus
from src.core.agents.agent_router_agent import AgentRouterAgent
from src.core.agents.agent_router_agent import clear_router_instance
from src.core.agents.agent_router_agent import get_agent_router as get_router_singleton
from src.core.agents.critic_agent import CriticAgent
from src.core.agents.critique_store import CritiqueStore
from src.core.agents.master_orchestrator_agent import MasterOrchestratorAgent
from src.core.agents.master_orchestrator_agent import clear_orchestrator_instance
from src.core.agents.master_orchestrator_agent import (
    get_master_orchestrator as get_orchestrator_singleton,
)
from src.core.database.session import get_db_session
from src.core.governance.governance_helper import apply_governance_check
from src.core.governance.rate_limiter import consent_read_limit as consent_read_limit
from src.core.middleware.tenant_context import get_current_tenant_id, safe_get_tenant_id

logger = logging.getLogger(__name__)

# NOTE: caches are module-level dicts (per-process, per-tenant). Safe under the GIL.
# Entries are never evicted automatically -- call clear_tenant_cache() when a tenant is
# suspended or deleted to prevent stale agents from being served after reactivation.
# AgentRouterAgent and MasterOrchestratorAgent both use the singleton cache in their
# own agents/-module (_instances) instead of a local dict here -- SP-ADR023-002 Dag 1
# consolidated the previously separate instantiation paths so async_session_factory
# (agent-discovery, ADR-023) reaches the instances that actually serve
# /orchestration/* requests.
_critic_cache: dict[int, CriticAgent] = {}
_health_monitor_cache: dict[int, AgentHealthMonitorAgent] = {}


def get_critic_agent(tenant_id: int = Depends(safe_get_tenant_id)) -> CriticAgent:
    if tenant_id not in _critic_cache:
        _critic_cache[tenant_id] = CriticAgent(tenant_id=tenant_id)
        logger.info("Created CriticAgent for tenant %s", tenant_id)
    return _critic_cache[tenant_id]


async def _get_redis_client_fail_graceful() -> (
    Any | None  # TODO(TYPE): replace Any with concrete type
):
    """Fetch a Redis client for the routing cache, degrading gracefully on failure.

    A Redis outage must never turn every /orchestration/* request into a 500 for
    what is purely an optional cache-tier optimization (SP-ADR023-002 Dag 2) --
    mirrors the fail-graceful pattern in
    src/core/api/v1/agentic/dependencies.py::get_adaptation_service().
    """
    from src.core.database.redis import get_redis_client

    try:
        return await get_redis_client()
    except Exception as exc:
        logger.warning("Redis unavailable for routing cache; caching disabled: %s", exc)
        return None


async def get_master_orchestrator(
    tenant_id: int = Depends(safe_get_tenant_id),
    _critic: CriticAgent = Depends(get_critic_agent),  # noqa: ARG001 -- pre-wires CriticMixin cache
) -> MasterOrchestratorAgent:
    """Return the tenant's MasterOrchestratorAgent via the master_orchestrator_agent
    singleton. Delegates to get_orchestrator_singleton() instead of maintaining a
    separate local cache -- SP-ADR023-002 Dag 1 (mirrors get_agent_router() above,
    closing the dual-cache gap found during FA-NEW-001). Wires async_session_factory
    and redis_client so its internal _get_router() call reaches the same DB-backed
    agent-discovery and cross-worker routing cache (ADR-023, Dag 1 + Dag 2)."""
    redis_client = await _get_redis_client_fail_graceful()
    return get_orchestrator_singleton(
        tenant_id=tenant_id,
        async_session_factory=get_db_session,
        redis_client=redis_client,
    )


async def get_agent_router(tenant_id: int = Depends(safe_get_tenant_id)) -> AgentRouterAgent:
    """Return the tenant's AgentRouterAgent via the agent_router_agent singleton.

    Delegates to get_router_singleton() (agent_router_agent.py) instead of
    maintaining a separate local cache -- SP-ADR023-002 Dag 1. Wires
    async_session_factory so DB-backed agent-discovery is active on the
    router that actually serves /orchestration/* requests (ADR-023), and
    redis_client so the cross-worker routing cache is active too (Dag 2).
    """
    redis_client = await _get_redis_client_fail_graceful()
    return get_router_singleton(
        tenant_id=tenant_id,
        async_session_factory=get_db_session,
        redis_client=redis_client,
    )


def get_health_monitor(tenant_id: int = Depends(safe_get_tenant_id)) -> AgentHealthMonitorAgent:
    if tenant_id not in _health_monitor_cache:
        _health_monitor_cache[tenant_id] = AgentHealthMonitorAgent(
            agent_id=f"health_monitor_t{tenant_id}",
            tenant_id=tenant_id,
            poll_interval_s=30,
        )
        logger.info("Created AgentHealthMonitorAgent for tenant %s", tenant_id)
    return _health_monitor_cache[tenant_id]


def get_critique_store() -> CritiqueStore:
    """Return the CritiqueStore singleton."""
    return CritiqueStore()


def clear_tenant_cache(tenant_id: int) -> None:
    """Evict all cached agent instances for a tenant (call on suspend/delete).

    NOTE: the 4 evictions are not atomic as a group -- a concurrent request can
    re-populate one cache between them. Acceptable for suspend/delete; do not rely
    on this as an instantaneous atomic fence across all 4 caches.
    """
    clear_router_instance(tenant_id)
    clear_orchestrator_instance(tenant_id)
    for cache in (_critic_cache, _health_monitor_cache):
        cache.pop(tenant_id, None)


__all__ = [
    # Re-exported agent classes (for type annotations in router files -- ADR-033)
    "AgentHealthMonitorAgent",
    "AgentHealthMonitorStatus",
    "AgentRouterAgent",
    "CriticAgent",
    "CritiqueStore",
    "MasterOrchestratorAgent",
    # DI factories
    "get_agent_router",
    "get_critic_agent",
    "get_critique_store",
    "get_health_monitor",
    "get_master_orchestrator",
    # Infrastructure
    "apply_governance_check",
    "clear_tenant_cache",
    "consent_read_limit",
    "get_current_tenant_id",
    "safe_get_tenant_id",
    "limiter",
]


class _LazyLimiter:
    """Proxy for slowapi.Limiter that defers creation until first request.

    Router modules can apply ``@limiter.limit(...)`` at import time without
    paying the import/initialization cost of slowapi during startup.
    """

    def __init__(self) -> None:
        self._limiter: Any | None = None  # TODO(TYPE): replace Any with concrete type
        self._decorated: dict[int, Callable[..., Any]] = {}

    def _get_limiter(self) -> Any:  # TODO(TYPE): replace Any with concrete type
        if self._limiter is None:
            from src.core.middleware.rate_limiter import get_limiter

            self._limiter = get_limiter()
        return self._limiter

    def limit(
        self, limit_value: str, *args: Any, **kwargs: Any
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
            func_id = id(func)

            @functools.wraps(func)
            async def async_wrapper(
                *f_args: Any,  # TODO(TYPE): replace Any with concrete type
                **f_kwargs: Any,  # TODO(TYPE): replace Any with concrete type
            ) -> Any:  # TODO(TYPE): replace Any with concrete type
                if func_id not in self._decorated:
                    self._decorated[func_id] = self._get_limiter().limit(
                        limit_value, *args, **kwargs
                    )(func)
                return await self._decorated[func_id](*f_args, **f_kwargs)

            @functools.wraps(func)
            def sync_wrapper(
                *f_args: Any,  # TODO(TYPE): replace Any with concrete type
                **f_kwargs: Any,  # TODO(TYPE): replace Any with concrete type
            ) -> Any:  # TODO(TYPE): replace Any with concrete type
                if func_id not in self._decorated:
                    self._decorated[func_id] = self._get_limiter().limit(
                        limit_value, *args, **kwargs
                    )(func)
                return self._decorated[func_id](*f_args, **f_kwargs)

            wrapper = async_wrapper if inspect.iscoroutinefunction(func) else sync_wrapper
            return wrapper

        return decorator


limiter = _LazyLimiter()
