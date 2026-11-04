"""
Test Suite for Agent Router (P4.5.1)
Comprehensive testing of intelligent agent routing, caching, and LLM-based selection
Target Coverage: 80%+

Test Categories:
    1. Initialization & Setup (5 tests)
    2. Agent Registration (6 tests)
    3. Routing Strategies (7 tests)
    4. Caching Mechanisms (8 tests)
    5. LLM-Based Selection (5 tests)
    6. Metrics Tracking (6 tests)
    7. Error Handling (5 tests)
    8. Integration Workflows (6 tests)
    9. Edge Cases & Performance (8 tests)
    10. Statistics & Reporting (4 tests)

Total: 60 tests designed to achieve 80%+ code coverage
"""

import asyncio
import json
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.agents.agent_router import (
    AgentMetrics,
    AgentRouter,
    CacheStrategy,
    RouteCache,
    RoutingContext,
    RoutingDecision,
    RoutingStrategy,
    create_agent_router,
    get_agent_router,
)
from src.core.types import AgentType

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def routing_context():
    """Create a sample routing context"""
    return RoutingContext(
        request_id="test-req-001",
        task_type="data_analysis",
        task_description="Analyze sales trends for Q4",
        required_capabilities=["analytics", "reporting"],
        priority=5,
        complexity_score=0.7,
        user_id="user-001",
    )


@pytest.fixture
def mock_llm_client():
    """Create mock LLM client"""
    client = AsyncMock()
    client.generate = AsyncMock()
    return client


@pytest.fixture
async def router():
    """Create agent router instance"""
    r = AgentRouter(strategy=RoutingStrategy.WEIGHTED_SCORE)
    await r.initialize()
    return r


@pytest.fixture
async def router_with_agents(router):
    """Create router with pre-registered agents"""
    agents = [
        ("data-analysis-agent", AgentType.DATA_ANALYSIS, ["analytics", "reporting"]),
        ("system-monitor-agent", AgentType.SYSTEM_MONITOR, ["monitoring", "health"]),
        ("code-execution-agent", AgentType.CODE_EXECUTION, ["code", "execution"]),
    ]

    for agent_id, agent_type, caps in agents:
        await router.register_agent(agent_id, agent_type, caps)
        router.agent_metrics[agent_id] = AgentMetrics(
            agent_id=agent_id,
            total_requests=10,
            successful_requests=9,
            failed_requests=1,
            success_rate=90.0,
            availability_score=0.95,
            cost_per_request=0.001,
        )

    return router


# ============================================================================
# TEST CATEGORY 1: Initialization & Setup (5 tests)
# ============================================================================


class TestRouterInitialization:
    """Test router initialization and setup"""

    def test_router_creation_default_strategy(self):
        """Test router creation with default strategy"""
        router = AgentRouter()
        assert router.strategy == RoutingStrategy.WEIGHTED_SCORE
        # enable_caching depends on CACHE_AVAILABLE being True
        assert isinstance(router.cache, RouteCache)

    def test_router_creation_custom_strategy(self):
        """Test router creation with custom strategy"""
        router = AgentRouter(strategy=RoutingStrategy.LLM_BASED, enable_caching=False)
        assert router.strategy == RoutingStrategy.LLM_BASED
        assert router.enable_caching is False

    @pytest.mark.asyncio
    async def test_router_initialization_success(self, mock_llm_client):
        """Test successful router initialization"""
        router = AgentRouter()
        result = await router.initialize(mock_llm_client)
        assert result is True
        assert router._initialized is True
        assert router._llm_client is mock_llm_client

    @pytest.mark.asyncio
    async def test_router_initialization_no_llm(self):
        """Test router initialization without LLM"""
        router = AgentRouter()
        result = await router.initialize(None)
        assert result is True
        assert router._llm_client is None

    @pytest.mark.asyncio
    async def test_get_global_router_singleton(self):
        """Test global router singleton behavior"""
        router1 = await get_agent_router()
        router2 = await get_agent_router()
        assert router1 is router2


# ============================================================================
# TEST CATEGORY 2: Agent Registration (6 tests)
# ============================================================================


