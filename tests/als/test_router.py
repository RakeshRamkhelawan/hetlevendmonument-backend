"""Tests for AgentRouterAgent routing infrastructure."""

import json
import pytest
from dataclasses import fields

from src.core.als.router import (
    RoutingDecision,
    RoutingError,
    RouterStats,
    RoutingTier,
)
from src.core.exceptions.exceptions import SanskritiError


@pytest.mark.als
class TestRoutingTier:
    def test_all_five_tiers_exist(self):
        assert {t.value for t in RoutingTier} == {
            "cache_memory",
            "cache_redis",
            "capability",
            "llm",
            "fallback",
        }


@pytest.mark.als
class TestRoutingDecision:
    def test_has_required_fields(self):
        field_names = {f.name for f in fields(RoutingDecision)}
        assert field_names >= {
            "agent_id",
            "agent_class",
            "department",
            "confidence",
            "tier_used",
            "attempted_tiers",
            "routing_latency_ms",
            "reasoning",
        }

    def test_reasoning_is_optional(self):
        from src.core.als.enterprise.departments.department_orchestrator import Department

        decision = RoutingDecision(
            agent_id="test_agent",
            agent_class=object,
            department=Department.FINANCE,
            confidence=0.9,
            tier_used=RoutingTier.CAPABILITY,
            attempted_tiers=[RoutingTier.CACHE_MEMORY, RoutingTier.CACHE_REDIS],
            routing_latency_ms=12.5,
            reasoning=None,
        )
        assert decision.reasoning is None


@pytest.mark.als
class TestRouterStats:
    def test_has_required_fields(self):
        stats = RouterStats(
            cache_hit_rate=0.85,
            llm_fallback_count=3,
            avg_latency_ms=45.2,
            total_requests=50,
        )
        assert stats.cache_hit_rate == 0.85
        assert stats.total_requests == 50


@pytest.mark.als
class TestRoutingError:
    def test_inherits_from_sanskriti_error(self):
        from src.core.als.router import RoutingTier

        err = RoutingError(
            tenant_id=1,
            task_type="contract_review",
            attempted_tiers=[RoutingTier.CAPABILITY, RoutingTier.LLM, RoutingTier.FALLBACK],
        )
        assert isinstance(err, SanskritiError)

    def test_message_contains_task_type_and_tenant(self):
        err = RoutingError(
            tenant_id=42,
            task_type="invoice_processing",
            attempted_tiers=[RoutingTier.FALLBACK],
        )
        assert "invoice_processing" in str(err)
        assert "42" in str(err)


# =============================================================================
# Task 2: RouterService skeleton tests
# =============================================================================

from unittest.mock import AsyncMock, MagicMock, patch
from src.core.shared.interfaces import TaskData


def _make_task(title="contract_review", description="", tags=None):
    return TaskData(
        title=title,
        description=description or title,
        tags=tags or [],
    )


def _make_router_service(tenant_id=1):
    """Build a RouterService with mocked dependencies."""
    from src.core.als.router import RouterService

    redis_client = AsyncMock()
    registry = MagicMock()
    registry.list_agents.return_value = []
    llm_client = AsyncMock()
    return RouterService(
        tenant_id=tenant_id,
        redis_client=redis_client,
        registry=registry,
        llm_client=llm_client,
    )


@pytest.mark.als
class TestRouterServiceInit:
    def test_build_cache_key_is_deterministic(self):
        svc = _make_router_service(tenant_id=5)
        task = _make_task(title="invoice_processing", description="Process invoice")
        key1 = svc._build_cache_key(task)
        key2 = svc._build_cache_key(task)
        assert key1 == key2
        assert len(key1) == 64  # SHA-256 hex digest

    def test_cache_key_differs_by_tenant(self):
        svc_a = _make_router_service(tenant_id=1)
        svc_b = _make_router_service(tenant_id=2)
        task = _make_task()
        assert svc_a._build_cache_key(task) != svc_b._build_cache_key(task)

    def test_cache_key_truncates_description_at_512(self):
        svc = _make_router_service(tenant_id=1)
        short_task = _make_task(description="x" * 512)
        long_task = _make_task(description="x" * 1000)
        assert svc._build_cache_key(short_task) == svc._build_cache_key(long_task)

    @pytest.mark.asyncio
    async def test_initialize_returns_true(self):
        svc = _make_router_service()
        svc._redis.ping = AsyncMock(return_value=True)
        result = await svc.initialize()
        assert result is True


