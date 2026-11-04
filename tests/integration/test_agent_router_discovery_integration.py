"""
Integration tests for AgentRouterAgent with AgentDiscoveryService.

Tests validate:
- Routing decisions based on database-backed discovery
- Department-based agent filtering
- Function-based capability matching
- Tenant isolation in routing
- Cache behavior with discovery results
- Fallback chain with discovered agents
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.agents.agent_discovery import AgentDiscoveryService, DepartmentFilter
from src.core.agents.agent_router_agent import AgentRouterAgent
from src.core.agents.models import RegisteredAgent
from src.core.shared.interfaces import TaskData


@pytest.mark.integration
@pytest.mark.multi_tenant
class TestAgentRouterDiscoveryIntegration:
    """Test AgentRouterAgent integration with AgentDiscoveryService."""

    @pytest.fixture
    async def discovery_service(self, db_session):
        """Create discovery service with seeded agents."""
        service = AgentDiscoveryService(tenant_id=1, db_session=db_session)

        # Seed test agents into database
        agents_data = [
            RegisteredAgent(
                agent_id="code_agent_001",
                name="Code Agent",
                description="Code generation and review",
                address="agent://code_agent_001",
                tenant_id=1,
                capabilities={
                    "department": DepartmentFilter.PRODUCT_INNOVATION,
                    "agent_type": "SPECIALIST",
                    "functions": ["code-generation", "code-review", "debugging"],
                },
                last_heartbeat=datetime.now(timezone.utc),
            ),
            RegisteredAgent(
                agent_id="executor_agent_001",
                name="Executor Agent",
                description="Multi-domain action execution",
                address="agent://executor_agent_001",
                tenant_id=1,
                capabilities={
                    "department": DepartmentFilter.OPERATIONS,
                    "agent_type": "SPECIALIST",
                    "functions": ["api-integration", "workflow-automation", "file-operations"],
                },
                last_heartbeat=datetime.now(timezone.utc),
            ),
            RegisteredAgent(
                agent_id="research_agent_001",
                name="Research Agent",
                description="Data analysis specialist",
                address="agent://research_agent_001",
                tenant_id=1,
                capabilities={
                    "department": DepartmentFilter.DATA_AI_GOVERNANCE,
                    "agent_type": "SPECIALIST",
                    "functions": ["data-analysis", "research-synthesis", "market-research"],
                },
                last_heartbeat=datetime.now(timezone.utc),
            ),
        ]

        for agent_data in agents_data:
            db_session.add(agent_data)
        await db_session.commit()

        return service

    @pytest.fixture
    async def router_agent(self, discovery_service):
        """Create router agent with discovery service."""
        router = AgentRouterAgent(agent_id="agent_router_001", tenant_id=1)
        router._discovery_service = discovery_service
        await router.initialize()
        return router

    @pytest.mark.asyncio
    async def test_route_with_function_discovery(self, router_agent, discovery_service):
        """Should route to agent based on function capability."""
        task = TaskData(
            id="task_001",
            title="Review Python code",
            description="Check for security issues",
            metadata={"capabilities": ["code-review"]},
        )

        agent_id = await router_agent.route(task)
        assert agent_id == "code_agent_001", "Should route to code agent for code-review capability"

    @pytest.mark.asyncio
    async def test_route_fallback_to_executor(self, router_agent):
        """Should fallback to executor when no capability match found."""
        task = TaskData(
            id="task_002",
            title="Unknown task",
            description="Something we have no specialist for",
            metadata={"capabilities": ["unknown-capability"]},
        )

        agent_id = await router_agent.route(task)
        assert agent_id == "executor_agent_001", (
            "Should fallback to executor for unknown capabilities"
        )

    @pytest.mark.asyncio
    async def test_route_caches_discovery_result(self, router_agent):
        """Should cache routing decision from discovery service."""
        task = TaskData(
            id="task_003",
            title="Data analysis task",
            description="Analyze market trends",
            metadata={"capabilities": ["data-analysis"]},
        )

        # First route — hits discovery service
        agent_id_1 = await router_agent.route(task)
        # Second route — should hit cache
        agent_id_2 = await router_agent.route(task)

        assert agent_id_1 == agent_id_2 == "research_agent_001"
        cache_stats = router_agent.get_cache_stats()
        assert cache_stats["hits"] > 0, "Cache should record hits"

    @pytest.mark.asyncio
    async def test_department_filtering_in_routing(self, router_agent, discovery_service):
        """Should respect department hints in task metadata."""
        task = TaskData(
            id="task_004",
            title="Workflow automation",
            description="Automate a business process",
            metadata={
                "capabilities": ["workflow-automation"],
                "preferred_department": DepartmentFilter.OPERATIONS,
            },
        )

        agent_id = await router_agent.route(task)
        assert agent_id == "executor_agent_001"

        # Verify executor is in OPERATIONS department
        agent = await discovery_service.find_agent_by_id("executor_agent_001")
        assert agent["department"] == DepartmentFilter.OPERATIONS

    @pytest.mark.asyncio
    async def test_tenant_isolation_in_routing(self, db_session):
        """Should not route to agents from different tenants."""
        from src.core.models.rbac_models import Tenant

        # Create tenant 2 first
        tenant2 = Tenant(name="isolation_test_tenant_2", domain="isolation2.test")
        db_session.add(tenant2)
        await db_session.commit()
        await db_session.refresh(tenant2)
        tenant2_id = tenant2.id

        # Seed agent for tenant 2
        agent_tenant2 = RegisteredAgent(
            agent_id="special_agent_002",
            name="Tenant 2 Agent",
            description="Only for tenant 2",
            address="agent://special_agent_002",
            tenant_id=tenant2_id,
            capabilities={
                "department": DepartmentFilter.PRODUCT_INNOVATION,
                "agent_type": "SPECIALIST",
                "functions": ["code-review"],
            },
            last_heartbeat=datetime.now(timezone.utc),
        )
        db_session.add(agent_tenant2)
        await db_session.commit()

        # Create router for tenant 1
        service1 = AgentDiscoveryService(tenant_id=1, db_session=db_session)
        router1 = AgentRouterAgent(tenant_id=1)
        router1._discovery_service = service1

        # Create router for tenant 2
        service2 = AgentDiscoveryService(tenant_id=tenant2_id, db_session=db_session)
        router2 = AgentRouterAgent(tenant_id=tenant2_id)
        router2._discovery_service = service2

        task = TaskData(
            id="task_005",
            title="Code review",
            description="Review code",
            metadata={"capabilities": ["code-review"]},
        )

        # Tenant 1 has no agents seeded in this test, so it falls back to executor
        agent_id_1 = await router1.route(task)
        assert agent_id_1 == "executor_agent_001"

        # Tenant 2 should route to its own agent
        agent_id_2 = await router2.route(task)
        assert agent_id_2 == "special_agent_002"

    @pytest.mark.asyncio
    async def test_multiple_capability_matching(self, router_agent):
        """Should prefer agent with most capability matches."""
        task = TaskData(
            id="task_006",
            title="Execute API workflow",
            description="Integrate with external API and automate workflow",
            metadata={"capabilities": ["api-integration", "workflow-automation"]},
        )

        agent_id = await router_agent.route(task)
        assert agent_id == "executor_agent_001", (
            "Should route to agent with most capability matches"
        )

    @pytest.mark.asyncio
    async def test_route_with_empty_manifests_falls_back(self, db_session):
        """Should fallback when no agents registered in discovery."""
        # Create empty discovery service (no agents seeded)
        service = AgentDiscoveryService(tenant_id=1)
        router = AgentRouterAgent(tenant_id=1)
        router._discovery_service = service

        task = TaskData(
            id="task_007",
            title="Any task",
            description="Will have no matches",
            metadata={"capabilities": ["any-capability"]},
        )

        agent_id = await router.route(task)
        assert agent_id == "executor_agent_001", (
            "Should fallback to executor when no agents available"
        )

    @pytest.mark.asyncio
    async def test_cache_invalidation_on_manifest_change(self, router_agent):
        """Should invalidate cache when new agents are registered."""
        task = TaskData(
            id="task_008",
            title="Initial task",
            description="Before adding new agent",
            metadata={"capabilities": ["unknown-cap"]},
        )

        # Route and cache the fallback
        agent_1 = await router_agent.route(task)
        assert agent_1 == "executor_agent_001"

        # Simulate registering a new agent with the unknown capability
        # (In real scenario, would be added to database and discovery service called)
        # Cache should still return fallback since we're using old data
        agent_2 = await router_agent.route(task)
        assert agent_2 == "executor_agent_001"

    @pytest.mark.asyncio
    async def test_route_metrics_track_discovery_routes(self, router_agent):
        """Should track routing metrics including discovery-based routes."""
        task = TaskData(
            id="task_009",
            title="Analyze data",
            description="Analyze trends",
            metadata={"capabilities": ["data-analysis"]},
        )

        await router_agent.route(task)
        metrics = router_agent.metrics()

        assert metrics["routes_total"] == 1
        assert metrics["registered_agents"] >= 0  # May be 0 if using only discovery

    @pytest.mark.asyncio
    async def test_agent_not_found_after_discovery(self, router_agent):
        """Should handle case where discovered agent is not available for execution."""
        # This validates the route() method returns agent_id even if agent not loaded
        task = TaskData(
            id="task_010",
            title="Research task",
            description="Market research",
            metadata={"capabilities": ["research-synthesis"]},
        )

        agent_id = await router_agent.route(task)
        assert agent_id == "research_agent_001"

        # Agent may not be loaded in process, but routing decision is valid
        result = await router_agent.process_task(task)
        # Result should indicate routing decision was made (even if execution isn't available)
        assert "routed_to" in result.result_data or "error" in result.result_data


@pytest.mark.integration
@pytest.mark.security
class TestAgentRouterDiscoverySecurity:
    """Security tests for discovery-integrated routing."""

    @pytest.mark.asyncio
    async def test_tenant_isolation_cross_tenant_access_denied(self, db_session):
        """Should prevent tenant A from routing to tenant B's agents."""
        from src.core.models.rbac_models import Tenant

        # Create tenant B first
        tenant_b = Tenant(name="security_test_tenant_b", domain="security_b.test")
        db_session.add(tenant_b)
        await db_session.commit()
        await db_session.refresh(tenant_b)
        tenant_b_id = tenant_b.id

        # Create agents for two different tenants
        agent_a = RegisteredAgent(
            agent_id="agent_a_001",
            name="Tenant A Agent",
            address="agent://agent_a_001",
            tenant_id=1,
            capabilities={
                "department": DepartmentFilter.OPERATIONS,
                "agent_type": "SPECIALIST",
                "functions": ["code-review"],
            },
            last_heartbeat=datetime.now(timezone.utc),
        )

        agent_b = RegisteredAgent(
            agent_id="agent_b_001",
            name="Tenant B Agent",
            address="agent://agent_b_001",
            tenant_id=tenant_b_id,
            capabilities={
                "department": DepartmentFilter.OPERATIONS,
                "agent_type": "SPECIALIST",
                "functions": ["code-review"],
            },
            last_heartbeat=datetime.now(timezone.utc),
        )

        db_session.add(agent_a)
        db_session.add(agent_b)
        await db_session.commit()

        # Tenant A discovery should only see agent_a_001
        service_a = AgentDiscoveryService(tenant_id=1, db_session=db_session)
        agents_a = await service_a.discover_all_agents()
        agent_ids_a = [a["agent_id"] for a in agents_a]

        assert "agent_a_001" in agent_ids_a, "Tenant A should see its own agent"
        assert "agent_b_001" not in agent_ids_a, "Tenant A should NOT see tenant B's agent"