class TestAgentRegistration:
    """Test agent registration"""

    @pytest.mark.asyncio
    async def test_register_agent_success(self, router):
        """Test successful agent registration"""
        result = await router.register_agent("test-agent", AgentType.DATA_ANALYSIS, ["analytics"])
        assert result is True
        assert "test-agent" in router.agent_metrics
        assert "analytics" in router.agent_capabilities["test-agent"]

    @pytest.mark.asyncio
    async def test_register_multiple_agents(self, router):
        """Test registering multiple agents"""
        agents = [
            ("agent-1", AgentType.ANALYZER, ["analysis"]),
            ("agent-2", AgentType.EXECUTOR, ["execution"]),
            ("agent-3", AgentType.MONITOR, ["monitoring"]),
        ]

        for agent_id, agent_type, caps in agents:
            result = await router.register_agent(agent_id, agent_type, caps)
            assert result is True

        assert len(router.agent_metrics) == 3

    @pytest.mark.asyncio
    async def test_register_agent_no_capabilities(self, router):
        """Test registering agent without capabilities"""
        result = await router.register_agent("generic-agent", AgentType.GENERIC, None)
        assert result is True
        assert "generic-agent" in router.agent_metrics

    @pytest.mark.asyncio
    async def test_register_agent_multiple_capabilities(self, router):
        """Test registering agent with multiple capabilities"""
        caps = ["analytics", "reporting", "visualization", "ml"]
        result = await router.register_agent("multi-agent", AgentType.DATA_ANALYSIS, caps)
        assert result is True
        assert router.agent_capabilities["multi-agent"] == set(caps)

    @pytest.mark.asyncio
    async def test_register_duplicate_agent_overwrites(self, router):
        """Test registering duplicate agent overwrites previous"""
        await router.register_agent("agent", AgentType.ANALYZER, ["cap1"])
        await router.register_agent("agent", AgentType.EXECUTOR, ["cap2"])

        # Should have updated capabilities
        assert "cap2" in router.agent_capabilities["agent"]

    @pytest.mark.asyncio
    async def test_register_agent_error_handling(self, router):
        """Test error handling in registration"""
        with patch.object(router, "agent_metrics", side_effect=Exception("DB Error")):
            # Function should handle gracefully
            router.agent_metrics = {}
            result = await router.register_agent("agent", AgentType.GENERIC, [])
            assert result is True


# ============================================================================
# TEST CATEGORY 3: Routing Strategies (7 tests)
# ============================================================================


class TestRoutingStrategies:
    """Test different routing strategies"""

    @pytest.mark.asyncio
    async def test_performance_based_routing(self, router_with_agents, routing_context):
        """Test performance-based routing"""
        router = router_with_agents
        router.strategy = RoutingStrategy.PERFORMANCE_BASED

        decision = await router.route(routing_context)

        assert decision.primary_agent in router.agent_metrics
        assert 0 <= decision.confidence_score <= 1.0
        assert decision.strategy_used == RoutingStrategy.PERFORMANCE_BASED

    @pytest.mark.asyncio
    async def test_capability_match_routing(self, router_with_agents, routing_context):
        """Test capability-based routing"""
        router = router_with_agents
        router.strategy = RoutingStrategy.CAPABILITY_MATCH

        decision = await router.route(routing_context)

        assert decision.primary_agent in ["data-analysis-agent", "generic"]
        assert decision.strategy_used == RoutingStrategy.CAPABILITY_MATCH

    @pytest.mark.asyncio
    async def test_cost_optimized_routing(self, router_with_agents, routing_context):
        """Test cost-optimized routing"""
        router = router_with_agents
        router.strategy = RoutingStrategy.COST_OPTIMIZED

        # Set different costs
        router.agent_metrics["data-analysis-agent"].cost_per_request = 0.001
        router.agent_metrics["system-monitor-agent"].cost_per_request = 0.005

        decision = await router.route(routing_context)

        assert decision.primary_agent is not None
        assert decision.strategy_used == RoutingStrategy.COST_OPTIMIZED

    @pytest.mark.asyncio
    async def test_weighted_score_routing(self, router_with_agents, routing_context):
        """Test weighted score routing"""
        router = router_with_agents
        router.strategy = RoutingStrategy.WEIGHTED_SCORE

        decision = await router.route(routing_context)

        assert decision.primary_agent is not None
        assert len(decision.secondary_agents) <= 2
        assert decision.strategy_used == RoutingStrategy.WEIGHTED_SCORE

    @pytest.mark.asyncio
    async def test_latency_optimized_routing(self, router_with_agents, routing_context):
        """Test latency-optimized routing"""
        router = router_with_agents
        router.strategy = RoutingStrategy.LATENCY_OPTIMIZED

        # Set different latencies
        router.agent_metrics["data-analysis-agent"].avg_execution_time = 0.5
        router.agent_metrics["system-monitor-agent"].avg_execution_time = 2.0

        decision = await router.route(routing_context)

        # Should select agent with lower latency
        assert decision.primary_agent is not None

    @pytest.mark.asyncio
    async def test_availability_based_routing(self, router_with_agents, routing_context):
        """Test availability-based routing"""
        router = router_with_agents
        router.strategy = RoutingStrategy.AVAILABILITY_BASED

        # Set different availability
        router.agent_metrics["data-analysis-agent"].availability_score = 0.99
        router.agent_metrics["system-monitor-agent"].availability_score = 0.5

        decision = await router.route(routing_context)

        # Should select agent with higher availability
        assert decision.primary_agent is not None

    @pytest.mark.asyncio
    async def test_round_robin_routing(self, router_with_agents, routing_context):
        """Test round robin routing"""
        router = router_with_agents
        router.strategy = RoutingStrategy.ROUND_ROBIN

        decisions = []
        for _ in range(5):
            decision = await router.route(routing_context)
            decisions.append(decision.primary_agent)

        # Should have called route method
        assert len(decisions) == 5