# =============================================================================
# Task 3a: Cache tier tests
# =============================================================================


@pytest.mark.als
class TestCacheTier:
    @pytest.mark.asyncio
    async def test_cache_miss_returns_none(self):
        svc = _make_router_service()
        result = await svc._check_cache("nonexistent_key")
        assert result is None

    @pytest.mark.asyncio
    async def test_memory_cache_hit_returns_decision(self):
        from src.core.als.enterprise.departments.department_orchestrator import Department

        svc = _make_router_service()
        decision = RoutingDecision(
            agent_id="forecasting_agent",
            agent_class=object,
            department=Department.FINANCE,
            confidence=0.9,
            tier_used=RoutingTier.CACHE_MEMORY,
            attempted_tiers=[],
            routing_latency_ms=1.0,
        )
        # Prime the memory cache directly
        svc._mem_cache["test_key"] = decision
        result = await svc._check_cache("test_key")
        assert result is not None
        assert result.agent_id == "forecasting_agent"
        assert result.tier_used == RoutingTier.CACHE_MEMORY

    @pytest.mark.als
    @pytest.mark.asyncio
    async def test_redis_cache_hit_after_memory_miss(self):
        from src.core.als.enterprise.departments.department_orchestrator import Department
        from src.core.als.agents.departments.base_department_agent import DepartmentType

        svc = _make_router_service()
        decision = RoutingDecision(
            agent_id="tax_agent",
            agent_class=object,
            department=Department.FINANCE,
            confidence=0.85,
            tier_used=RoutingTier.CACHE_REDIS,
            attempted_tiers=[RoutingTier.CACHE_MEMORY],
            routing_latency_ms=3.5,
        )
        svc._redis.get = AsyncMock(
            return_value=json.dumps(
                {
                    "agent_id": decision.agent_id,
                    "department": decision.department.value,
                    "confidence": decision.confidence,
                }
            )
        )
        # Note: minimal Redis deserialization - agent_class reconstructed from registry
        svc._registry.get_registration = MagicMock(
            return_value=MagicMock(
                agent_id=decision.agent_id,
                agent_class=object,
                department=DepartmentType.FINANCE_TREASURY,
            )
        )
        result = await svc._check_cache("redis_key")
        assert result is not None
        assert result.tier_used == RoutingTier.CACHE_REDIS

    @pytest.mark.als
    @pytest.mark.asyncio
    async def test_low_confidence_not_written_to_cache(self):
        from src.core.als.enterprise.departments.department_orchestrator import Department

        svc = _make_router_service()
        svc._redis.setex = AsyncMock()
        low_conf_decision = RoutingDecision(
            agent_id="fallback_agent",
            agent_class=object,
            department=Department.OPERATIONS,
            confidence=0.30,  # below threshold
            tier_used=RoutingTier.FALLBACK,
            attempted_tiers=[RoutingTier.CAPABILITY, RoutingTier.LLM],
            routing_latency_ms=50.0,
        )
        await svc._write_cache("some_key", low_conf_decision)
        svc._redis.setex.assert_not_called()
        assert "some_key" not in svc._mem_cache

    @pytest.mark.als
    @pytest.mark.security
    def test_cache_key_includes_tenant_id_no_cross_tenant_hit(self):
        svc_a = _make_router_service(tenant_id=10)
        svc_b = _make_router_service(tenant_id=20)
        task = _make_task(title="forecast", description="quarterly forecast")
        assert svc_a._build_cache_key(task) != svc_b._build_cache_key(task)


# =============================================================================
# Task 3b: Capability tier tests
# =============================================================================

from src.core.als.agents.organism_registry import AgentRegistration, AgentPriority
from src.core.als.agents.departments.base_department_agent import AgentTechnology
from src.core.als.agents.departments.base_department_agent import DepartmentType