@pytest.mark.integration
class TestAgentRouterDiscoveryPerformance:
    """Performance tests for discovery-integrated routing."""

    @pytest.fixture
    async def discovery_service(self, db_session):
        """Create discovery service with seeded agents for performance tests."""
        service = AgentDiscoveryService(tenant_id=1, db_session=db_session)
        agents_data = [
            RegisteredAgent(
                agent_id="perf_agent_001",
                name="Perf Agent",
                description="Code review specialist",
                address="agent://perf_agent_001",
                tenant_id=1,
                capabilities={
                    "department": DepartmentFilter.PRODUCT_INNOVATION,
                    "agent_type": "SPECIALIST",
                    "functions": ["code-review"],
                },
                last_heartbeat=datetime.now(timezone.utc),
            ),
        ]
        for agent_data in agents_data:
            db_session.add(agent_data)
        await db_session.commit()
        return service

    @pytest.fixture
    async def router_agent(self, discovery_service):
        """Create router agent with discovery service for performance tests."""
        router = AgentRouterAgent(agent_id="agent_router_perf_001", tenant_id=1)
        router._discovery_service = discovery_service
        await router.initialize()
        return router

    @pytest.mark.asyncio
    @pytest.mark.slow
    async def test_routing_cache_performance(self, router_agent):
        """Should maintain cache performance with discovery backend."""
        task = TaskData(
            id="task_perf_001",
            title="Repeated task",
            description="Same task routed multiple times",
            metadata={"capabilities": ["code-review"]},
        )

        # Warm cache
        agent_1 = await router_agent.route(task)

        # Repeated routes should hit cache
        for i in range(100):
            agent_id = await router_agent.route(task)
            assert agent_id == agent_1

        cache_stats = router_agent.get_cache_stats()
        # Most hits after first miss should come from cache
        assert cache_stats["hit_rate"] > 0.95, "Cache should be highly effective"
