"""Integration test -- SP-ADR023-002 Dag 2 -- Redis cross-worker routing cache.

Bewijst met een ECHTE Redis-instantie (poort 6380, sanskritisetu_redis_integration)
dat twee losse AgentRouterAgent-instanties (die twee verschillende "workers"
simuleren) een ECHTE routingbeslissing delen via route() -- niet alleen dat
RedisRouteCacheTier in isolatie tegen Redis werkt.

Geschiedenis: een eerdere versie van dit bestand riep _redis_cache_tier.get()/
.set() rechtstreeks aan, wat bewees dat de tier tegen Redis werkt maar NIET dat
route() hem daadwerkelijk gebruikt. De onafhankelijke review van Dag 2 vond dit
(FA-001): AgentRouterAgent.route() raadpleegde _redis_cache_tier nergens, dus de
cross-worker cache bestond in productie niet ondanks groene tests. Gefixed in
agent_router_agent.py::route() (tier 1.5) -- deze test gaat nu door route() zelf.
"""

from __future__ import annotations

import pytest

from src.core.agents.agent_router_agent import (
    AgentManifest,
    RedisRouteCacheTier,
    RouteCacheEntry,
    get_agent_router,
)
import src.core.agents.agent_router_agent as ara_module
from src.core.database.redis import get_redis_client
from src.core.shared.interfaces import TaskData


@pytest.mark.integration
@pytest.mark.asyncio
async def test_route_shares_decision_across_two_worker_instances_via_redis() -> None:
    """A routing decision made via worker1_router.route() must be readable by
    worker2_router.route() for the SAME task -- even though worker2 has no
    registered manifests, no discovery service, and no LLM client, and would
    therefore be unable to resolve the task on its own tier 2/3/4. The only way
    worker2 can return the right agent_id is via the shared Redis tier 1.5.

    Uses the real get_agent_router() singleton factory (not a hand-built
    AgentRouterAgent) so this exercises the actual production wiring path.
    Clearing _instances between "worker 1" and "worker 2" simulates two
    separate Gunicorn worker processes, which each have their own in-memory
    _instances dict (and manifest registry) in real deployments but share the
    same Redis."""
    tenant_id = 88910
    task = TaskData(
        id="cross-worker-task-1",
        title="cross worker redis routing task",
        description="proves route() consults the Redis tier",
        metadata={"capabilities": ["legal"]},
    )
    cache_key = ara_module.RouteCache()._key(task.title, ["legal"], tenant_id)

    redis_client = await get_redis_client()
    original = ara_module._instances.pop(tenant_id, None)
    try:
        await redis_client.delete(f"route_cache:{tenant_id}:{cache_key}")

        # "Worker 1": has a registered manifest, resolves via capability-match
        # (tier 3), which must ALSO write through to Redis via route()'s
        # _remember_route() helper.
        worker1_router = get_agent_router(tenant_id, redis_client=redis_client)
        assert worker1_router._redis_cache_tier is not None
        await worker1_router.register(
            AgentManifest(
                agent_id="specialist_agent_007",
                agent_type="specialist",
                capabilities=["legal"],
                department="legal",
            )
        )
        first_result = await worker1_router.route(task)
        assert first_result == "specialist_agent_007"

        # "Worker 2": simulate a separate process by clearing _instances --
        # deliberately NO manifest registered, NO discovery service, NO LLM
        # client. If route() does not consult the Redis tier, this call falls
        # through all the way to tier 5 (executor_agent_001).
        ara_module._instances.pop(tenant_id, None)
        worker2_router = get_agent_router(tenant_id, redis_client=redis_client)
        assert worker2_router._redis_cache_tier is not None
        assert worker2_router is not worker1_router
        assert worker2_router._manifests == {}

        second_result = await worker2_router.route(task)

        assert second_result == "specialist_agent_007", (
            "Cross-worker cache-hit FAILED -- worker2's route() could not resolve "
            f"the task via Redis (got {second_result!r}, expected the agent worker1 "
            "cached). The Redis-cache wiring is not actually active on the routing path."
        )
    finally:
        await redis_client.delete(f"route_cache:{tenant_id}:{cache_key}")
        ara_module._instances.pop(tenant_id, None)
        if original is not None:
            ara_module._instances[tenant_id] = original


@pytest.mark.integration
@pytest.mark.asyncio
async def test_redis_route_cache_tier_isolates_tenants() -> None:
    """The same cache_key for two different tenants must not collide (ADR-005) --
    verified against real Redis, not just the key-format string."""
    tenant_a, tenant_b = 88911, 88912
    cache_key = "shared_cache_key_tenant_isolation_check"

    redis_client = await get_redis_client()
    tier = RedisRouteCacheTier(redis_client)
    try:
        await redis_client.delete(f"route_cache:{tenant_a}:{cache_key}")
        await redis_client.delete(f"route_cache:{tenant_b}:{cache_key}")

        entry_a = RouteCacheEntry(agent_id="agent_for_tenant_a", agent_type="specialist", score=0.5)
        await tier.set(cache_key, tenant_a, entry_a)

        result_for_tenant_b = await tier.get(cache_key, tenant_b)

        assert result_for_tenant_b is None, (
            "Tenant isolation FAILED -- tenant B read tenant A's cached routing decision."
        )
    finally:
        await redis_client.delete(f"route_cache:{tenant_a}:{cache_key}")
        await redis_client.delete(f"route_cache:{tenant_b}:{cache_key}")
