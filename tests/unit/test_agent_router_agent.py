"""
Unit tests for AgentRouterAgent - 5-tier routing, cache, registration.

Tests cover:
  - RouteCache: TTL, tenant isolation, max entries eviction, stats, invalidate_all
  - AgentManifest and RouteCacheEntry dataclass fields
  - AgentRouterAgent registration / deregistration
  - capability_match: happy and unhappy paths
  - route() 5-tier chain: cache, discovery, capability, LLM, fallback
  - _discovery_route(): no service, hit, exception
  - metrics(): all keys, discovery_hits counted
  - get_agent_router() singleton: same tenant -> same instance, different -> different
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.agents.agent_router_agent import (
    AgentManifest,
    AgentRouterAgent,
    RouteCache,
    RouteCacheEntry,
    get_agent_router,
)
from src.core.llm.fallback_chain import FallbackResult, ModelTier
from src.core.shared.interfaces import TaskData


@pytest.fixture(autouse=True)
def _no_live_llm_calls(monkeypatch):
    """Unit tests must never make real LLM network calls (test isolation).

    _llm_route() falls through to the real fallback chain whenever _manifests
    is non-empty and the upper routing tiers miss. Default to a deterministic
    no-match FallbackResult so tests that only care about earlier tiers (cache,
    capability match, overload fallback) never hit the network. Tests that
    specifically exercise the LLM tier patch get_fallback_chain themselves,
    which overrides this default for the duration of their own `with` block.
    """
    # Het taalmodel is dat van de TENANT van de router (`TenantTaalmodel`); geen echte aanroep (brief 2026-10-20).
    monkeypatch.setattr(
        "src.core.services.llm.tenant_deur.TenantTaalmodel.tekst",
        AsyncMock(return_value='{"agent_id": "__no_llm_match__"}'),
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_task(
    title: str = "test task",
    description: str = "task description",
    capabilities: list[str] | None = None,
) -> TaskData:
    metadata: dict = {}
    if capabilities:
        metadata["capabilities"] = capabilities
    return TaskData(id="t1", title=title, description=description, metadata=metadata)


def _make_manifest(
    agent_id: str = "agent_001",
    capabilities: list[str] | None = None,
    current_load: float = 0.0,
) -> AgentManifest:
    return AgentManifest(
        agent_id=agent_id,
        agent_type="specialist",
        capabilities=capabilities or ["legal", "contracts"],
        department="legal",
        current_load=current_load,
    )


@pytest.fixture
def router() -> AgentRouterAgent:
    """Build an AgentRouterAgent with base-class init patched out."""
    from collections import defaultdict

    r = AgentRouterAgent.__new__(AgentRouterAgent)
    # Use private backing attr since agent_id is a read-only property
    r._agent_id = "test_router"
    r.tenant_id = 42
    r.specialization = "intent_based_task_routing"
    r.llm_client = None
    r._manifests = {}
    r._manifests_lock = asyncio.Lock()
    r._cap_index = defaultdict(list)
    r._cache = RouteCache(ttl_seconds=300)
    r._redis_cache_tier = None
    r._discovery_service = None
    r._routes_total = 0
    r._cache_hits = 0
    r._discovery_hits = 0
    r._fallbacks_used = 0
    r._load_tracker = None
    r._async_session_factory = None
    return r


# ===========================================================================
# RouteCache tests
# ===========================================================================


@pytest.mark.unit
def test_route_cache_miss_returns_none():
    cache = RouteCache()
    result = cache.get("draft contract", ["legal"], tenant_id=1)
    assert result is None


@pytest.mark.unit
def test_route_cache_set_and_hit():
    cache = RouteCache()
    entry = RouteCacheEntry(agent_id="legal_agent_001", agent_type="specialist", score=0.9)
    cache.set("draft contract", ["legal"], tenant_id=1, entry=entry)
    result = cache.get("draft contract", ["legal"], tenant_id=1)
    assert result is not None
    assert result.agent_id == "legal_agent_001"


@pytest.mark.unit
def test_route_cache_tenant_isolation():
    cache = RouteCache()
    entry = RouteCacheEntry(agent_id="legal_agent_001", agent_type="specialist", score=0.9)
    cache.set("draft contract", ["legal"], tenant_id=1, entry=entry)
    # Different tenant should not see tenant 1's entry
    result = cache.get("draft contract", ["legal"], tenant_id=2)
    assert result is None


@pytest.mark.unit
def test_route_cache_ttl_expiry():
    cache = RouteCache(ttl_seconds=300)
    entry = RouteCacheEntry(agent_id="legal_agent_001", agent_type="specialist", score=0.9)
    # Set the entry with a created_at far in the past
    entry.created_at = datetime.now(timezone.utc) - timedelta(seconds=301)
    key = cache._key("draft contract", ["legal"], tenant_id=1)
    cache._store[key] = entry
    result = cache.get("draft contract", ["legal"], tenant_id=1)
    assert result is None
    # Key should be cleaned up
    assert key not in cache._store


@pytest.mark.unit
def test_route_cache_max_entries_evicts_oldest():
    cache = RouteCache(ttl_seconds=300, max_entries=3)
    # Add 3 entries with distinct created_at (oldest first)
    base_time = datetime.now(timezone.utc)
    for i in range(3):
        e = RouteCacheEntry(agent_id=f"agent_{i}", agent_type="t", score=0.5)
        e.created_at = base_time + timedelta(seconds=i)
        cache.set(f"task_{i}", [], tenant_id=1, entry=e)
    # Adding a 4th entry should evict the oldest (i=0)
    oldest_key = cache._key("task_0", [], tenant_id=1)
    new_entry = RouteCacheEntry(agent_id="agent_new", agent_type="t", score=0.5)
    cache.set("task_new", [], tenant_id=1, entry=new_entry)
    assert oldest_key not in cache._store
    assert len(cache._store) == 3


@pytest.mark.unit
def test_route_cache_stats_hit_rate():
    cache = RouteCache()
    entry = RouteCacheEntry(agent_id="a1", agent_type="t", score=0.8)
    cache.set("t", ["c"], tenant_id=1, entry=entry)
    cache.get("t", ["c"], tenant_id=1)  # hit
    cache.get("t", ["c"], tenant_id=1)  # hit
    cache.get("missing", [], tenant_id=1)  # miss
    stats = cache.stats()
    assert stats["hits"] == 2
    assert stats["misses"] == 1
    assert stats["hit_rate"] == round(2 / 3, 4)


@pytest.mark.unit
def test_route_cache_invalidate_all():
    cache = RouteCache()
    entry = RouteCacheEntry(agent_id="a1", agent_type="t", score=0.9)
    cache.set("t1", [], tenant_id=1, entry=entry)
    cache.set("t2", [], tenant_id=2, entry=entry)
    cleared = cache.invalidate_all()
    assert cleared == 2
    assert len(cache._store) == 0


# ===========================================================================
# AgentRouterAgent registration
# ===========================================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_register_adds_to_manifests(router: AgentRouterAgent):
    manifest = _make_manifest("legal_agent_001")
    await router.register(manifest)
    assert "legal_agent_001" in router._manifests


@pytest.mark.unit
@pytest.mark.asyncio
async def test_register_indexes_capabilities(router: AgentRouterAgent):
    manifest = _make_manifest("legal_agent_001", capabilities=["contracts", "compliance"])
    await router.register(manifest)
    assert "legal_agent_001" in router._cap_index["contracts"]
    assert "legal_agent_001" in router._cap_index["compliance"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_deregister_removes_manifest_and_index(router: AgentRouterAgent):
    manifest = _make_manifest("legal_agent_001", capabilities=["contracts"])
    await router.register(manifest)
    await router.deregister("legal_agent_001")
    assert "legal_agent_001" not in router._manifests
    assert "legal_agent_001" not in router._cap_index["contracts"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_deregister_noop_if_not_registered(router: AgentRouterAgent):
    # Should not raise
    await router.deregister("nonexistent_agent")
    assert len(router._manifests) == 0


# ===========================================================================
# capability_match tests
# ===========================================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_capability_match_returns_best_overlap(router: AgentRouterAgent):
    m1 = _make_manifest("legal_agent_001", capabilities=["contracts", "compliance"])
    m2 = _make_manifest("data_agent_001", capabilities=["analytics"])
    await router.register(m1)
    await router.register(m2)
    result = router.capability_match(["contracts", "compliance"])
    assert result == "legal_agent_001"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_capability_match_skips_overloaded_agent(router: AgentRouterAgent):
    overloaded = _make_manifest("overloaded_agent", capabilities=["contracts"], current_load=0.95)
    normal = _make_manifest("normal_agent", capabilities=["contracts"], current_load=0.5)
    await router.register(overloaded)
    await router.register(normal)
    result = router.capability_match(["contracts"])
    assert result == "normal_agent"


@pytest.mark.unit
def test_capability_match_returns_none_on_empty_caps(router: AgentRouterAgent):
    result = router.capability_match([])
    assert result is None


@pytest.mark.unit
def test_capability_match_returns_none_on_no_registered_agents(router: AgentRouterAgent):
    result = router.capability_match(["contracts"])
    assert result is None


# ===========================================================================
# route() 5-tier chain
# ===========================================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_route_cache_hit_skips_other_tiers(router: AgentRouterAgent):
    entry = RouteCacheEntry(agent_id="cached_agent_001", agent_type="", score=0.95)
    router._cache.set("legal task", ["legal"], tenant_id=42, entry=entry)
    task = _make_task(title="legal task", capabilities=["legal"])
    router._discovery_service = AsyncMock()
    result = await router.route(task)
    assert result == "cached_agent_001"
    router._discovery_service.find_best_agent_for_task.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_route_discovery_hit_caches_and_returns(router: AgentRouterAgent):
    task = _make_task(title="process invoice", capabilities=[])
    router._discovery_service = AsyncMock()
    router._discovery_service.find_best_agent_for_task.return_value = {
        "agent_id": "finance_agent_001"
    }
    result = await router.route(task)
    assert result == "finance_agent_001"
    # Should be cached after discovery hit
    cached = router._cache.get(task.title, [], tenant_id=42)
    assert cached is not None
    assert cached.agent_id == "finance_agent_001"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_route_capability_hit_when_discovery_misses(router: AgentRouterAgent):
    task = _make_task(title="analyze data", capabilities=["analytics"])
    router._discovery_service = AsyncMock()
    router._discovery_service.find_best_agent_for_task.return_value = None
    manifest = _make_manifest("data_agent_001", capabilities=["analytics"])
    await router.register(manifest)
    result = await router.route(task)
    assert result == "data_agent_001"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_route_llm_hit_when_upper_tiers_miss(router: AgentRouterAgent, monkeypatch):
    task = _make_task(title="classify document", capabilities=["ocr"])
    router._discovery_service = AsyncMock()
    router._discovery_service.find_best_agent_for_task.return_value = None
    # Register agent but with non-matching cap so cap match misses
    manifest = _make_manifest("doc_agent_001", capabilities=["document_processing"])
    await router.register(manifest)

    # Het taalmodel is dat van de TENANT van de router (`TenantTaalmodel`); geen echte aanroep (brief 2026-10-20).
    monkeypatch.setattr(
        "src.core.services.llm.tenant_deur.TenantTaalmodel.tekst",
        AsyncMock(return_value='{"agent_id": "doc_agent_001"}'),
    )

    result = await router.route(task)
    assert result == "doc_agent_001"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_route_fallback_when_all_tiers_miss(router: AgentRouterAgent):
    task = _make_task(title="unknown task", capabilities=[])
    router._discovery_service = AsyncMock()
    router._discovery_service.find_best_agent_for_task.return_value = None
    # No agents registered, no LLM client
    router.llm_client = None
    result = await router.route(task)
    assert result == "executor_agent_001"
    assert router._fallbacks_used == 1


# ===========================================================================
# route() tier 1.5 -- RedisRouteCacheTier (SP-ADR023-002 Dag 2 follow-up)
#
# Found by the independent review of Dag 2: RedisRouteCacheTier was constructed
# and assigned to _redis_cache_tier, but route() never read or wrote it -- the
# cross-worker cache existed in isolation, never on the actual routing path.
# ===========================================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_route_checks_redis_tier_on_in_memory_cache_miss(router: AgentRouterAgent):
    """route() must consult _redis_cache_tier (tier 1.5) when the in-memory
    cache (tier 1) misses, BEFORE falling through to DB discovery (tier 2)."""
    task = _make_task(title="redis cached task", capabilities=["legal"])
    router._discovery_service = AsyncMock()

    redis_entry = RouteCacheEntry(agent_id="redis_cached_agent_001", agent_type="", score=0.9)
    router._redis_cache_tier = AsyncMock()
    router._redis_cache_tier.get = AsyncMock(return_value=redis_entry)

    result = await router.route(task)

    assert result == "redis_cached_agent_001"
    router._redis_cache_tier.get.assert_awaited_once()
    router._discovery_service.find_best_agent_for_task.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_route_redis_tier_hit_populates_in_memory_cache(router: AgentRouterAgent):
    """A Redis-tier hit must populate the in-memory tier-1 cache too, so
    subsequent calls on the SAME worker hit tier 1 without another Redis round-trip."""
    task = _make_task(title="redis cached task 2", capabilities=[])
    router._discovery_service = AsyncMock()

    redis_entry = RouteCacheEntry(agent_id="redis_cached_agent_002", agent_type="", score=0.9)
    router._redis_cache_tier = AsyncMock()
    router._redis_cache_tier.get = AsyncMock(return_value=redis_entry)

    await router.route(task)

    in_memory = router._cache.get(task.title, [], tenant_id=router.tenant_id)
    assert in_memory is not None
    assert in_memory.agent_id == "redis_cached_agent_002"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_route_writes_to_redis_tier_after_discovery_hit(router: AgentRouterAgent):
    """A successful DB-discovery routing decision must be written to the Redis
    tier (not just the in-memory cache), so OTHER workers can reuse it."""
    task = _make_task(title="discovery task for redis write", capabilities=[])
    router._discovery_service = AsyncMock()
    router._discovery_service.find_best_agent_for_task.return_value = {
        "agent_id": "finance_agent_redis_001"
    }
    router._redis_cache_tier = AsyncMock()
    router._redis_cache_tier.get = AsyncMock(return_value=None)
    router._redis_cache_tier.set = AsyncMock()

    result = await router.route(task)

    assert result == "finance_agent_redis_001"
    router._redis_cache_tier.set.assert_awaited_once()
    call_args = router._redis_cache_tier.set.call_args
    written_entry = call_args.args[2] if len(call_args.args) > 2 else call_args.kwargs["entry"]
    assert written_entry.agent_id == "finance_agent_redis_001"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_route_without_redis_tier_stays_fail_graceful(router: AgentRouterAgent):
    """Without a Redis tier (_redis_cache_tier is None, the default), route()
    must behave exactly as before -- no regression for single-worker deployments."""
    task = _make_task(title="no redis tier task", capabilities=[])
    router._discovery_service = AsyncMock()
    router._discovery_service.find_best_agent_for_task.return_value = {"agent_id": "agent_x"}
    assert router._redis_cache_tier is None

    result = await router.route(task)

    assert result == "agent_x"


# ===========================================================================
# _discovery_route tests
# ===========================================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_discovery_route_returns_none_when_service_not_initialized(
    router: AgentRouterAgent,
):
    router._discovery_service = None
    task = _make_task()
    result = await router._discovery_route(task)
    assert result is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_discovery_route_returns_agent_id_on_hit(router: AgentRouterAgent):
    task = _make_task(description="write legal contract")
    router._discovery_service = AsyncMock()
    router._discovery_service.find_best_agent_for_task.return_value = {
        "agent_id": "legal_agent_001"
    }
    result = await router._discovery_route(task)
    assert result == "legal_agent_001"
    assert router._discovery_hits == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_discovery_route_returns_none_on_exception(router: AgentRouterAgent):
    task = _make_task()
    router._discovery_service = AsyncMock()
    router._discovery_service.find_best_agent_for_task.side_effect = RuntimeError(
        "DB connection failed"
    )
    result = await router._discovery_route(task)
    assert result is None


# ===========================================================================
# metrics() tests
# ===========================================================================


@pytest.mark.unit
def test_metrics_returns_all_expected_keys(router: AgentRouterAgent):
    m = router.metrics()
    expected_keys = {
        "routes_total",
        "cache_hits",
        "discovery_hits",
        "fallbacks_used",
        "registered_agents",
        "cache_hit_rate",
    }
    assert expected_keys.issubset(m.keys())


@pytest.mark.unit
@pytest.mark.asyncio
async def test_metrics_discovery_hits_counted(router: AgentRouterAgent):
    task = _make_task(description="process contract")
    router._discovery_service = AsyncMock()
    router._discovery_service.find_best_agent_for_task.return_value = {
        "agent_id": "legal_agent_001"
    }
    await router.route(task)
    m = router.metrics()
    assert m["discovery_hits"] == 1
    assert m["routes_total"] == 1


# ===========================================================================
# Singleton get_agent_router tests
# ===========================================================================


@pytest.mark.unit
def test_get_agent_router_same_tenant_same_instance():
    import src.core.agents.agent_router_agent as ara_module

    # Clear singleton state for test isolation
    original_instances = ara_module._instances.copy()
    ara_module._instances.clear()

    try:
        with patch.object(
            AgentRouterAgent,
            "__init__",
            lambda self, agent_id="", tenant_id=1, async_session_factory=None: _patched_init(
                self, agent_id, tenant_id
            ),
        ):
            r1 = get_agent_router(tenant_id=99)
            r2 = get_agent_router(tenant_id=99)
            assert r1 is r2
    finally:
        ara_module._instances.clear()
        ara_module._instances.update(original_instances)


@pytest.mark.unit
def test_get_agent_router_different_tenant_different_instance():
    import src.core.agents.agent_router_agent as ara_module

    original_instances = ara_module._instances.copy()
    ara_module._instances.clear()

    try:
        with patch.object(
            AgentRouterAgent,
            "__init__",
            lambda self, agent_id="", tenant_id=1, async_session_factory=None: _patched_init(
                self, agent_id, tenant_id
            ),
        ):
            r1 = get_agent_router(tenant_id=10)
            r2 = get_agent_router(tenant_id=20)
            assert r1 is not r2
    finally:
        ara_module._instances.clear()
        ara_module._instances.update(original_instances)


# ---------------------------------------------------------------------------
# Helper for singleton tests: minimal __init__ replacement
# ---------------------------------------------------------------------------


def _patched_init(self: AgentRouterAgent, agent_id: str, tenant_id: int) -> None:
    """Minimal __init__ replacement used in singleton tests."""
    import asyncio
    from collections import defaultdict
    from src.core.agents.agent_router_agent import RouteCache

    self._agent_id = agent_id
    self.tenant_id = tenant_id
    self.specialization = "intent_based_task_routing"
    self.llm_client = None
    self._manifests = {}
    self._manifests_lock = asyncio.Lock()
    self._cap_index = defaultdict(list)
    self._cache = RouteCache(ttl_seconds=300)
    self._discovery_service = None
    self._routes_total = 0
    self._cache_hits = 0
    self._discovery_hits = 0
    self._fallbacks_used = 0


# ===========================================================================
# Phase 2: Health-aware routing tests (Task 3)
# ===========================================================================


@pytest.mark.unit
@pytest.mark.asyncio
async def test_capability_match_prefers_healthier_agent(router: AgentRouterAgent):
    """Agent with higher health score wins over same-capability agent with worse metrics."""
    healthy = _make_manifest(
        "healthy_agent",
        capabilities=["contracts"],
        current_load=0.3,
    )
    healthy.success_rate = 0.95
    healthy.avg_latency_ms = 200.0

    degraded = _make_manifest(
        "degraded_agent",
        capabilities=["contracts"],
        current_load=0.3,
    )
    degraded.success_rate = 0.5
    degraded.avg_latency_ms = 4000.0

    await router.register(healthy)
    await router.register(degraded)
    result = router.capability_match(["contracts"])
    assert result == "healthy_agent"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_route_refreshes_load_from_tracker(router: AgentRouterAgent):
    """route() uses MGET to refresh manifest load from load tracker before routing."""
    from unittest.mock import AsyncMock

    manifest = _make_manifest("agent_001", capabilities=["contracts"])
    await router.register(manifest)

    mock_tracker = AsyncMock()
    mock_tracker.get_loads.return_value = {"agent_001": 0.8}
    router._load_tracker = mock_tracker

    task = _make_task(title="draft contract", capabilities=["contracts"])
    router._discovery_service = AsyncMock()
    router._discovery_service.find_best_agent_for_task.return_value = None

    await router.route(task)

    mock_tracker.get_loads.assert_awaited_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_route_excludes_overloaded_agent_in_capability_match(router: AgentRouterAgent):
    """route()'s capability-match tier omits agents with current_load >= 0.9.

    route_with_fallback_chain() (the method this test used to target) was
    removed as dead code -- route() already performs the same overload
    exclusion via its own composite-scoring tier (see _composite()/current_load
    check in agent_router_agent.py)."""
    overloaded = _make_manifest("overloaded_agent", capabilities=["contracts"], current_load=0.95)
    normal = _make_manifest("normal_agent", capabilities=["contracts"], current_load=0.4)
    await router.register(overloaded)
    await router.register(normal)
    router._discovery_service = AsyncMock()
    router._discovery_service.find_best_agent_for_task.return_value = None

    result = await router.route(_make_task(title="test", capabilities=["contracts"]))

    assert result == "normal_agent"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_all_agents_overloaded_falls_back_to_executor(router: AgentRouterAgent):
    """When every registered agent is overloaded, route() falls back to executor."""
    from unittest.mock import AsyncMock

    overloaded = _make_manifest("overloaded_agent", capabilities=["contracts"], current_load=0.95)
    await router.register(overloaded)

    router._discovery_service = AsyncMock()
    router._discovery_service.find_best_agent_for_task.return_value = None

    result = await router.route(_make_task(title="draft contract", capabilities=["contracts"]))
    assert result == "executor_agent_001"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_cache_hit_bypassed_for_overloaded_agent(router: AgentRouterAgent):
    """A cached agent with current_load >= 0.9 is skipped; routing falls through."""
    from unittest.mock import AsyncMock

    agent = _make_manifest("agent_001", capabilities=["contracts"], current_load=0.1)
    await router.register(agent)

    task = _make_task(title="draft contract", capabilities=["contracts"])
    router._discovery_service = AsyncMock()
    router._discovery_service.find_best_agent_for_task.return_value = None

    # Warm the cache with a low-load hit
    first = await router.route(task)
    assert first == "agent_001"

    # Now mark the agent overloaded — cache hit should be skipped
    router._manifests["agent_001"].current_load = 0.95
    second = await router.route(task)
    # Falls through capability-match (overloaded, skipped) to executor fallback
    assert second == "executor_agent_001"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_llm_route_falls_back_to_token_match_on_non_json_response(
    router: AgentRouterAgent, monkeypatch
):
    """When the model ignores response_model and returns free text (e.g. a
    local/heuristic tier without JSON mode), _llm_route() degrades to matching
    a known agent_id token instead of returning None outright."""
    manifest = _make_manifest("doc_agent_001", capabilities=["document_processing"])
    await router.register(manifest)

    # Het taalmodel is dat van de TENANT van de router (`TenantTaalmodel`); geen echte aanroep (brief 2026-10-20).
    monkeypatch.setattr(
        "src.core.services.llm.tenant_deur.TenantTaalmodel.tekst",
        AsyncMock(return_value="I believe doc_agent_001 is the best match."),
    )

    result = await router._llm_route(_make_task(title="classify document"))
    assert result == "doc_agent_001"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_llm_route_returns_none_on_malformed_response(router: AgentRouterAgent, monkeypatch):
    """A structured response naming an unknown agent_id must return None, not
    crash or route to a nonexistent agent."""
    manifest = _make_manifest("doc_agent_001", capabilities=["document_processing"])
    await router.register(manifest)

    # Het taalmodel is dat van de TENANT van de router (`TenantTaalmodel`); geen echte aanroep (brief 2026-10-20).
    monkeypatch.setattr(
        "src.core.services.llm.tenant_deur.TenantTaalmodel.tekst",
        AsyncMock(return_value='{"agent_id": "nonexistent_agent"}'),
    )

    result = await router._llm_route(_make_task(title="classify document"))
    assert result is None


@pytest.mark.unit
def test_llm_route_no_testing_env_branch():
    """The TESTING=1/Mock-detection production-code hack must never come back --
    _llm_route() must always use the real routing path, never branch on the
    test environment."""
    import inspect

    from src.core.agents.agent_router_agent import AgentRouterAgent

    source = inspect.getsource(AgentRouterAgent._llm_route)
    assert 'os.getenv("TESTING")' not in source
    assert "unittest.mock" not in source


# ===========================================================================
# _execute_task() -- process_task() entrypoint (previously untested: this
# uncovered 3 real crash bugs, see mypy fix): self.async_session_factory()
# (attribute didn't exist -- always self._async_session_factory), the
# RedisRouteCacheTier None-narrowing, and record_usage()'s wrong kwargs.
# ===========================================================================


class _FakeAsyncSessionCtx:
    async def __aenter__(self):
        return MagicMock()

    async def __aexit__(self, *args):
        return None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_task_routes_and_records_usage_with_session_factory(
    router: AgentRouterAgent,
):
    """_execute_task() must use self._async_session_factory (not the
    nonexistent self.async_session_factory) and call BudgetManager.record_usage
    with its real kwargs (tokens_used, cost_usd), not input_tokens/output_tokens."""
    router._async_session_factory = MagicMock(return_value=_FakeAsyncSessionCtx())
    manifest = _make_manifest("agent_001")
    await router.register(manifest)

    with patch("src.core.agents.budget_manager.BudgetManager") as mock_budget_cls:
        mock_budget = AsyncMock()
        mock_budget.check_budget.return_value = MagicMock(allowed=True, reason=None)
        mock_budget_cls.return_value = mock_budget

        result = await router._execute_task(_make_task(title="draft contract"))

        assert result.success is True
        mock_budget.check_budget.assert_awaited_once()
        mock_budget.record_usage.assert_awaited_once()
        call_kwargs = mock_budget.record_usage.call_args.kwargs
        assert call_kwargs["tokens_used"] == 300
        assert "cost_usd" in call_kwargs


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_task_blocked_when_budget_exceeded(router: AgentRouterAgent):
    """When BudgetManager denies the request, _execute_task() must return a
    failed ExecutionResult and never proceed to route()/record_usage()."""
    router._async_session_factory = MagicMock(return_value=_FakeAsyncSessionCtx())
    manifest = _make_manifest("agent_001")
    await router.register(manifest)

    with patch("src.core.agents.budget_manager.BudgetManager") as mock_budget_cls:
        mock_budget = AsyncMock()
        mock_budget.check_budget.return_value = MagicMock(
            allowed=False, reason="Monthly token limit reached"
        )
        mock_budget_cls.return_value = mock_budget

        result = await router._execute_task(_make_task(title="draft contract"))

        assert result.success is False
        assert "Budget exceeded" in str(result.result_data)
        mock_budget.record_usage.assert_not_awaited()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_execute_task_skips_budget_tracking_without_session_factory(
    router: AgentRouterAgent,
):
    """Without a configured session factory (e.g. lightweight/test agents),
    _execute_task() must still route successfully -- fail-graceful, not crash."""
    router._async_session_factory = None
    manifest = _make_manifest("agent_001")
    await router.register(manifest)

    result = await router._execute_task(
        _make_task(title="draft contract", capabilities=["contracts"])
    )

    assert result.success is True
    assert result.result_data == {"routed_to": "agent_001"}