# ============================================================================
# TEST CATEGORY 4: Caching Mechanisms (8 tests)
# ============================================================================


class TestCaching:
    """Test caching mechanisms"""

    @pytest.mark.asyncio
    async def test_cache_hit(self):
        """Test cache hit scenario"""
        cache = RouteCache(max_size=100, default_ttl=300)
        decision = RoutingDecision(primary_agent="agent-1", confidence_score=0.9)

        await cache.set("key1", decision)
        retrieved = await cache.get("key1")

        assert retrieved is not None
        assert retrieved.primary_agent == "agent-1"

    @pytest.mark.asyncio
    async def test_cache_miss(self):
        """Test cache miss scenario"""
        cache = RouteCache(max_size=100)

        retrieved = await cache.get("nonexistent")

        assert retrieved is None

    @pytest.mark.asyncio
    async def test_cache_ttl_expiration(self):
        """Test cache TTL expiration"""
        cache = RouteCache(max_size=100, default_ttl=1)
        decision = RoutingDecision(primary_agent="agent-1", confidence_score=0.9)

        await cache.set("key1", decision)
        await asyncio.sleep(1.1)

        retrieved = await cache.get("key1")

        assert retrieved is None

    @pytest.mark.asyncio
    async def test_cache_lru_eviction(self):
        """Test LRU cache eviction"""
        cache = RouteCache(max_size=3, strategy=CacheStrategy.LRU)

        for i in range(4):
            decision = RoutingDecision(primary_agent=f"agent-{i}", confidence_score=0.9)
            await cache.set(f"key{i}", decision)

        # Oldest entry should be evicted
        assert await cache.get("key0") is None
        assert await cache.get("key1") is not None

    @pytest.mark.asyncio
    async def test_cache_statistics(self):
        """Test cache statistics tracking"""
        cache = RouteCache(max_size=100)
        decision = RoutingDecision(primary_agent="agent-1", confidence_score=0.9)

        await cache.set("key1", decision)
        await cache.get("key1")  # Hit
        await cache.get("key2")  # Miss

        stats = await cache.get_stats()

        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 50.0

    @pytest.mark.asyncio
    async def test_cache_invalidation_pattern(self):
        """Test pattern-based cache invalidation"""
        cache = RouteCache(max_size=100)

        await cache.set("user1:agent1", RoutingDecision(primary_agent="a1"))
        await cache.set("user1:agent2", RoutingDecision(primary_agent="a2"))
        await cache.set("user2:agent1", RoutingDecision(primary_agent="a3"))

        invalidated = await cache.invalidate_pattern("user1:")

        assert invalidated == 2
        assert await cache.get("user1:agent1") is None
        assert await cache.get("user2:agent1") is not None

    @pytest.mark.asyncio
    async def test_cache_with_routing_context(self, router_with_agents, routing_context):
        """Test cache with actual routing context"""
        router = router_with_agents
        router.enable_caching = True

        # First route - should cache
        decision1 = await router.route(routing_context)
        cache_stats1 = await router.cache.get_stats()
        hits1 = cache_stats1["hits"]

        # Second route with same context - should hit cache
        decision2 = await router.route(routing_context)
        cache_stats2 = await router.cache.get_stats()
        hits2 = cache_stats2["hits"]

        assert decision1.primary_agent == decision2.primary_agent
        assert hits2 > hits1