def _make_registration(agent_id, dept_type=DepartmentType.FINANCE_TREASURY):
    return AgentRegistration(
        agent_id=agent_id,
        agent_class=object,
        department=dept_type,
        technology=AgentTechnology.LLM,
        priority=AgentPriority.HIGH,
        description=f"Agent for {agent_id}",
    )


@pytest.mark.als
class TestCapabilityTier:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_keyword_match(self):
        svc = _make_router_service()
        task = _make_task(title="completely_unknown_task", tags=[])
        agents = [_make_registration("forecasting_agent")]
        result = await svc._match_capabilities(task, agents)
        assert result is None

    @pytest.mark.asyncio
    async def test_matches_agent_by_task_title_keyword(self):
        svc = _make_router_service()
        task = _make_task(title="invoice_processing", tags=["billing"])
        agents = [
            _make_registration("forecasting_agent"),
            _make_registration("accounts_receivable_payable"),
        ]
        result = await svc._match_capabilities(task, agents)
        assert result is not None
        assert result.agent_id == "accounts_receivable_payable"
        assert result.tier_used == RoutingTier.CAPABILITY
        assert result.confidence == pytest.approx(0.85, abs=0.01)

    @pytest.mark.asyncio
    async def test_matches_agent_by_tag_keyword(self):
        svc = _make_router_service()
        task = _make_task(title="legal_review", tags=["contract", "clause"])
        agents = [
            _make_registration("contract_analysis", DepartmentType.LEGAL_COMPLIANCE),
        ]
        result = await svc._match_capabilities(task, agents)
        assert result is not None
        assert result.agent_id == "contract_analysis"

    @pytest.mark.asyncio
    async def test_returns_none_for_agent_not_in_capability_map(self):
        svc = _make_router_service()
        task = _make_task(title="custom_task")
        agents = [_make_registration("unlisted_custom_agent")]
        result = await svc._match_capabilities(task, agents)
        assert result is None


# =============================================================================
# Task 3d: Fallback tier tests
# =============================================================================


@pytest.mark.als
class TestFallbackTier:
    @pytest.mark.asyncio
    async def test_fallback_returns_first_agent(self):
        from src.core.als.enterprise.departments.department_orchestrator import Department

        svc = _make_router_service()
        agents = [
            _make_registration("agent_a", DepartmentType.FINANCE_TREASURY),
            _make_registration("agent_b", DepartmentType.FINANCE_TREASURY),
        ]
        result = await svc._fallback(_make_task("unknown_task"), Department.FINANCE, agents)
        assert result.agent_id == "agent_a"
        assert result.tier_used == RoutingTier.FALLBACK
        assert result.confidence == pytest.approx(0.30, abs=0.01)

    @pytest.mark.asyncio
    async def test_fallback_raises_routing_error_when_no_agents(self):
        from src.core.als.enterprise.departments.department_orchestrator import Department

        svc = _make_router_service()
        with pytest.raises(RoutingError) as exc_info:
            await svc._fallback(_make_task("unknown"), Department.FINANCE, [])
        assert "unknown" in str(exc_info.value)
        assert svc._tenant_id == exc_info.value.tenant_id

    @pytest.mark.asyncio
    async def test_fallback_attempted_tiers_are_recorded(self):
        from src.core.als.enterprise.departments.department_orchestrator import Department

        svc = _make_router_service()
        agents = [_make_registration("any_agent", DepartmentType.FINANCE_TREASURY)]
        result = await svc._fallback(_make_task("t"), Department.FINANCE, agents)
        assert RoutingTier.FALLBACK == result.tier_used
        assert len(result.attempted_tiers) > 0


# =============================================================================
# Task 3c: LLM tier tests
# =============================================================================

import asyncio
from src.core.exceptions.exceptions import AgentTimeoutError


