"""Unit tests for orchestration/dependencies.py DI factories (SP-AGT-002 Dag 1+2)."""

import pytest
from fastapi import HTTPException
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.unit
def test_safe_get_tenant_id_none_raises_401() -> None:
    """safe_get_tenant_id must raise HTTP 401 when tenant_id is None (FA-002 unhappy path)."""
    from src.core.middleware.tenant_context import safe_get_tenant_id

    with pytest.raises(HTTPException) as exc_info:
        safe_get_tenant_id(tenant_id=None)
    assert exc_info.value.status_code == 401
    assert "Tenant context required" in exc_info.value.detail


@pytest.mark.unit
def test_get_master_orchestrator_importable() -> None:
    from src.core.api.v1.orchestration.dependencies import get_master_orchestrator

    assert callable(get_master_orchestrator)


@pytest.mark.unit
def test_get_agent_router_importable() -> None:
    from src.core.api.v1.orchestration.dependencies import get_agent_router

    assert callable(get_agent_router)


@pytest.mark.unit
def test_get_critic_agent_importable() -> None:
    from src.core.api.v1.orchestration.dependencies import get_critic_agent

    assert callable(get_critic_agent)


@pytest.mark.unit
def test_get_health_monitor_importable() -> None:
    from src.core.api.v1.orchestration.dependencies import get_health_monitor

    assert callable(get_health_monitor)


@pytest.mark.unit
def test_get_critic_agent_same_tenant_returns_cached_instance() -> None:
    """Same tenant_id must return the same CriticAgent instance (module-level cache)."""
    import src.core.api.v1.orchestration.dependencies as dep_module
    from src.core.api.v1.orchestration.dependencies import get_critic_agent

    tenant_id = 99901
    original = dep_module._critic_cache.pop(tenant_id, None)
    try:
        with patch(
            "src.core.api.v1.orchestration.dependencies.CriticAgent",
            return_value=MagicMock(),
        ):
            result1 = get_critic_agent(tenant_id=tenant_id)
            result2 = get_critic_agent(tenant_id=tenant_id)
        assert result1 is result2
    finally:
        dep_module._critic_cache.pop(tenant_id, None)
        if original is not None:
            dep_module._critic_cache[tenant_id] = original


def _patched_orchestrator_init(
    self: object, agent_id: str, tenant_id: int, async_session_factory: object = None
) -> None:
    """Minimal MasterOrchestratorAgent.__init__ replacement for consolidation tests.

    dependencies.get_master_orchestrator() no longer constructs MasterOrchestratorAgent
    itself (SP-ADR023-002 Dag 1 -- FA-NEW-001 follow-up) -- it delegates to the
    master_orchestrator_agent singleton, so this test patches
    MasterOrchestratorAgent.__init__ directly (same pattern as
    tests/unit/test_agent_router_agent.py) instead of the (now removed)
    dependencies._orchestrator_cache / dependencies.MasterOrchestratorAgent.
    """
    self._agent_id = agent_id  # type: ignore[attr-defined]
    self.tenant_id = tenant_id  # type: ignore[attr-defined]
    self._async_session_factory = async_session_factory  # type: ignore[attr-defined]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_master_orchestrator_different_tenants_return_different_instances() -> None:
    """Different tenant_ids must be keyed separately in the singleton _instances cache."""
    import src.core.agents.master_orchestrator_agent as moa_module
    from src.core.agents.master_orchestrator_agent import MasterOrchestratorAgent
    from src.core.api.v1.orchestration.dependencies import get_master_orchestrator

    t1, t2 = 99902, 99903
    for t in (t1, t2):
        moa_module._instances.pop(t, None)
    try:
        with (
            patch.object(
                MasterOrchestratorAgent,
                "__init__",
                lambda self, agent_id="", tenant_id=1, async_session_factory=None, redis_client=None: (
                    _patched_orchestrator_init(self, agent_id, tenant_id, async_session_factory)
                ),
            ),
            patch("src.core.database.redis.get_redis_client", new=AsyncMock(return_value=object())),
        ):
            r1 = await get_master_orchestrator(tenant_id=t1)
            r2 = await get_master_orchestrator(tenant_id=t2)
        assert r1 is not r2
        assert r1.tenant_id == t1
        assert r2.tenant_id == t2
    finally:
        for t in (t1, t2):
            moa_module._instances.pop(t, None)


def _patched_router_init(self: object, agent_id: str, tenant_id: int) -> None:
    """Minimal AgentRouterAgent.__init__ replacement for consolidation tests.

    dependencies.get_agent_router() no longer constructs AgentRouterAgent
    itself (SP-ADR023-002 Dag 1) -- it delegates to the agent_router_agent
    singleton, so this test patches AgentRouterAgent.__init__ directly
    (same pattern as tests/unit/test_agent_router_agent.py) instead of the
    (now removed) dependencies._router_cache / dependencies.AgentRouterAgent.
    """
    self._agent_id = agent_id  # type: ignore[attr-defined]
    self.tenant_id = tenant_id  # type: ignore[attr-defined]
    self._async_session_factory = None  # type: ignore[attr-defined]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_agent_router_different_tenants_return_different_instances() -> None:
    """Different tenant_ids must be keyed separately in the singleton _instances cache."""
    import src.core.agents.agent_router_agent as ara_module
    from src.core.agents.agent_router_agent import AgentRouterAgent
    from src.core.api.v1.orchestration.dependencies import get_agent_router

    t1, t2 = 99904, 99905
    for t in (t1, t2):
        ara_module._instances.pop(t, None)
    try:
        with (
            patch.object(
                AgentRouterAgent,
                "__init__",
                lambda self, agent_id="", tenant_id=1, async_session_factory=None: (
                    _patched_router_init(self, agent_id, tenant_id)
                ),
            ),
            patch("src.core.database.redis.get_redis_client", new=AsyncMock(return_value=object())),
        ):
            r1 = await get_agent_router(tenant_id=t1)
            r2 = await get_agent_router(tenant_id=t2)
        assert r1 is not r2
        assert r1.tenant_id == t1
        assert r2.tenant_id == t2
    finally:
        for t in (t1, t2):
            ara_module._instances.pop(t, None)


@pytest.mark.unit
def test_get_health_monitor_different_tenants_return_different_instances() -> None:
    """Different tenant_ids must be keyed separately in _health_monitor_cache."""
    import src.core.api.v1.orchestration.dependencies as dep_module
    from src.core.api.v1.orchestration.dependencies import get_health_monitor

    t1, t2 = 99906, 99907
    for t in (t1, t2):
        dep_module._health_monitor_cache.pop(t, None)
    mock_t1, mock_t2 = MagicMock(), MagicMock()
    keyed: dict[int, MagicMock] = {t1: mock_t1, t2: mock_t2}
    try:
        with patch(
            "src.core.api.v1.orchestration.dependencies.AgentHealthMonitorAgent",
            side_effect=lambda **kw: keyed[kw["tenant_id"]],
        ):
            r1 = get_health_monitor(tenant_id=t1)
            r2 = get_health_monitor(tenant_id=t2)
        assert r1 is not r2
        assert r1 is mock_t1
        assert r2 is mock_t2
    finally:
        for t in (t1, t2):
            dep_module._health_monitor_cache.pop(t, None)
