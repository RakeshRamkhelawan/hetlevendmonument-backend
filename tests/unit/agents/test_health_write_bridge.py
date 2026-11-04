"""Tests for AgentHealthMonitorAgent -> AgentRouterAgent write-bridge (CG-005).

TDD: these tests are written RED-first. They will fail until the write-bridge
and RedisRouteCacheTier are implemented in SP-WE-10.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock

from src.core.agents.agent_router_agent import AgentManifest, AgentRouterAgent
from src.core.agents.agent_health_monitor_agent import (
    AgentHealthMonitorAgent,
    HealthStatus,
)


# ---------------------------------------------------------------------------
# Test 1: manifest.health_status is updated after status transition
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_manifest_health_status_updated_on_transition() -> None:
    """RED: manifest.health_status should change from UNKNOWN to WARNING
    after monitor records failures and runs _check_all.
    Without write-bridge this test FAILS (set_router AttributeError).
    """
    router = AgentRouterAgent(tenant_id=42)
    monitor = AgentHealthMonitorAgent(tenant_id=42)
    monitor.set_router(router)

    manifest = AgentManifest(
        agent_id="test_agent_001",
        agent_type="executor",
        capabilities=["task_execution"],
        department="ops",
    )
    await router.register(manifest)

    # Record 5 failures -- should trigger WARNING or CRITICAL
    for _ in range(5):
        await monitor._process_record(
            agent_id="test_agent_001",
            agent_type="executor",
            latency_ms=6000.0,
            success=False,
        )

    await monitor._check_all()

    updated = router.get_manifest("test_agent_001")
    assert updated is not None
    assert updated.health_status != "UNKNOWN", (
        f"Expected health_status to be updated from UNKNOWN, got {updated.health_status!r}"
    )


# ---------------------------------------------------------------------------
# Test 2: HealthScorer penalizes CRITICAL agent after write-bridge update
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_health_scorer_penalizes_critical_agent() -> None:
    """RED: routing score should drop significantly after CRITICAL status.
    Without write-bridge health_status stays UNKNOWN -- score stays ~0.43.
    """
    from src.core.agents.health_scorer import HealthScorer

    router = AgentRouterAgent(tenant_id=42)
    monitor = AgentHealthMonitorAgent(tenant_id=42)
    monitor.set_router(router)

    manifest = AgentManifest(
        agent_id="critical_agent_001",
        agent_type="executor",
        capabilities=["risky_task"],
        department="ops",
        success_rate=0.1,
        avg_latency_ms=9000.0,
    )
    await router.register(manifest)

    # Force status transitions via _process_record + _check_all
    for _ in range(5):
        await monitor._process_record("critical_agent_001", "executor", 9000.0, False)
    await monitor._check_all()

    updated = router.get_manifest("critical_agent_001")
    assert updated is not None
    score = HealthScorer.score_manifest(updated)
    assert score < 0.3, (
        f"Expected score < 0.3 for degraded agent, got {score:.4f} "
        f"(health_status={updated.health_status!r})"
    )


# ---------------------------------------------------------------------------
# Test 3: RedisRouteCacheTier -- miss falls through to None
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.als
@pytest.mark.asyncio
async def test_redis_cache_tier_miss_falls_through() -> None:
    """RED: RedisRouteCacheTier.get returns None on miss -- ImportError before fix."""
    from src.core.agents.agent_router_agent import RedisRouteCacheTier  # noqa: PLC0415

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)

    tier = RedisRouteCacheTier(redis_client=mock_redis, ttl_seconds=60)
    result = await tier.get("sha256key_abc", tenant_id=99)
    assert result is None
    mock_redis.get.assert_called_once()


# ---------------------------------------------------------------------------
# Test 4: Tenant isolation -- monitor for tenant 1 does NOT update router for tenant 2
# ---------------------------------------------------------------------------


@pytest.mark.unit
@pytest.mark.security
@pytest.mark.asyncio
async def test_health_bridge_tenant_isolation() -> None:
    """Tenant A's monitor must NOT update tenant B's router manifests."""
    router_1 = AgentRouterAgent(agent_id="router_001", tenant_id=1)
    router_2 = AgentRouterAgent(agent_id="router_002", tenant_id=2)
    monitor_1 = AgentHealthMonitorAgent(agent_id="monitor_001", tenant_id=1)
    monitor_1.set_router(router_1)  # wired to tenant 1's router only

    manifest = AgentManifest(
        agent_id="shared_agent_name",
        agent_type="executor",
        capabilities=["task"],
        department="ops",
    )
    await router_2.register(manifest)

    # Record failures on monitor_1 for an agent that only exists in router_2
    for _ in range(5):
        await monitor_1._process_record("shared_agent_name", "executor", 9000.0, False)
    await monitor_1._check_all()

    # router_2's manifest must NOT be affected (monitor_1 is wired to router_1 only)
    m = router_2.get_manifest("shared_agent_name")
    assert m is not None
    assert m.health_status == "UNKNOWN", (
        f"router_2 manifest should stay UNKNOWN but got {m.health_status!r}"
    )
