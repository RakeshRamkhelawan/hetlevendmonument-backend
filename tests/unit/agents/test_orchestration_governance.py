import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from src.core.agents.agent_router_agent import AgentRouterAgent
from src.core.agents.master_orchestrator_agent import MasterOrchestratorAgent
from src.core.shared.interfaces import TaskData
from src.core.governance.oversight_gate import OversightGate
from src.core.governance import governance_helper


@pytest.fixture(autouse=True)
def _clear_shadow_ceo_cache():
    """_shadow_ceo_instances is a module-level cache -- clear it around every
    test so accumulated threat_memory/veto_count from one test can never leak
    into another (real review_task() calls run unmocked in several tests)."""
    governance_helper._shadow_ceo_instances.clear()
    yield
    governance_helper._shadow_ceo_instances.clear()


@pytest.mark.asyncio
async def test_agent_router_agent_route_and_execute_enforces_governance():
    """
    Test 1: Check if AgentRouterAgent bypasses the base agent's governance
    when route_and_execute is called directly. It should enforce governance!
    """
    router = AgentRouterAgent(tenant_id=1)
    task = TaskData(id="task_1", title="test", description="test task")

    with patch(
        "src.core.governance.governance_helper.apply_governance_check", new_callable=AsyncMock
    ) as mock_gov:
        mock_gov.return_value = (False, "Blocked by test governance")

        # If it enforces governance, it should return failure
        result = await router.route_and_execute(task)

        # Expect governance to be called for the routing action itself!
        mock_gov.assert_called()
        assert result.success is False
        assert "Blocked by test governance" in str(result.result_data)


def test_oversight_gate_instantiation_not_toothless():
    """
    Test 2: Check that OversightGate instantiations are not toothless (empty).
    The websocket endpoints instantiate it. We verify they have policy_engine and audit_service.
    """
    # This test might fail if the implementation is currently using OversightGate()
    import inspect
    import ast

    def check_file_for_toothless_gate(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            tree = ast.parse(f.read())

        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "OversightGate":
                # An empty call OversightGate() has no args or kwargs
                assert len(node.args) > 0 or len(node.keywords) > 0, (
                    f"Toothless OversightGate found in {filepath}"
                )

    check_file_for_toothless_gate("src/core/api/swarm_websocket_endpoints.py")
    check_file_for_toothless_gate("src/core/api/v1/agentic/websocket.py")


@pytest.mark.asyncio
async def test_adr026_fallback_chain_called_on_llm_routes():
    """
    Test 3: de LLM-route van AgentRouterAgent gebruikt het model van de TENANT (`TenantTaalmodel`).

    Gewijzigd 2026-10-20 (ADR-041 B14): de route riep de platformketen `get_fallback_chain()` aan; die kent
    de keuze van de klant niet. Uitval binnen de keuze van de klant regelt `LLMService.for_tenant` zelf.
    """
    router = AgentRouterAgent(tenant_id=1)
    # Register an agent so it enters _llm_route and doesn't return early
    from src.core.agents.agent_router_agent import AgentManifest

    await router.register(
        AgentManifest(agent_id="test_agent", agent_type="test", capabilities=[], department="test")
    )

    task = TaskData(id="task_2", title="test", description="test task")

    router.llm_client = MagicMock()
    router.llm_client.tekst = AsyncMock(return_value='{"agent_id": "test_agent"}')
    router.llm_client.text_completion = AsyncMock()

    await router._llm_route(task)

    router.llm_client.tekst.assert_awaited_once()
    router.llm_client.text_completion.assert_not_called()


@pytest.mark.asyncio
async def test_shadow_ceo_reused_across_governance_checks_same_tenant():
    """ShadowCEO instance must be cached per tenant so threat_memory persists
    across governance checks -- a fresh instance per call means the Byzantine
    and threat-pattern checks can never fire (they read self.threat_memory)."""
    with patch("src.core.als.infrastructure.redis_pool.get_redis_pool") as mock_pool:
        mock_pool.return_value = MagicMock()

        first = governance_helper._get_shadow_ceo(tenant_id=1)
        second = governance_helper._get_shadow_ceo(tenant_id=1)

        assert first is second


@pytest.mark.asyncio
async def test_shadow_ceo_separate_instance_per_tenant():
    """Different tenants must never share a ShadowCEO instance (tenant isolation)."""
    with patch("src.core.als.infrastructure.redis_pool.get_redis_pool") as mock_pool:
        mock_pool.return_value = MagicMock()

        tenant_a = governance_helper._get_shadow_ceo(tenant_id=1)
        tenant_b = governance_helper._get_shadow_ceo(tenant_id=2)

        assert tenant_a is not tenant_b
        assert tenant_a.tenant_id == 1
        assert tenant_b.tenant_id == 2


@pytest.mark.asyncio
async def test_shadow_ceo_uses_real_signal_bus_backed_by_shared_redis_pool():
    """ShadowCEO must be wired with a real SignalBus (same shared Redis pool
    pattern as src/core/api/v1/als/shared.py::get_orchestrator()) instead of
    signal_bus=None -- otherwise vetoes are never broadcast to chief_orchestrator."""
    with patch("src.core.als.infrastructure.redis_pool.get_redis_pool") as mock_pool:
        mock_pool.return_value = MagicMock()

        shadow_ceo = governance_helper._get_shadow_ceo(tenant_id=3)

        assert shadow_ceo.signal_bus is not None
        assert shadow_ceo.signal_bus.pool is mock_pool.return_value


@pytest.mark.asyncio
async def test_shadow_ceo_falls_back_to_none_with_warning_when_redis_unavailable():
    """When the Redis pool cannot be obtained, ShadowCEO must still be
    constructed (signal_bus=None) without raising, and a warning must be
    logged so the gap is observable instead of silent."""
    with (
        patch("src.core.als.infrastructure.redis_pool.get_redis_pool") as mock_pool,
        patch.object(governance_helper.logger, "warning") as mock_warning,
    ):
        mock_pool.side_effect = RuntimeError("Redis pool not initialized")

        shadow_ceo = governance_helper._get_shadow_ceo(tenant_id=4)

        assert shadow_ceo.signal_bus is None
        mock_warning.assert_called_once()