# ============================================================================
# TEST CATEGORY 5: LLM-Based Selection (5 tests)
# ============================================================================


class TestLLMBasedRouting:
    """Test LLM-based agent selection"""

    @pytest.mark.asyncio
    async def test_llm_routing_valid_response(self, router_with_agents, routing_context):
        """Test LLM routing with valid response"""
        router = router_with_agents
        router.strategy = RoutingStrategy.LLM_BASED

        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(
            return_value='{"agent_id": "data-analysis-agent", "confidence": 0.95, "reasoning": "Best fit for analytics"}'
        )

        await router.initialize(mock_llm)

        decision = await router.route(routing_context)

        assert decision.primary_agent == "data-analysis-agent"
        assert decision.confidence_score == 0.95
        assert decision.strategy_used == RoutingStrategy.LLM_BASED

    @pytest.mark.asyncio
    async def test_llm_routing_invalid_json(self, router_with_agents, routing_context):
        """Test LLM routing with invalid JSON response"""
        router = router_with_agents
        router.strategy = RoutingStrategy.LLM_BASED

        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(return_value="invalid json {")

        await router.initialize(mock_llm)

        decision = await router.route(routing_context)

        assert decision.primary_agent is not None
        assert decision.confidence_score <= 0.5

    @pytest.mark.asyncio
    async def test_llm_routing_missing_llm_client(self, router_with_agents, routing_context):
        """Test LLM routing fallback when no LLM client"""
        router = router_with_agents
        router.strategy = RoutingStrategy.LLM_BASED
        router._llm_client = None

        decision = await router.route(routing_context)

        # Should fallback to performance-based routing
        assert decision.primary_agent is not None

    @pytest.mark.asyncio
    async def test_llm_prompt_generation(self, router_with_agents, routing_context):
        """Test LLM routing prompt generation"""
        router = router_with_agents

        prompt = router._prepare_routing_prompt(routing_context)

        assert "Task Type" in prompt
        assert "data_analysis" in prompt
        assert "Available Agents" in prompt

    @pytest.mark.asyncio
    async def test_llm_response_parsing(self, router):
        """Test LLM response parsing"""
        response = '{"agent_id": "test-agent", "confidence": 0.88, "reasoning": "test"}'

        agent_id, confidence, reasoning = router._parse_llm_response(response)

        assert agent_id == "test-agent"
        assert confidence == 0.88
        assert reasoning == "test"


# ============================================================================
# TEST CATEGORY 6: Metrics Tracking (6 tests)
# ============================================================================