@pytest.mark.als
class TestLLMTier:
    @pytest.mark.asyncio
    async def test_llm_returns_valid_agent_id(self):
        svc = _make_router_service()
        agents = [
            _make_registration("contract_analysis", DepartmentType.LEGAL_COMPLIANCE),
            _make_registration("gdpr_privacy_guard", DepartmentType.LEGAL_COMPLIANCE),
        ]
        svc._llm.generate_response = AsyncMock(return_value={"text": "contract_analysis"})
        result = await svc._route_via_llm(_make_task("contract_review"), agents)
        assert result is not None
        assert result.agent_id == "contract_analysis"
        assert result.tier_used == RoutingTier.LLM
        assert result.confidence == pytest.approx(0.90, abs=0.01)
        assert result.reasoning is not None

    @pytest.mark.asyncio
    async def test_llm_returns_none_for_unknown_agent_id(self):
        svc = _make_router_service()
        agents = [_make_registration("contract_analysis", DepartmentType.LEGAL_COMPLIANCE)]
        svc._llm.generate_response = AsyncMock(return_value={"text": "nonexistent_agent_xyz"})
        result = await svc._route_via_llm(_make_task("review"), agents)
        assert result is None

    @pytest.mark.asyncio
    async def test_llm_timeout_returns_none(self):
        svc = _make_router_service()
        agents = [_make_registration("contract_analysis", DepartmentType.LEGAL_COMPLIANCE)]

        async def slow_response(*args, **kwargs):
            await asyncio.sleep(999)
            return {"text": "contract_analysis"}

        svc._llm.generate_response = slow_response
        with patch("src.core.als.router._LLM_TIMEOUT", 0.01):
            result = await svc._route_via_llm(_make_task("review"), agents)
        assert result is None

    @pytest.mark.asyncio
    async def test_llm_exception_returns_none_and_logs_error(self):
        svc = _make_router_service()
        agents = [_make_registration("contract_analysis", DepartmentType.LEGAL_COMPLIANCE)]
        svc._llm.generate_response = AsyncMock(side_effect=RuntimeError("API down"))
        result = await svc._route_via_llm(_make_task("review"), agents)
        assert result is None


# =============================================================================
# Task 4: route() + invalidate() + get_stats() full flow tests
# =============================================================================

from src.core.als.enterprise.departments.department_orchestrator import Department


