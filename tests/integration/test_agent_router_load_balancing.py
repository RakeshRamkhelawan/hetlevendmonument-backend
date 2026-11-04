"""Integration tests for health-aware and load-balanced routing in AgentRouterAgent.

These tests use TESTING=1 (SQLite) and mock external dependencies (Redis, LLM)
to verify the routing chain end-to-end without a real PostgreSQL database.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock

import pytest

os.environ.setdefault("TESTING", "1")

from src.core.agents.agent_router_agent import (
    AgentManifest,
    AgentRouterAgent,
    RouteCache,
    RouteCacheEntry,
)
from src.core.agents.health_scorer import HealthScorer
from src.core.shared.interfaces import TaskData


def _make_manifest(
    agent_id: str,
    capabilities: list[str] | None = None,
    current_load: float = 0.0,
    success_rate: float = 1.0,
    avg_latency_ms: float = 100.0,
) -> AgentManifest:
    m = AgentManifest(
        agent_id=agent_id,
        agent_type="specialist",
        capabilities=capabilities or ["general"],
        department="general",
        current_load=current_load,
    )
    m.success_rate = success_rate
    m.avg_latency_ms = avg_latency_ms
    return m


def _make_task(
    title: str = "test task",
    capabilities: list[str] | None = None,
) -> TaskData:
    meta: dict[str, list[str]] = {}
    if capabilities:
        meta["capabilities"] = capabilities
    return TaskData(id="t1", title=title, description="desc", metadata=meta)


def _build_router(tenant_id: int = 1) -> AgentRouterAgent:
    """Build a real AgentRouterAgent (TESTING=1, no DB session factory).

    NOTE: dit ging eerder via `AgentRouterAgent.__new__()` met 13 handmatig gezette
    attributen. Toen productiecode `self._redis_cache_tier` kreeg
    (agent_router_agent.py:262) liep die kopie achter en gooide `route()` een
    AttributeError -- 5 tests rood, wekenlang onopgemerkt (OP-11 cluster C). De echte
    constructor werkt in de testomgeving, dus die gebruiken we: nieuwe attributen
    komen nu automatisch mee.
    """
    router = AgentRouterAgent(agent_id=f"router_{tenant_id}", tenant_id=tenant_id)
    router.llm_client = None
    router._discovery_service = None
    router._load_tracker = None
    return router


# ===========================================================================
# Health-based routing ordering
# ===========================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_health_score_determines_routing_order():
    """route() selects the healthiest agent when multiple match the capability."""
    router = _build_router()
    healthy = _make_manifest(
        "healthy_agent",
        ["contracts"],
        current_load=0.2,
        success_rate=0.98,
        avg_latency_ms=150.0,
    )
    degraded = _make_manifest(
        "degraded_agent",
        ["contracts"],
        current_load=0.2,
        success_rate=0.4,
        avg_latency_ms=4500.0,
    )
    await router.register(healthy)
    await router.register(degraded)

    router._discovery_service = AsyncMock()
    router._discovery_service.find_best_agent_for_task.return_value = None

    result = await router.route(_make_task("draft contract", ["contracts"]))
    assert result == "healthy_agent"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_overloaded_agent_excluded_from_routing():
    """route() never returns an agent with current_load >= 0.9."""
    router = _build_router()
    overloaded = _make_manifest("overloaded_agent", ["contracts"], current_load=0.92)
    normal = _make_manifest("normal_agent", ["contracts"], current_load=0.5)
    await router.register(overloaded)
    await router.register(normal)

    router._discovery_service = AsyncMock()
    router._discovery_service.find_best_agent_for_task.return_value = None

    result = await router.route(_make_task("draft contract", ["contracts"]))
    assert result == "normal_agent"


# ===========================================================================
# Redis load refresh via MGET
# ===========================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_redis_load_refresh_updates_manifest_before_routing():
    """route() refreshes load from Redis before capability-match tier."""
    router = _build_router()
    agent = _make_manifest("target_agent", ["analytics"], current_load=0.1)
    await router.register(agent)

    mock_tracker = AsyncMock()
    mock_tracker.get_loads.return_value = {"target_agent": 0.85}
    router._load_tracker = mock_tracker

    router._discovery_service = AsyncMock()
    router._discovery_service.find_best_agent_for_task.return_value = None

    await router.route(_make_task("analyze data", ["analytics"]))

    # Manifest load should be refreshed from Redis
    assert router._manifests["target_agent"].current_load == pytest.approx(0.85)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_redis_unavailable_falls_back_to_in_memory_load():
    """route() continues with in-memory load values when AgentLoadTracker returns empty dict.

    AgentLoadTracker absorbs Redis errors internally and returns {} on failure.
    route() must still select the best in-memory candidate when get_loads returns {}.
    """
    router = _build_router()
    agent = _make_manifest("target_agent", ["analytics"], current_load=0.3)
    await router.register(agent)

    # Simulate AgentLoadTracker returning empty dict on Redis unavailability
    mock_tracker = AsyncMock()
    mock_tracker.get_loads.return_value = {}
    router._load_tracker = mock_tracker

    router._discovery_service = AsyncMock()
    router._discovery_service.find_best_agent_for_task.return_value = None

    # In-memory load (0.3) is used; routing succeeds
    result = await router.route(_make_task("analyze data", ["analytics"]))
    assert result == "target_agent"
    # In-memory load unchanged (no Redis data to refresh from)
    assert router._manifests["target_agent"].current_load == pytest.approx(0.3)


# ===========================================================================
# Health score per manifest
#
# NOTE (OP-11 cluster D): deze sectie testte `route_with_fallback_chain()`, een
# publieke methode die op 2026-07-09 uit agent_router_agent.py is verwijderd
# (commit fcbb5354) zonder opvolger; de fallback-logica leeft nu binnen `route()`
# (`_fallbacks_used`). De twee tests bleven achter en riepen een niet-bestaande
# methode aan.
# - De overload-uitsluiting was een duplicaat van
#   test_overloaded_agent_excluded_from_routing hierboven (via de echte `route()`)
#   en is daarom verwijderd, niet herschreven.
# - De health-score-invariant is wel unieke dekking en staat hieronder, direct op
#   HealthScorer.score_manifest -- de functie die `route()` gebruikt om een
#   gezondere agent te laten voorgaan.
# ===========================================================================


@pytest.mark.integration
def test_health_score_is_bounded_for_a_manifest():
    """HealthScorer geeft een score in [0.0, 1.0] voor een manifest."""
    manifest = _make_manifest(
        "test_agent",
        ["contracts"],
        success_rate=0.9,
        avg_latency_ms=300.0,
    )

    score = HealthScorer.score_manifest(manifest)

    assert 0.0 <= score <= 1.0


@pytest.mark.integration
def test_health_score_prefers_the_healthier_manifest():
    """Een agent met hogere success_rate en lagere latency scoort hoger."""
    healthy = _make_manifest("healthy", ["contracts"], success_rate=0.98, avg_latency_ms=150.0)
    degraded = _make_manifest("degraded", ["contracts"], success_rate=0.4, avg_latency_ms=4500.0)

    assert HealthScorer.score_manifest(healthy) > HealthScorer.score_manifest(degraded)


# ===========================================================================
# find_agents_by_functions (TESTING path)
# ===========================================================================


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_agents_by_functions_returns_matching_agents():
    """find_agents_by_functions() TESTING path returns agents with matching caps."""
    from src.core.agents.agent_discovery import AgentDiscoveryService

    agent_a = MagicMock()
    agent_a.capabilities = ["contracts", "legal"]
    agent_a.agent_id = "legal_agent_001"

    agent_b = MagicMock()
    agent_b.capabilities = ["analytics"]
    agent_b.agent_id = "data_agent_001"

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [agent_a, agent_b]
    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_result

    svc = AgentDiscoveryService.__new__(AgentDiscoveryService)
    svc._tenant_id = 1
    svc._ttl = 300
    svc._cache = {}
    svc._db_session = mock_session
    svc._async_session_factory = None

    result = await svc.find_agents_by_functions(["contracts"])

    assert any(a.agent_id == "legal_agent_001" for a in result)
    assert all(a.agent_id != "data_agent_001" for a in result)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_find_agents_by_functions_respects_limit():
    """find_agents_by_functions() never returns more than limit agents."""
    from src.core.agents.agent_discovery import AgentDiscoveryService

    agents = [MagicMock(capabilities=["contracts"], agent_id=f"a_{i}") for i in range(10)]

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = agents
    mock_session = AsyncMock()
    mock_session.execute.return_value = mock_result

    svc = AgentDiscoveryService.__new__(AgentDiscoveryService)
    svc._tenant_id = 1
    svc._ttl = 300
    svc._cache = {}
    svc._db_session = mock_session
    svc._async_session_factory = None

    result = await svc.find_agents_by_functions(["contracts"], limit=4)

    assert len(result) == 4


# ===========================================================================
# Tenant isolation
# ===========================================================================


@pytest.mark.integration
def test_routers_for_different_tenants_are_isolated():
    """Two routers with different tenant_ids do not share manifests."""
    router_a = _build_router(tenant_id=1)
    router_b = _build_router(tenant_id=2)

    router_a._manifests["agent_t1"] = _make_manifest("agent_t1", ["contracts"])

    assert "agent_t1" in router_a._manifests
    assert "agent_t1" not in router_b._manifests


@pytest.mark.integration
@pytest.mark.asyncio
async def test_route_cache_is_tenant_scoped():
    """Cache entries from tenant 1 are not visible to tenant 2."""
    cache_a = RouteCache(ttl_seconds=300)
    cache_b = RouteCache(ttl_seconds=300)

    entry = RouteCacheEntry(agent_id="legal_agent_001", agent_type="specialist", score=0.9)
    cache_a.set("draft contract", ["contracts"], tenant_id=1, entry=entry)

    result_same = cache_a.get("draft contract", ["contracts"], tenant_id=1)
    result_other = cache_b.get("draft contract", ["contracts"], tenant_id=2)
    # Same cache instance, different tenant: key must be tenant-scoped
    result_cross = cache_a.get("draft contract", ["contracts"], tenant_id=2)

    assert result_same is not None
    assert result_other is None
    assert result_cross is None


# ===========================================================================
# Health scorer accuracy
# ===========================================================================


@pytest.mark.integration
def test_health_scorer_formula_end_to_end():
    """HealthScorer produces the expected composite score for known inputs."""
    score = HealthScorer.score(
        success_rate=0.9,
        avg_latency_ms=1000.0,
        health_status="HEALTHY",
    )
    # 0.9*0.4 + (1-1000/5000)*0.3 + 1.0*0.3 = 0.36 + 0.24 + 0.30 = 0.90
    assert score == pytest.approx(0.90, abs=0.001)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_routing_chain_contract_task_to_legal_agent():
    """End-to-end: contract task routes to legal agent via capability-match tier."""
    router = _build_router()
    legal = _make_manifest(
        "legal_agent_001",
        ["contracts", "legal"],
        current_load=0.2,
        success_rate=0.95,
    )
    data = _make_manifest(
        "data_agent_001",
        ["analytics"],
        current_load=0.1,
        success_rate=0.99,
    )
    await router.register(legal)
    await router.register(data)

    router._discovery_service = AsyncMock()
    router._discovery_service.find_best_agent_for_task.return_value = None

    result = await router.route(_make_task("draft a legal contract", ["contracts"]))
    assert result == "legal_agent_001"