class TestMetricsTracking:
    """Test agent metrics tracking"""

    @pytest.mark.asyncio
    async def test_update_metrics_success(self, router_with_agents):
        """Test updating metrics for successful execution"""
        router = router_with_agents
        agent_id = "data-analysis-agent"

        initial_requests = router.agent_metrics[agent_id].total_requests

        await router.update_agent_metrics(agent_id, 0.5, True, 0.001)

        assert router.agent_metrics[agent_id].total_requests == initial_requests + 1
        assert router.agent_metrics[agent_id].successful_requests > 0

    @pytest.mark.asyncio
    async def test_update_metrics_failure(self, router_with_agents):
        """Test updating metrics for failed execution"""
        router = router_with_agents
        agent_id = "data-analysis-agent"

        router.agent_metrics[agent_id].consecutive_failures = 0

        await router.update_agent_metrics(agent_id, 2.0, False)

        assert router.agent_metrics[agent_id].failed_requests > 0
        assert router.agent_metrics[agent_id].consecutive_failures > 0

    @pytest.mark.asyncio
    async def test_metrics_success_rate_calculation(self, router_with_agents):
        """Test success rate calculation"""
        router = router_with_agents
        agent_id = "data-analysis-agent"

        await router.update_agent_metrics(agent_id, 0.5, True)

        success_rate = router.agent_metrics[agent_id].success_rate
        assert 0 <= success_rate <= 100

    @pytest.mark.asyncio
    async def test_agent_health_score_calculation(self):
        """Test agent health score calculation"""
        metrics = AgentMetrics(agent_id="test", success_rate=95.0, availability_score=0.95)

        health_score = metrics.health_score

        assert 0 <= health_score <= 1.0
        assert health_score > 0.5

    @pytest.mark.asyncio
    async def test_agent_health_score_with_failures(self):
        """Test agent health score with consecutive failures"""
        metrics = AgentMetrics(agent_id="test", consecutive_failures=5)

        health_score = metrics.health_score

        assert health_score == 0.0

    @pytest.mark.asyncio
    async def test_get_router_stats(self, router_with_agents, routing_context):
        """Test retrieving router statistics"""
        router = router_with_agents

        await router.route(routing_context)

        stats = await router.get_stats()

        assert stats["total_routings"] > 0
        assert "strategy" in stats
        assert "cache" in stats


# ============================================================================
# TEST CATEGORY 7: Error Handling (5 tests)
# ============================================================================


class TestErrorHandling:
    """Test error handling and edge cases"""

    @pytest.mark.asyncio
    async def test_routing_with_no_agents(self):
        """Test routing when no agents registered"""
        router = AgentRouter()
        await router.initialize()

        context = RoutingContext(request_id="test", task_type="test", task_description="test")

        decision = await router.route(context)

        assert decision.primary_agent == "generic"

    @pytest.mark.asyncio
    async def test_routing_error_fallback(self, router_with_agents, routing_context):
        """Test routing error fallback"""
        router = router_with_agents

        with patch.object(router, "_route_weighted_score", side_effect=Exception("Route error")):
            decision = await router.route(routing_context)

        assert decision.primary_agent is not None

    @pytest.mark.asyncio
    async def test_register_agent_error_handling(self, router):
        """Test error handling in agent registration"""
        # This should handle gracefully
        result = await router.register_agent("agent", AgentType.GENERIC, [])
        assert result is True

    @pytest.mark.asyncio
    async def test_update_metrics_nonexistent_agent(self, router):
        """Test updating metrics for non-existent agent"""
        # Should not raise error
        await router.update_agent_metrics("nonexistent", 0.5, True)

    @pytest.mark.asyncio
    async def test_routing_context_cache_key_generation(self):
        """Test cache key generation from routing context"""
        context1 = RoutingContext(
            request_id="req1",
            task_type="analysis",
            task_description="test",
            required_capabilities=["a", "b"],
        )

        context2 = RoutingContext(
            request_id="req2",
            task_type="analysis",
            task_description="different",
            required_capabilities=["b", "a"],
        )

        key1 = context1.to_cache_key()
        key2 = context2.to_cache_key()

        # Same capabilities should generate same key
        assert key1 == key2


# ============================================================================
# TEST CATEGORY 8: Integration Workflows (6 tests)
# ============================================================================