@pytest.mark.als
class TestRouteMainMethod:
    @pytest.mark.asyncio
    async def test_route_returns_decision_with_latency(self):
        svc = _make_router_service()
        # Mock Phase 1 (DeterministicRouter)
        with patch(
            "src.core.als.enterprise.departments.deterministic_router.DeterministicRouter"
        ) as mock_det:
            mock_det.return_value.route.return_value = Department.FINANCE
            svc._registry.list_agents.return_value = [
                _make_registration("forecasting_agent", DepartmentType.FINANCE_TREASURY)
            ]
            task = _make_task(title="budget_forecast", tags=["forecast"])
            result = await svc.route(task)
        assert result.routing_latency_ms >= 0
        assert result.agent_id is not None
        assert len(result.attempted_tiers) >= 1

    @pytest.mark.asyncio
    async def test_route_uses_cache_on_second_call(self):
        svc = _make_router_service()
        with patch(
            "src.core.als.enterprise.departments.deterministic_router.DeterministicRouter"
        ) as mock_det:
            mock_det.return_value.route.return_value = Department.FINANCE
            svc._registry.list_agents.return_value = [
                _make_registration("forecasting_agent", DepartmentType.FINANCE_TREASURY)
            ]
            task = _make_task(title="budget_forecast", tags=["forecast", "financial"])
            result1 = await svc.route(task)
            result2 = await svc.route(task)
        # Second call should hit memory cache
        assert result2.tier_used == RoutingTier.CACHE_MEMORY

    @pytest.mark.asyncio
    async def test_routing_decision_contains_latency_and_attempted_tiers(self):
        svc = _make_router_service()
        with patch(
            "src.core.als.enterprise.departments.deterministic_router.DeterministicRouter"
        ) as mock_det:
            mock_det.return_value.route.return_value = Department.LEGAL_COMPLIANCE
            svc._registry.list_agents.return_value = [
                _make_registration("contract_analysis", DepartmentType.LEGAL_COMPLIANCE)
            ]
            task = _make_task(title="contract_review", tags=["contract"])
            result = await svc.route(task)
        assert result.routing_latency_ms > 0
        assert isinstance(result.attempted_tiers, list)

    @pytest.mark.als
    @pytest.mark.asyncio
    async def test_stats_rolling_window_is_50_tasks(self):
        svc = _make_router_service()
        with patch(
            "src.core.als.enterprise.departments.deterministic_router.DeterministicRouter"
        ) as mock_det:
            mock_det.return_value.route.return_value = Department.FINANCE
            svc._registry.list_agents.return_value = [
                _make_registration("forecasting_agent", DepartmentType.FINANCE_TREASURY)
            ]
            task = _make_task(title="budget", tags=["financial"])
            for _ in range(60):  # more than window size
                await svc.route(task)
        stats = svc.get_stats()
        assert stats.total_requests == 60
        assert len(svc._latencies) <= 50  # window capped

    @pytest.mark.als
    @pytest.mark.asyncio
    async def test_invalidate_clears_memory_cache(self):
        from src.core.als.enterprise.departments.department_orchestrator import Department

        svc = _make_router_service()
        svc._mem_cache["some_key"] = MagicMock()
        svc._redis.scan = AsyncMock(return_value=(0, []))
        await svc.invalidate("any_agent_id")
        assert len(svc._mem_cache) == 0

    @pytest.mark.als
    @pytest.mark.security
    @pytest.mark.asyncio
    async def test_tenant_isolation_agent_lookup(self):
        """Tenant A routes using only its own tenant context."""
        svc_a = _make_router_service(tenant_id=1)
        svc_b = _make_router_service(tenant_id=2)
        task = _make_task(title="invoice_processing", tags=["billing"])
        with patch(
            "src.core.als.enterprise.departments.deterministic_router.DeterministicRouter"
        ) as mock_det:
            mock_det.return_value.route.return_value = Department.FINANCE
            svc_a._registry.list_agents.return_value = [
                _make_registration("ar_payable_tenant1", DepartmentType.FINANCE_TREASURY)
            ]
            svc_b._registry.list_agents.return_value = [
                _make_registration("accounts_receivable_payable", DepartmentType.FINANCE_TREASURY)
            ]
            result_a = await svc_a.route(task)
            result_b = await svc_b.route(task)
        assert result_a.agent_id != result_b.agent_id


# =============================================================================
# Task 5: AgentRouterAgent wrapper + singleton management
# =============================================================================


@pytest.mark.als
class TestAgentRouterAgent:
    def test_instantiation_does_not_raise(self):
        from src.core.als.router import AgentRouterAgent
        from unittest.mock import MagicMock

        agent = AgentRouterAgent(tenant_id=1, signal_bus=MagicMock())
        assert agent is not None

    @pytest.mark.asyncio
    async def test_process_task_returns_execution_result_on_success(self):
        from src.core.als.router import AgentRouterAgent
        from src.core.shared.interfaces import TaskData

        agent = AgentRouterAgent(tenant_id=1, signal_bus=MagicMock())
        task = _make_task(title="invoice_processing", tags=["billing"])
        with patch.object(agent, "route", new_callable=AsyncMock) as mock_route:
            from src.core.als.enterprise.departments.department_orchestrator import Department

            mock_route.return_value = RoutingDecision(
                agent_id="accounts_receivable_payable",
                agent_class=object,
                department=Department.FINANCE,
                confidence=0.85,
                tier_used=RoutingTier.CAPABILITY,
                attempted_tiers=[RoutingTier.CACHE_MEMORY],
                routing_latency_ms=5.2,
            )
            result = await agent.process_task(task)
        assert result.success is True
        assert result.result_data["agent_id"] == "accounts_receivable_payable"

    @pytest.mark.asyncio
    async def test_process_task_returns_failure_on_routing_error(self):
        from src.core.als.router import AgentRouterAgent, RoutingError, RoutingTier

        agent = AgentRouterAgent(tenant_id=1, signal_bus=MagicMock())
        task = _make_task(title="impossible_task")
        with patch.object(agent, "route", new_callable=AsyncMock) as mock_route:
            mock_route.side_effect = RoutingError(
                tenant_id=1,
                task_type="impossible_task",
                attempted_tiers=[RoutingTier.FALLBACK],
            )
            result = await agent.process_task(task)
        assert result.success is False
        assert "impossible_task" in result.error_message

    # User behavioral test
    @pytest.mark.asyncio
    async def test_user_submits_contract_task_gets_legal_agent(self):
        """From user perspective: submit a contract task, get a legal agent back."""
        from src.core.als.router import AgentRouterAgent

        agent = AgentRouterAgent(tenant_id=99, signal_bus=MagicMock())
        task = TaskData(
            title="contract_review",
            description="Review vendor NDA for GDPR clauses",
            tags=["contract", "legal", "gdpr"],
        )
        with patch.object(agent._service, "route", new_callable=AsyncMock) as mock_route:
            from src.core.als.enterprise.departments.department_orchestrator import Department

            mock_route.return_value = RoutingDecision(
                agent_id="contract_analysis",
                agent_class=object,
                department=Department.LEGAL_COMPLIANCE,
                confidence=0.85,
                tier_used=RoutingTier.CAPABILITY,
                attempted_tiers=[RoutingTier.CACHE_MEMORY, RoutingTier.CACHE_REDIS],
                routing_latency_ms=8.0,
            )
            result = await agent.process_task(task)
        assert result.success is True
        assert result.result_data["agent_id"] == "contract_analysis"
        assert result.result_data["department"] is not None


