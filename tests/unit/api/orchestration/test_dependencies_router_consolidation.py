"""Rode tests -- SP-ADR023-002 Dag 1 -- router-instantiatie consolidatie.

Voor de fix bestaan er TWEE gescheiden instantiatiepaden voor AgentRouterAgent:
de singleton in agent_router_agent.py en een eigen _router_cache in
orchestration/dependencies.py. Deze tests leggen de consolidatie naar 1 canoniek
pad vast als regressietest tegen die architecturale inconsistentie.

SP-ADR023-002 Dag 2: dependencies.get_agent_router() is nu `async def` (haalt
redis_client op) -- alle aanroepen hier moeten `await`-en, en `get_redis_client`
moet gemockt zijn om te voorkomen dat een unit-test een echte Redis-verbinding
probeert te maken.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dependencies_get_agent_router_delegates_to_singleton() -> None:
    """dependencies.get_agent_router() must return the SAME object as the
    agent_router_agent singleton factory for the same tenant."""
    import src.core.agents.agent_router_agent as ara_module
    from src.core.agents.agent_router_agent import get_agent_router as singleton_get_agent_router
    from src.core.api.v1.orchestration.dependencies import (
        get_agent_router as dep_get_agent_router,
    )

    tenant_id = 88801
    original = ara_module._instances.pop(tenant_id, None)
    try:
        with patch(
            "src.core.database.redis.get_redis_client", new=AsyncMock(return_value=object())
        ):
            router_from_dependencies = await dep_get_agent_router(tenant_id=tenant_id)
        router_from_singleton = singleton_get_agent_router(tenant_id=tenant_id)
        assert router_from_dependencies is router_from_singleton
    finally:
        ara_module._instances.pop(tenant_id, None)
        if original is not None:
            ara_module._instances[tenant_id] = original


@pytest.mark.unit
@pytest.mark.asyncio
async def test_dependencies_get_agent_router_wires_async_session_factory() -> None:
    """The router returned by dependencies.get_agent_router() must have a
    non-None _async_session_factory (agent-discovery wiring, ADR-023). Uses
    get_db_session (src.core.database.session) rather than db_manager directly
    -- orchestration/ may not import src.core.database.database (ADR-034)."""
    import src.core.agents.agent_router_agent as ara_module
    from src.core.api.v1.orchestration.dependencies import get_agent_router
    from src.core.database.session import get_db_session

    tenant_id = 88802
    original = ara_module._instances.pop(tenant_id, None)
    try:
        with patch(
            "src.core.database.redis.get_redis_client", new=AsyncMock(return_value=object())
        ):
            router = await get_agent_router(tenant_id=tenant_id)
        assert router._async_session_factory is get_db_session
    finally:
        ara_module._instances.pop(tenant_id, None)
        if original is not None:
            ara_module._instances[tenant_id] = original


@pytest.mark.unit
@pytest.mark.asyncio
async def test_clear_tenant_cache_evicts_singleton_router_instance() -> None:
    """clear_tenant_cache() must evict the consolidated singleton instance -- a
    subsequent get_agent_router() call for the same tenant returns a new object."""
    import src.core.agents.agent_router_agent as ara_module
    from src.core.api.v1.orchestration.dependencies import clear_tenant_cache, get_agent_router

    tenant_id = 88803
    original = ara_module._instances.pop(tenant_id, None)
    try:
        with patch(
            "src.core.database.redis.get_redis_client", new=AsyncMock(return_value=object())
        ):
            first = await get_agent_router(tenant_id=tenant_id)
            clear_tenant_cache(tenant_id)
            second = await get_agent_router(tenant_id=tenant_id)
        assert first is not second
    finally:
        ara_module._instances.pop(tenant_id, None)
        if original is not None:
            ara_module._instances[tenant_id] = original