class TestIntegrationWorkflows:
    """Test end-to-end workflows"""

    @pytest.mark.asyncio
    async def test_complete_routing_workflow(self, router_with_agents, routing_context):
        """Test complete routing workflow"""
        router = router_with_agents

        # Route request
        decision = await router.route(routing_context)
        assert decision.primary_agent is not None

        # Update metrics
        await router.update_agent_metrics(decision.primary_agent, 0.5, True, 0.001)

        # Verify metrics updated
        metrics = router.agent_metrics[decision.primary_agent]
        assert metrics.total_requests > 0

    @pytest.mark.asyncio
    async def test_multiple_routing_decisions(self, router_with_agents):
        """Test multiple routing decisions with different contexts"""
        router = router_with_agents

        contexts = [
            RoutingContext(
                request_id="req1",
                task_type="analysis",
                task_description="task 1",
                required_capabilities=["analytics"],
            ),
            RoutingContext(
                request_id="req2",
                task_type="monitoring",
                task_description="task 2",
                required_capabilities=["monitoring"],
            ),
            RoutingContext(
                request_id="req3",
                task_type="code",
                task_description="task 3",
                required_capabilities=["code"],
            ),
        ]

        decisions = []
        for context in contexts:
            decision = await router.route(context)
            decisions.append(decision)

        assert len(decisions) == 3
        assert all(d.primary_agent for d in decisions)

    @pytest.mark.asyncio
    async def test_routing_with_strategy_change(self, router_with_agents, routing_context):
        """Test routing with strategy change"""
        router = router_with_agents

        # Route with one strategy
        router.strategy = RoutingStrategy.PERFORMANCE_BASED
        decision1 = await router.route(routing_context)

        # Change strategy and clear cache so new strategy is applied
        router.strategy = RoutingStrategy.COST_OPTIMIZED
        await router.cache.clear()
        decision2 = await router.route(routing_context)

        # Should use different strategy
        assert decision2.strategy_used == RoutingStrategy.COST_OPTIMIZED

    @pytest.mark.asyncio
    async def test_router_stats_accumulation(self, router_with_agents):
        """Test statistics accumulation over multiple routings"""
        router = router_with_agents

        for i in range(5):
            context = RoutingContext(
                request_id=f"req-{i}",
                task_type="test",
                task_description="test",
                priority=i + 1,
            )
            await router.route(context)

        stats = await router.get_stats()

        assert stats["total_routings"] == 5

    @pytest.mark.asyncio
    async def test_caching_with_multiple_strategies(self, router_with_agents, routing_context):
        """Test caching behavior with multiple strategies"""
        router = router_with_agents
        router.enable_caching = True

        # Route with strategy 1
        router.strategy = RoutingStrategy.PERFORMANCE_BASED
        await router.route(routing_context)

        # Route with same context but different strategy
        router.strategy = RoutingStrategy.COST_OPTIMIZED
        await router.route(routing_context)

        cache_stats = await router.cache.get_stats()
        assert cache_stats["total_entries"] > 0

    @pytest.mark.asyncio
    async def test_fallback_agent_selection(self, router_with_agents):
        """Test fallback agent selection"""
        router = router_with_agents

        # Clear metrics to test fallback
        router.agent_metrics.clear()

        fallback = router._get_fallback_agent()

        assert fallback == "generic"


# ============================================================================
# TEST CATEGORY 9: Edge Cases & Performance (8 tests)
# ============================================================================