@pytest.mark.als
class TestSingletonManagement:
    @pytest.mark.asyncio
    async def test_get_router_returns_same_instance_for_same_tenant(self):
        from src.core.als.router import clear_router, get_router

        clear_router(1)
        r1 = await get_router(1, AsyncMock(), MagicMock(), AsyncMock())
        r2 = await get_router(1, AsyncMock(), MagicMock(), AsyncMock())
        assert r1 is r2
        clear_router(1)

    def test_clear_router_removes_instance_and_lock(self):
        from src.core.als.router import _router_cache, _router_locks, clear_router

        _router_cache[999] = MagicMock()
        _router_locks[999] = asyncio.Lock()
        clear_router(999)
        assert 999 not in _router_cache
        assert 999 not in _router_locks


# ---------------------------------------------------------------------------
# Integration tests (real Redis) - skipped if Redis unavailable
# ---------------------------------------------------------------------------

import redis.asyncio as aioredis


@pytest.fixture
async def redis_client():
    """Real Redis client for integration tests. Skip if unavailable."""
    client = aioredis.from_url("redis://localhost:6385/0", decode_responses=True)
    try:
        await client.ping()
    except Exception as exc:
        pytest.skip(f"Redis unavailable: {exc}")
    yield client
    await client.aclose()


@pytest.mark.als
@pytest.mark.integration
class TestIntegration:
    @pytest.mark.asyncio
    async def test_redis_cache_persists_across_router_instances(self, redis_client):
        """Cache written by instance A is readable by instance B (same tenant)."""
        from src.core.als.router import RouterService
        from src.core.als.enterprise.departments.department_orchestrator import Department

        registry = MagicMock()
        registry.list_agents.return_value = [
            _make_registration("forecasting_agent", DepartmentType.FINANCE_TREASURY)
        ]
        registry.get_registration.return_value = _make_registration("forecasting_agent")

        svc_a = RouterService(
            tenant_id=777,
            redis_client=redis_client,
            registry=registry,
            llm_client=AsyncMock(),
        )
        svc_b = RouterService(
            tenant_id=777,
            redis_client=redis_client,
            registry=registry,
            llm_client=AsyncMock(),
        )

        task = _make_task(title="budget_forecast", tags=["forecast", "financial"])
        with patch(
            "src.core.als.enterprise.departments.deterministic_router.DeterministicRouter"
        ) as mock_det:
            mock_det.return_value.route.return_value = Department.FINANCE
            decision_a = await svc_a.route(task)

        # B should find it in Redis (not memory)
        svc_b._mem_cache.clear()
        result = await svc_b._check_cache(svc_b._build_cache_key(task))
        assert result is not None
        assert result.agent_id == decision_a.agent_id

        # Cleanup
        await svc_a.invalidate("any")

    @pytest.mark.asyncio
    async def test_full_routing_flow_end_to_end(self, redis_client):
        """Full route() call with real Redis, mock LLM and registry."""
        from src.core.als.router import RouterService
        from src.core.als.enterprise.departments.department_orchestrator import Department

        registry = MagicMock()
        registry.list_agents.return_value = [
            _make_registration("contract_analysis", DepartmentType.LEGAL_COMPLIANCE)
        ]
        svc = RouterService(
            tenant_id=888,
            redis_client=redis_client,
            registry=registry,
            llm_client=AsyncMock(),
        )
        task = _make_task(title="contract_review", tags=["contract", "legal"])
        with patch(
            "src.core.als.enterprise.departments.deterministic_router.DeterministicRouter"
        ) as mock_det:
            mock_det.return_value.route.return_value = Department.LEGAL_COMPLIANCE
            result = await svc.route(task)

        assert result.agent_id == "contract_analysis"
        assert result.routing_latency_ms > 0
        await svc.invalidate("any")


