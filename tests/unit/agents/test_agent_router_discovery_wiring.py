"""Rode tests -- SP-ADR023-002 Dag 1 -- agent-discovery wiring in productie.

Voor de fix: `_init_agent_health_write_bridge` (app_lifespan.py) roept
`get_agent_router(tenant_id)` aan zonder `async_session_factory`, waardoor
`AgentDiscoveryService` stil terugvalt op lege resultaten (zie TODO(Rakesh) op
agent_router_agent.py:716-717).
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.unit
@pytest.mark.asyncio
async def test_agent_health_write_bridge_passes_async_session_factory() -> None:
    """_init_agent_health_write_bridge must call get_agent_router with a real
    async_session_factory (get_db_session), not None -- ADR-034 forbids importing
    src.core.database.database in the orchestration package, so this and
    dependencies.get_agent_router() both use the get_db_session facade instead."""
    import src.core.app_lifespan as lifespan_module
    from src.core.database.session import get_db_session

    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.all.return_value = [(1,)]
    mock_session.execute = AsyncMock(return_value=mock_result)

    mock_session_cm = AsyncMock()
    mock_session_cm.__aenter__.return_value = mock_session
    mock_session_cm.__aexit__.return_value = None

    mock_router = MagicMock()
    mock_monitor = AsyncMock()
    sentinel_redis = object()

    with (
        patch.object(lifespan_module.db_manager, "get_session", return_value=mock_session_cm),
        patch(
            "src.core.agents.agent_router_agent.get_agent_router", return_value=mock_router
        ) as mock_get_router,
        patch(
            "src.core.agents.agent_health_monitor_agent.get_health_monitor",
            return_value=mock_monitor,
        ),
        patch(
            "src.core.database.redis.get_redis_client",
            new=AsyncMock(return_value=sentinel_redis),
        ),
    ):
        await lifespan_module._init_agent_health_write_bridge(MagicMock())

    mock_get_router.assert_called_once_with(
        1, async_session_factory=get_db_session, redis_client=sentinel_redis
    )


@pytest.mark.unit
@pytest.mark.asyncio
async def test_router_initialize_wires_async_session_factory_into_discovery_service() -> None:
    """AgentRouterAgent.initialize() must construct its AgentDiscoveryService with
    the async_session_factory passed to the constructor -- proves the wiring reaches
    the actual discovery layer, not just that a kwarg is threaded through."""
    from src.core.agents.agent_router_agent import AgentRouterAgent

    @asynccontextmanager
    async def fake_factory():
        raise AssertionError("factory should not be invoked during initialize()")
        yield None  # pragma: no cover -- makes this an async generator, unreachable

    router = AgentRouterAgent(
        agent_id="test_router_wiring", tenant_id=1, async_session_factory=fake_factory
    )
    await router.initialize()

    assert router._discovery_service is not None
    assert router._discovery_service._async_session_factory is fake_factory


@pytest.mark.unit
@pytest.mark.asyncio
async def test_router_initialize_without_factory_stays_fail_graceful() -> None:
    """Without a factory, discovery must still initialize (fail-graceful) -- existing
    behaviour for call-sites that intentionally omit DB access must not regress."""
    from src.core.agents.agent_router_agent import AgentRouterAgent

    router = AgentRouterAgent(agent_id="test_router_no_factory", tenant_id=1)
    await router.initialize()

    assert router._discovery_service is not None
    assert router._discovery_service._async_session_factory is None


@pytest.mark.unit
def test_master_orchestrator_get_router_wires_async_session_factory() -> None:
    """MasterOrchestratorAgent._get_router() is a THIRD call-site of the consolidated
    AgentRouterAgent singleton (found by the independent review, FA-NEW-001) -- it
    must also pass async_session_factory, or a tenant whose first router access
    happens via an orchestrated workflow (before any /orchestration/* HTTP request)
    permanently locks that tenant's singleton without DB-backed discovery.

    The factory is injected via MasterOrchestratorAgent.__init__ (ADR-034: agents
    never import src.core.database themselves) and threaded through by _get_router()."""
    import src.core.agents.agent_router_agent as ara_module
    from src.core.agents.master_orchestrator_agent import MasterOrchestratorAgent
    from src.core.database.session import get_db_session

    tenant_id = 88804
    original = ara_module._instances.pop(tenant_id, None)
    try:
        with patch.object(MasterOrchestratorAgent, "_register_agent_profile", return_value=None):
            orchestrator = MasterOrchestratorAgent(
                agent_id="test_orch_fa_new_001",
                tenant_id=tenant_id,
                async_session_factory=get_db_session,
            )
        router = orchestrator._get_router()
        assert router._async_session_factory is get_db_session
    finally:
        ara_module._instances.pop(tenant_id, None)
        if original is not None:
            ara_module._instances[tenant_id] = original


@pytest.mark.unit
def test_master_orchestrator_without_factory_stays_none() -> None:
    """Without an injected factory, _async_session_factory stays None (fail-graceful,
    matches AgentRouterAgent's own default) -- no regression for call-sites that
    intentionally omit DB access."""
    from unittest.mock import patch as _patch

    from src.core.agents.master_orchestrator_agent import MasterOrchestratorAgent

    with _patch.object(MasterOrchestratorAgent, "_register_agent_profile", return_value=None):
        orchestrator = MasterOrchestratorAgent(agent_id="test_orch_no_factory", tenant_id=1)
    assert orchestrator._async_session_factory is None


@pytest.mark.unit
def test_master_orchestrator_get_router_wires_redis_client() -> None:
    """MasterOrchestratorAgent._get_router() must also pass redis_client through to
    the AgentRouterAgent singleton (SP-ADR023-002 Dag 2), mirroring the
    async_session_factory wiring from Dag 1 -- same first-creation-wins risk applies
    to the Redis cache tier."""
    import src.core.agents.agent_router_agent as ara_module
    from src.core.agents.master_orchestrator_agent import MasterOrchestratorAgent

    sentinel_redis = object()
    tenant_id = 88808
    original = ara_module._instances.pop(tenant_id, None)
    try:
        with patch.object(MasterOrchestratorAgent, "_register_agent_profile", return_value=None):
            orchestrator = MasterOrchestratorAgent(
                agent_id="test_orch_redis", tenant_id=tenant_id, redis_client=sentinel_redis
            )
        router = orchestrator._get_router()
        assert router._redis_cache_tier is not None
        assert router._redis_cache_tier._redis is sentinel_redis
    finally:
        ara_module._instances.pop(tenant_id, None)
        if original is not None:
            ara_module._instances[tenant_id] = original


@pytest.mark.unit
def test_master_orchestrator_without_redis_client_stays_none() -> None:
    """Without an injected redis_client, _redis_client stays None (fail-graceful)."""
    from unittest.mock import patch as _patch

    from src.core.agents.master_orchestrator_agent import MasterOrchestratorAgent

    with _patch.object(MasterOrchestratorAgent, "_register_agent_profile", return_value=None):
        orchestrator = MasterOrchestratorAgent(agent_id="test_orch_no_redis", tenant_id=1)
    assert orchestrator._redis_client is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dependencies_get_master_orchestrator_wires_async_session_factory() -> None:
    """orchestration/dependencies.get_master_orchestrator() must wire
    async_session_factory into the MasterOrchestratorAgent it constructs
    (FA-NEW-001 follow-up -- mirrors get_agent_router's wiring). Delegates to the
    master_orchestrator_agent singleton (consolidated, no local cache anymore)."""
    import src.core.agents.master_orchestrator_agent as moa_module
    import src.core.api.v1.orchestration.dependencies as dep_module
    from src.core.database.session import get_db_session

    tenant_id = 88805
    original = moa_module._instances.pop(tenant_id, None)
    try:
        with (
            patch.object(
                dep_module.MasterOrchestratorAgent, "_register_agent_profile", return_value=None
            ),
            patch(
                "src.core.database.redis.get_redis_client",
                new=AsyncMock(return_value=object()),
            ),
        ):
            orchestrator = await dep_module.get_master_orchestrator(tenant_id=tenant_id)
        assert orchestrator._async_session_factory is get_db_session
    finally:
        moa_module._instances.pop(tenant_id, None)
        if original is not None:
            moa_module._instances[tenant_id] = original