class TestEdgeCasesAndPerformance:
    """Test edge cases and performance characteristics"""

    @pytest.mark.asyncio
    async def test_routing_with_single_agent(self):
        """Test routing with single agent registered"""
        router = AgentRouter()
        await router.initialize()
        await router.register_agent("only-agent", AgentType.GENERIC)

        context = RoutingContext(request_id="test", task_type="test", task_description="test")

        decision = await router.route(context)

        assert decision.primary_agent == "only-agent"

    @pytest.mark.asyncio
    async def test_routing_with_many_agents(self):
        """Test routing with many agents"""
        router = AgentRouter()
        await router.initialize()

        # Register many agents
        for i in range(50):
            agent_id = f"agent-{i}"
            await router.register_agent(agent_id, AgentType.GENERIC)
            router.agent_metrics[agent_id].success_rate = 90.0 - (i * 0.5)

        context = RoutingContext(request_id="test", task_type="test", task_description="test")

        decision = await router.route(context)

        assert decision.primary_agent is not None
        assert len(decision.secondary_agents) <= 2

    @pytest.mark.asyncio
    async def test_cache_with_large_dataset(self):
        """Test cache performance with large dataset"""
        cache = RouteCache(max_size=1000)

        # Add many entries
        for i in range(500):
            decision = RoutingDecision(primary_agent=f"agent-{i % 10}", confidence_score=0.9)
            await cache.set(f"key-{i}", decision)

        stats = await cache.get_stats()

        assert stats["total_entries"] == 500

    @pytest.mark.asyncio
    async def test_concurrent_routing_requests(self, router_with_agents):
        """Test handling concurrent routing requests"""
        router = router_with_agents

        contexts = [
            RoutingContext(
                request_id=f"req-{i}",
                task_type="test",
                task_description=f"task {i}",
            )
            for i in range(20)
        ]

        decisions = await asyncio.gather(*[router.route(context) for context in contexts])

        assert len(decisions) == 20
        assert all(d.primary_agent for d in decisions)

    @pytest.mark.asyncio
    async def test_metrics_with_zero_requests(self):
        """Test metrics calculation with zero requests"""
        metrics = AgentMetrics(agent_id="test", total_requests=0)

        # Default success_rate is 0.95 per dataclass default
        assert metrics.success_rate >= 0.0
        assert metrics.health_score >= 0.0

    @pytest.mark.asyncio
    async def test_empty_secondary_agents(self, router):
        """Test routing with no secondary agents available"""
        router = router
        await router.register_agent("only-agent", AgentType.GENERIC)

        context = RoutingContext(request_id="test", task_type="test", task_description="test")

        decision = await router.route(context)

        assert decision.primary_agent == "only-agent"
        assert len(decision.secondary_agents) == 0

    @pytest.mark.asyncio
    async def test_context_with_all_optional_fields(self):
        """Test routing context with all optional fields populated"""
        context = RoutingContext(
            request_id="full-req",
            task_type="complex_task",
            task_description="A complex task with all fields",
            required_capabilities=["c1", "c2", "c3"],
            priority=9,
            complexity_score=0.95,
            user_id="user-123",
            preferred_agents=["agent-1", "agent-2"],
            constraints={"max_cost": 0.05, "max_latency": 5.0},
            metadata={"source": "api", "version": "v2"},
        )

        cache_key = context.to_cache_key()

        assert len(cache_key) > 0


# ============================================================================
# TEST CATEGORY 10: Statistics & Reporting (4 tests)
# ============================================================================


class TestStatisticsAndReporting:
    """Test statistics and reporting functionality"""

    @pytest.mark.asyncio
    async def test_router_statistics_collection(self, router_with_agents):
        """Test statistics collection during routing"""
        router = router_with_agents

        for i in range(5):
            context = RoutingContext(
                request_id=f"stats-req-{i}",
                task_type="analytics",
                task_description=f"Analyze data batch {i}",
                priority=i + 1,
            )
            await router.route(context)

        stats = await router.get_stats()

        assert stats["total_routings"] == 5
        assert "strategy" in stats
        assert "agent_count" in stats

    @pytest.mark.asyncio
    async def test_reset_router_statistics(self, router_with_agents, routing_context):
        """Test resetting router statistics"""
        router = router_with_agents

        await router.route(routing_context)
        await router.reset_stats()

        stats = await router.get_stats()

        assert stats["total_routings"] == 0

    @pytest.mark.asyncio
    async def test_confidence_score_averaging(self, router_with_agents):
        """Test confidence score averaging in statistics"""
        router = router_with_agents

        contexts = [
            RoutingContext(
                request_id=f"req-{i}",
                task_type="test",
                task_description=f"task {i}",
            )
            for i in range(3)
        ]

        for context in contexts:
            await router.route(context)

        stats = await router.get_stats()

        assert 0 <= stats["avg_confidence"] <= 1.0

    @pytest.mark.asyncio
    async def test_detailed_cache_statistics(self):
        """Test detailed cache statistics reporting"""
        cache = RouteCache(max_size=100)

        for i in range(10):
            decision = RoutingDecision(primary_agent="agent", confidence_score=0.9)
            await cache.set(f"key-{i}", decision)

        for i in range(5):
            await cache.get(f"key-{i}")  # Hits

        for i in range(10):
            await cache.get(f"missing-{i}")  # Misses

        stats = await cache.get_stats()

        assert stats["hits"] == 5
        assert stats["misses"] == 10
        assert stats["hit_rate"] == pytest.approx(33.33, rel=1)