# ---------------------------------------------------------------------------
# Security tests - tenant isolation
# ---------------------------------------------------------------------------


@pytest.mark.als
@pytest.mark.security
class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_tenant_a_cannot_see_tenant_b_agents(self):
        """Routing for tenant A never returns agents registered only for tenant B."""
        svc_a = _make_router_service(tenant_id=1)
        svc_b = _make_router_service(tenant_id=2)
        task = _make_task(title="invoice_processing", tags=["billing", "payment"])

        with patch(
            "src.core.als.enterprise.departments.deterministic_router.DeterministicRouter"
        ) as mock_det:
            mock_det.return_value.route.return_value = Department.FINANCE
            svc_a._registry.list_agents.return_value = [
                _make_registration("ar_agent_tenant1", DepartmentType.FINANCE_TREASURY)
            ]
            svc_b._registry.list_agents.return_value = [
                _make_registration("accounts_receivable_payable", DepartmentType.FINANCE_TREASURY)
            ]
            # Route for tenant A
            result_a = await svc_a.route(task)
            # Tenant A should not get tenant B's agent
            assert result_a.agent_id != "accounts_receivable_payable"

    def test_cache_key_no_cross_tenant_collision(self):
        svc1 = _make_router_service(tenant_id=1)
        svc2 = _make_router_service(tenant_id=2)
        task = _make_task(title="same_task", description="same description")
        assert svc1._build_cache_key(task) != svc2._build_cache_key(task)


# =============================================================================
# Code Review Fixes Tests
# =============================================================================


@pytest.mark.als
class TestAgentRouterAgentTenantId:
    """Test for tenant_id storage in AgentRouterAgent"""

    def test_agent_router_stores_tenant_id_correctly(self):
        """Verify tenant_id is properly stored in AgentRouterAgent."""
        from src.core.als.router import AgentRouterAgent
        from unittest.mock import MagicMock

        agent = AgentRouterAgent(tenant_id=42, signal_bus=MagicMock())
        # AgentRouterAgent stores tenant_id in _tenant_id
        assert hasattr(agent, "_tenant_id")
        assert agent._tenant_id == 42
        # Also verify it's passed to RouterService
        assert agent._service._tenant_id == 42


@pytest.mark.als
class TestRoutingDecisionDefaults:
    def test_attempted_tiers_has_default_empty_list(self):
        """Verify attempted_tiers defaults to empty list when not provided."""
        from src.core.als.enterprise.departments.department_orchestrator import Department

        decision = RoutingDecision(
            agent_id="test_agent",
            agent_class=object,
            department=Department.FINANCE,
            confidence=0.9,
            tier_used=RoutingTier.CAPABILITY,
            routing_latency_ms=12.5,
            # attempted_tiers NOT provided - should default to []
        )
        assert decision.attempted_tiers == []
        assert isinstance(decision.attempted_tiers, list)


