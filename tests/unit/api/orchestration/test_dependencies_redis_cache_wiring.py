"""Rode tests -- SP-ADR023-002 Dag 2 -- Redis-cache cross-worker wiring.

Voor de fix geven dependencies.get_agent_router() en get_master_orchestrator()
geen redis_client door aan hun singleton-factory, waardoor RedisRouteCacheTier
nooit actief wordt op het live pad (ADR-023 sectie 4).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dependencies_get_agent_router_wires_redis_client() -> None:
    """dependencies.get_agent_router() must fetch a Redis client and pass it to
    the singleton factory so RedisRouteCacheTier is active on the router that
    serves /orchestration/* requests."""
    import src.core.agents.agent_router_agent as ara_module
    from src.core.api.v1.orchestration.dependencies import get_agent_router

    sentinel_redis = object()
    tenant_id = 88901
    original = ara_module._instances.pop(tenant_id, None)
    try:
        with patch(
            "src.core.database.redis.get_redis_client",
            new=AsyncMock(return_value=sentinel_redis),
        ):
            router = await get_agent_router(tenant_id=tenant_id)
        assert router._redis_cache_tier is not None
        assert router._redis_cache_tier._redis is sentinel_redis
    finally:
        ara_module._instances.pop(tenant_id, None)
        if original is not None:
            ara_module._instances[tenant_id] = original


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dependencies_get_agent_router_keeps_async_session_factory() -> None:
    """Redis-wiring must not regress the Dag-1 async_session_factory wiring."""
    import src.core.agents.agent_router_agent as ara_module
    from src.core.api.v1.orchestration.dependencies import get_agent_router
    from src.core.database.session import get_db_session

    tenant_id = 88902
    original = ara_module._instances.pop(tenant_id, None)
    try:
        with patch(
            "src.core.database.redis.get_redis_client",
            new=AsyncMock(return_value=object()),
        ):
            router = await get_agent_router(tenant_id=tenant_id)
        assert router._async_session_factory is get_db_session
    finally:
        ara_module._instances.pop(tenant_id, None)
        if original is not None:
            ara_module._instances[tenant_id] = original


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dependencies_get_master_orchestrator_wires_redis_client() -> None:
    """dependencies.get_master_orchestrator() must fetch a Redis client and pass
    it through to the MasterOrchestratorAgent it constructs, so _get_router()
    can wire it into the AgentRouterAgent it delegates to."""
    import src.core.agents.master_orchestrator_agent as moa_module
    from src.core.api.v1.orchestration.dependencies import get_master_orchestrator

    sentinel_redis = object()
    tenant_id = 88903
    original = moa_module._instances.pop(tenant_id, None)
    try:
        with (
            patch.object(
                moa_module.MasterOrchestratorAgent, "_register_agent_profile", return_value=None
            ),
            patch(
                "src.core.database.redis.get_redis_client",
                new=AsyncMock(return_value=sentinel_redis),
            ),
        ):
            orchestrator = await get_master_orchestrator(tenant_id=tenant_id)
        assert orchestrator._redis_client is sentinel_redis
    finally:
        moa_module._instances.pop(tenant_id, None)
        if original is not None:
            moa_module._instances[tenant_id] = original
