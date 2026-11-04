"""Rode tests -- SP-ADR023-002 Dag 3 -- Prometheus-metrics op AgentRouterAgent.route().

Tests zijn ROOD totdat agent_router_decision_latency_seconds en
agent_router_cache_result_total bestaan in src/core/observability/metrics.py EN
daadwerkelijk worden aangeroepen op elk van de 6 tiers in route(). Volgt het
gevestigde testpatroon van tests/unit/agents/test_critique_metrics.py (SP-AGT-007):
patch de metric-objecten op de CONSUMERENDE module, assert .labels(...) + .observe()/.inc().
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.agents.agent_router_agent import AgentManifest, AgentRouterAgent, RouteCache
from src.core.shared.interfaces import TaskData


def _make_task(title: str = "metrics task", capabilities: list[str] | None = None) -> TaskData:
    metadata: dict = {}
    if capabilities:
        metadata["capabilities"] = capabilities
    return TaskData(id="t-metrics", title=title, description="d", metadata=metadata)


@pytest.fixture
def router() -> AgentRouterAgent:
    """Same minimal construction pattern as tests/unit/test_agent_router_agent.py."""
    r = AgentRouterAgent.__new__(AgentRouterAgent)
    r._agent_id = "test_router_metrics"
    r.tenant_id = 77
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
    return r


@pytest.mark.unit
@pytest.mark.asyncio
async def test_route_observes_latency_on_in_memory_cache_hit(router: AgentRouterAgent) -> None:
    from src.core.agents.agent_router_agent import RouteCacheEntry

    task = _make_task(title="cached task", capabilities=["legal"])
    router._cache.set(
        "cached task",
        ["legal"],
        router.tenant_id,
        RouteCacheEntry(agent_id="cached_agent", agent_type="", score=0.95),
    )
    router._discovery_service = AsyncMock()

    with patch(
        "src.core.agents.agent_router_agent.agent_router_decision_latency_seconds"
    ) as mock_hist:
        mock_obs = MagicMock()
        mock_hist.labels.return_value = mock_obs
        result = await router.route(task)

    assert result == "cached_agent"
    mock_hist.labels.assert_called_once_with(tenant_id="77", tier="in_memory")
    mock_obs.observe.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_route_observes_latency_on_redis_cache_hit(router: AgentRouterAgent) -> None:
    from src.core.agents.agent_router_agent import RouteCacheEntry

    task = _make_task(title="redis task", capabilities=[])
    router._redis_cache_tier = AsyncMock()
    router._redis_cache_tier.get = AsyncMock(
        return_value=RouteCacheEntry(agent_id="redis_agent", agent_type="", score=0.9)
    )
    router._discovery_service = AsyncMock()

    with patch(
        "src.core.agents.agent_router_agent.agent_router_decision_latency_seconds"
    ) as mock_hist:
        mock_obs = MagicMock()
        mock_hist.labels.return_value = mock_obs
        result = await router.route(task)

    assert result == "redis_agent"
    mock_hist.labels.assert_called_once_with(tenant_id="77", tier="redis")
    mock_obs.observe.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_route_observes_latency_on_discovery_hit(router: AgentRouterAgent) -> None:
    task = _make_task(title="discovery task", capabilities=[])
    router._discovery_service = AsyncMock()
    router._discovery_service.find_best_agent_for_task.return_value = {
        "agent_id": "discovery_agent"
    }

    with patch(
        "src.core.agents.agent_router_agent.agent_router_decision_latency_seconds"
    ) as mock_hist:
        mock_obs = MagicMock()
        mock_hist.labels.return_value = mock_obs
        result = await router.route(task)

    assert result == "discovery_agent"
    mock_hist.labels.assert_called_once_with(tenant_id="77", tier="discovery")
    mock_obs.observe.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_route_observes_latency_on_capability_hit(router: AgentRouterAgent) -> None:
    task = _make_task(title="capability task", capabilities=["analytics"])
    router._discovery_service = AsyncMock()
    router._discovery_service.find_best_agent_for_task.return_value = None
    await router.register(
        AgentManifest(
            agent_id="cap_agent",
            agent_type="specialist",
            capabilities=["analytics"],
            department="d",
        )
    )

    with patch(
        "src.core.agents.agent_router_agent.agent_router_decision_latency_seconds"
    ) as mock_hist:
        mock_obs = MagicMock()
        mock_hist.labels.return_value = mock_obs
        result = await router.route(task)

    assert result == "cap_agent"
    mock_hist.labels.assert_called_once_with(tenant_id="77", tier="capability")
    mock_obs.observe.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_route_observes_latency_on_llm_hit(router: AgentRouterAgent) -> None:
    task = _make_task(title="llm task", capabilities=["ocr"])
    router._discovery_service = AsyncMock()
    router._discovery_service.find_best_agent_for_task.return_value = None
    await router.register(
        AgentManifest(
            agent_id="doc_agent", agent_type="specialist", capabilities=["other"], department="d"
        )
    )
    # `_llm_route()` praat met het model van de TENANT van de router (`TenantTaalmodel`, brief 2026-10-20).
    # Dat moet gemockt worden, anders is dit geen unit test: de echte aanroep zou een database en een model
    # nodig hebben.
    router.llm_client = MagicMock()
    router.llm_client.tekst = AsyncMock(return_value='{"agent_id": "doc_agent"}')

    with (
        patch(
            "src.core.agents.agent_router_agent.agent_router_decision_latency_seconds"
        ) as mock_hist,
    ):
        mock_obs = MagicMock()
        mock_hist.labels.return_value = mock_obs
        result = await router.route(task)

    assert result == "doc_agent"
    mock_hist.labels.assert_called_once_with(tenant_id="77", tier="llm")
    mock_obs.observe.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_route_observes_latency_on_fallback(router: AgentRouterAgent) -> None:
    task = _make_task(title="unknown task", capabilities=[])
    router._discovery_service = AsyncMock()
    router._discovery_service.find_best_agent_for_task.return_value = None
    router.llm_client = None

    with patch(
        "src.core.agents.agent_router_agent.agent_router_decision_latency_seconds"
    ) as mock_hist:
        mock_obs = MagicMock()
        mock_hist.labels.return_value = mock_obs
        result = await router.route(task)

    assert result == "executor_agent_001"
    mock_hist.labels.assert_called_once_with(tenant_id="77", tier="fallback")
    mock_obs.observe.assert_called_once()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_route_increments_cache_result_counter_for_in_memory_and_redis_miss(
    router: AgentRouterAgent,
) -> None:
    """Both the in-memory tier and the Redis tier must record a 'miss' when
    neither has an entry, before falling through to discovery."""
    task = _make_task(title="cache miss task", capabilities=[])
    router._redis_cache_tier = AsyncMock()
    router._redis_cache_tier.get = AsyncMock(return_value=None)
    router._discovery_service = AsyncMock()
    router._discovery_service.find_best_agent_for_task.return_value = {"agent_id": "agent_x"}

    with patch(
        "src.core.agents.agent_router_agent.agent_router_cache_result_total"
    ) as mock_counter:
        mock_inc = MagicMock()
        mock_counter.labels.return_value = mock_inc
        await router.route(task)

    mock_counter.labels.assert_any_call(tenant_id="77", tier="in_memory", result="miss")
    mock_counter.labels.assert_any_call(tenant_id="77", tier="redis", result="miss")
    assert mock_inc.inc.call_count == 2


@pytest.mark.unit
@pytest.mark.asyncio
async def test_route_does_not_emit_in_memory_latency_when_cache_hit_is_overloaded(
    router: AgentRouterAgent,
) -> None:
    """An in-memory cache hit whose manifest is overloaded (load >= 0.9) does
    NOT return -- it falls through to the next tier. The latency histogram
    must therefore never be observed with tier='in_memory' for this call;
    only the tier that actually resolves the route may be observed. Guards
    against scoping the .observe() call to the outer 'if cached:' block
    instead of the specific 'return cached.agent_id' line (Gate 2 review note)."""
    from src.core.agents.agent_router_agent import RouteCacheEntry

    task = _make_task(title="overloaded task", capabilities=["legal"])
    router._cache.set(
        "overloaded task",
        ["legal"],
        router.tenant_id,
        RouteCacheEntry(agent_id="overloaded_agent", agent_type="", score=0.95),
    )
    router._manifests["overloaded_agent"] = AgentManifest(
        agent_id="overloaded_agent",
        agent_type="specialist",
        capabilities=["legal"],
        department="d",
        current_load=0.95,
    )
    router._discovery_service = AsyncMock()
    router._discovery_service.find_best_agent_for_task.return_value = {
        "agent_id": "discovery_agent"
    }

    with patch(
        "src.core.agents.agent_router_agent.agent_router_decision_latency_seconds"
    ) as mock_hist:
        mock_obs = MagicMock()
        mock_hist.labels.return_value = mock_obs
        result = await router.route(task)

    assert result == "discovery_agent"
    for call in mock_hist.labels.call_args_list:
        assert call.kwargs.get("tier") != "in_memory", (
            "overloaded cache hit must not be counted as a resolved in_memory tier"
        )
    mock_hist.labels.assert_called_once_with(tenant_id="77", tier="discovery")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_route_does_not_increment_redis_cache_counter_when_tier_absent(
    router: AgentRouterAgent,
) -> None:
    """When _redis_cache_tier is None (single-worker / no Redis configured),
    the cache-result counter must only fire for the in_memory tier -- never
    for tier='redis', since that tier was never actually consulted."""
    task = _make_task(title="no redis task", capabilities=[])
    router._redis_cache_tier = None
    router._discovery_service = AsyncMock()
    router._discovery_service.find_best_agent_for_task.return_value = {"agent_id": "agent_y"}

    with patch(
        "src.core.agents.agent_router_agent.agent_router_cache_result_total"
    ) as mock_counter:
        mock_inc = MagicMock()
        mock_counter.labels.return_value = mock_inc
        await router.route(task)

    for call in mock_counter.labels.call_args_list:
        assert call.kwargs.get("tier") != "redis", (
            "redis tier counter must not fire when _redis_cache_tier is None"
        )
    mock_counter.labels.assert_any_call(tenant_id="77", tier="in_memory", result="miss")