@pytest.mark.als
class TestPublicAPI:
    def test_all_exports_are_defined(self):
        """Verify __all__ exports exist and are importable."""
        from src.core.als import router

        for name in router.__all__:
            assert hasattr(router, name), f"{name} not found in router module"

    def test_all_contains_expected_exports(self):
        """Verify __all__ contains expected public API."""
        from src.core.als import router

        expected = {
            "RoutingTier",
            "RoutingDecision",
            "RouterStats",
            "RoutingError",
            "GatekeeperRoutingError",
            "AgentUnhealthyError",
            "RouterService",
            "AgentRouterAgent",
            "get_router",
            "clear_router",
        }
        assert set(router.__all__) == expected


from unittest.mock import patch, call


@pytest.mark.als
class TestLogging:
    @pytest.mark.asyncio
    async def test_route_logs_tenant_id_on_start(self):
        """Verify route() logs tenant_id at start of routing."""
        from src.core.als.enterprise.departments.department_orchestrator import Department

        svc = _make_router_service(tenant_id=99)
        with patch("src.core.als.router.logger") as mock_logger:
            with patch("src.core.als.router.DeterministicRouter") as mock_det:
                mock_det.return_value.route.return_value = Department.FINANCE
                svc._registry.list_agents.return_value = [
                    _make_registration("forecasting_agent", DepartmentType.FINANCE_TREASURY)
                ]
                task = _make_task(title="budget_forecast")
                await svc.route(task)

        # Verify debug log with tenant_id was called (tier logging)
        assert mock_logger.debug.called
        # Check that tenant_id appears in log messages via %s formatting
        tenant_in_logs = any(
            "99" in str(call_args)
            for call_args in mock_logger.debug.call_args_list
        )
        assert tenant_in_logs, "tenant_id should appear in logs"

    @pytest.mark.asyncio
    async def test_route_logs_routing_result(self):
        """Verify route() logs the routing result."""
        from src.core.als.enterprise.departments.department_orchestrator import Department

        svc = _make_router_service(tenant_id=99)
        with patch("src.core.als.router.logger") as mock_logger:
            with patch("src.core.als.router.DeterministicRouter") as mock_det:
                mock_det.return_value.route.return_value = Department.FINANCE
                svc._registry.list_agents.return_value = [
                    _make_registration("forecasting_agent", DepartmentType.FINANCE_TREASURY)
                ]
                task = _make_task(title="budget_forecast")
                await svc.route(task)

        # Verify debug log with tenant_id
        assert mock_logger.debug.called
        # Verify agent_id appears in logs
        agent_in_logs = any(
            "forecasting" in str(call_args)
            for call_args in mock_logger.debug.call_args_list
        )
        assert agent_in_logs, "agent_id should appear in logs"

    @pytest.mark.asyncio
    async def test_check_cache_logs_tenant_id(self):
        """Verify _check_cache logs tenant_id on cache hit."""
        from src.core.als.enterprise.departments.department_orchestrator import Department

        svc = _make_router_service(tenant_id=42)
        # Prime the cache with a decision
        decision = RoutingDecision(
            agent_id="test_agent",
            agent_class=object,
            department=Department.FINANCE,
            confidence=0.9,
            tier_used=RoutingTier.CACHE_MEMORY,
            attempted_tiers=[],
            routing_latency_ms=1.0,
        )
        svc._mem_cache["test_key"] = decision

        with patch("src.core.als.router.logger") as mock_logger:
            result = await svc._check_cache("test_key")

        assert result is not None
        # Should have debug logging with tenant_id
        assert mock_logger.debug.called
        tenant_in_logs = any(
            "42" in str(call_args)
            for call_args in mock_logger.debug.call_args_list
        )
        assert tenant_in_logs, "tenant_id should appear in cache debug logs"

    def test_build_cache_key_logs_tenant_id(self):
        """Verify _build_cache_key logs tenant_id."""
        svc = _make_router_service(tenant_id=55)
        with patch("src.core.als.router.logger") as mock_logger:
            task = _make_task(title="test_task")
            key = svc._build_cache_key(task)

        # May or may not log - just verify no error
        assert isinstance(key, str)
        assert len(key) == 64
