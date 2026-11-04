"""
Slice 8: AgentRegistry - Comprehensive Test Suite (RED Phase)

Tests central agent registration, discovery, and metadata management.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from src.core.agents.capabilities.agent_registry import AgentRegistry
from src.core.agents.capabilities.schemas import AgentMetadata, AgentRegistration, AgentStatus

# ============================================================================
# TEST SUITE 1: Agent Registration
# ============================================================================


class TestAgentRegistration:
    """Test agent registration workflow"""

    @pytest.mark.asyncio
    async def test_registers_agent(self):
        """Should register an agent successfully"""
        registry = AgentRegistry()

        registration = AgentRegistration(
            agent_type="planner",
            agent_name="PlannerAgent",
            version="1.0.0",
            capabilities=["planning", "orchestration"],
            tenant_id=uuid4(),
        )

        result = await registry.register_agent(registration)

        assert result is not None
        assert result.agent_id is not None
        assert result.agent_type == "planner"
        assert result.status == AgentStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_generates_agent_id(self):
        """Should generate unique agent ID"""
        registry = AgentRegistry()

        registration = AgentRegistration(
            agent_type="executor",
            agent_name="ExecutorAgent",
            version="1.0.0",
            capabilities=["execution"],
            tenant_id=uuid4(),
        )

        result = await registry.register_agent(registration)

        assert isinstance(result.agent_id, UUID)

    @pytest.mark.asyncio
    async def test_stores_agent_metadata(self):
        """Should store complete agent metadata"""
        registry = AgentRegistry()

        registration = AgentRegistration(
            agent_type="retriever",
            agent_name="RetrieverAgent",
            version="2.0.0",
            capabilities=["retrieval", "search"],
            tenant_id=uuid4(),
            description="Knowledge base retrieval agent",
        )

        result = await registry.register_agent(registration)

        assert result.agent_name == "RetrieverAgent"
        assert result.version == "2.0.0"
        assert "retrieval" in result.capabilities
        assert result.description == "Knowledge base retrieval agent"


# ============================================================================
# TEST SUITE 2: Agent Discovery
# ============================================================================


class TestAgentDiscovery:
    """Test agent discovery by type and capability"""

    @pytest.mark.asyncio
    async def test_finds_agent_by_type(self):
        """Should find agents by type"""
        registry = AgentRegistry()
        tenant_id = uuid4()

        # Register planner agent
        reg = AgentRegistration(
            agent_type="planner",
            agent_name="PlannerAgent",
            version="1.0.0",
            capabilities=["planning"],
            tenant_id=tenant_id,
        )
        await registry.register_agent(reg)

        # Find by type
        agents = await registry.find_agents_by_type("planner", tenant_id)

        assert len(agents) > 0
        assert all(a.agent_type == "planner" for a in agents)

    @pytest.mark.asyncio
    async def test_finds_agent_by_capability(self):
        """Should find agents by capability"""
        registry = AgentRegistry()
        tenant_id = uuid4()

        # Register executor with execution capability
        reg = AgentRegistration(
            agent_type="executor",
            agent_name="ExecutorAgent",
            version="1.0.0",
            capabilities=["execution", "retry"],
            tenant_id=tenant_id,
        )
        await registry.register_agent(reg)

        # Find by capability
        agents = await registry.find_agents_by_capability("execution", tenant_id)

        assert len(agents) > 0
        assert all("execution" in a.capabilities for a in agents)

    @pytest.mark.asyncio
    async def test_returns_empty_for_nonexistent_type(self):
        """Should return empty list for nonexistent agent type"""
        registry = AgentRegistry()
        tenant_id = uuid4()

        agents = await registry.find_agents_by_type("nonexistent", tenant_id)

        assert isinstance(agents, list)
        assert len(agents) == 0


# ============================================================================
# TEST SUITE 3: Agent Retrieval
# ============================================================================


class TestAgentRetrieval:
    """Test individual agent retrieval"""

    @pytest.mark.asyncio
    async def test_gets_agent_by_id(self):
        """Should retrieve agent by ID"""
        registry = AgentRegistry()
        tenant_id = uuid4()

        # Register agent
        reg = AgentRegistration(
            agent_type="compliance",
            agent_name="ComplianceAgent",
            version="1.0.0",
            capabilities=["compliance"],
            tenant_id=tenant_id,
        )
        registered = await registry.register_agent(reg)

        # Retrieve by ID
        agent = await registry.get_agent(registered.agent_id, tenant_id)

        assert agent is not None
        assert agent.agent_id == registered.agent_id
        assert agent.agent_type == "compliance"

    @pytest.mark.asyncio
    async def test_returns_none_for_nonexistent_id(self):
        """Should return None for nonexistent agent ID"""
        registry = AgentRegistry()
        tenant_id = uuid4()
        nonexistent_id = uuid4()

        agent = await registry.get_agent(nonexistent_id, tenant_id)

        assert agent is None


# ============================================================================
# TEST SUITE 4: Tenant Isolation
# ============================================================================


class TestTenantIsolation:
    """Test tenant isolation in registry"""

    @pytest.mark.asyncio
    async def test_isolates_agents_by_tenant(self):
        """Should only return agents for current tenant"""
        registry = AgentRegistry()
        tenant_a = uuid4()
        tenant_b = uuid4()

        # Register agent for tenant A
        reg_a = AgentRegistration(
            agent_type="planner",
            agent_name="PlannerA",
            version="1.0.0",
            capabilities=["planning"],
            tenant_id=tenant_a,
        )
        await registry.register_agent(reg_a)

        # Register agent for tenant B
        reg_b = AgentRegistration(
            agent_type="planner",
            agent_name="PlannerB",
            version="1.0.0",
            capabilities=["planning"],
            tenant_id=tenant_b,
        )
        await registry.register_agent(reg_b)

        # Retrieve for tenant A
        agents_a = await registry.find_agents_by_type("planner", tenant_a)

        # Should only get tenant A's agent
        assert len(agents_a) == 1
        assert agents_a[0].tenant_id == tenant_a

    @pytest.mark.asyncio
    async def test_blocks_cross_tenant_access(self):
        """Should not allow access to other tenant's agents"""
        registry = AgentRegistry()
        tenant_a = uuid4()
        tenant_b = uuid4()

        # Register agent for tenant A
        reg = AgentRegistration(
            agent_type="executor",
            agent_name="ExecutorAgent",
            version="1.0.0",
            capabilities=["execution"],
            tenant_id=tenant_a,
        )
        registered = await registry.register_agent(reg)

        # Try to access from tenant B
        agent = await registry.get_agent(registered.agent_id, tenant_b)

        assert agent is None


# ============================================================================
# TEST SUITE 5: Agent Status Tracking
# ============================================================================


class TestAgentStatusTracking:
    """Test agent status lifecycle"""

    @pytest.mark.asyncio
    async def test_agent_starts_active(self):
        """Should start with ACTIVE status"""
        registry = AgentRegistry()

        reg = AgentRegistration(
            agent_type="reviewer",
            agent_name="ReviewerAgent",
            version="1.0.0",
            capabilities=["review"],
            tenant_id=uuid4(),
        )
        result = await registry.register_agent(reg)

        assert result.status == AgentStatus.ACTIVE

    @pytest.mark.asyncio
    async def test_updates_agent_status(self):
        """Should update agent status"""
        registry = AgentRegistry()
        tenant_id = uuid4()

        # Register agent
        reg = AgentRegistration(
            agent_type="planner",
            agent_name="PlannerAgent",
            version="1.0.0",
            capabilities=["planning"],
            tenant_id=tenant_id,
        )
        registered = await registry.register_agent(reg)

        # Update status
        updated = await registry.update_agent_status(
            registered.agent_id,
            AgentStatus.INACTIVE,
            tenant_id,
        )

        assert updated.status == AgentStatus.INACTIVE

    @pytest.mark.asyncio
    async def test_filters_by_status(self):
        """Should filter agents by status"""
        registry = AgentRegistry()
        tenant_id = uuid4()

        # Register and mark inactive
        reg = AgentRegistration(
            agent_type="executor",
            agent_name="ExecutorAgent",
            version="1.0.0",
            capabilities=["execution"],
            tenant_id=tenant_id,
        )
        registered = await registry.register_agent(reg)
        await registry.update_agent_status(
            registered.agent_id,
            AgentStatus.INACTIVE,
            tenant_id,
        )

        # Get only active agents
        active_agents = await registry.list_agents(
            tenant_id,
            status_filter=AgentStatus.ACTIVE,
        )

        # Inactive agent should not appear
        agent_ids = [a.agent_id for a in active_agents]
        assert registered.agent_id not in agent_ids


# ============================================================================
# TEST SUITE 6: Agent Versioning
# ============================================================================


class TestAgentVersioning:
    """Test agent version tracking"""

    @pytest.mark.asyncio
    async def test_stores_agent_version(self):
        """Should store agent version"""
        registry = AgentRegistry()

        reg = AgentRegistration(
            agent_type="compliance",
            agent_name="ComplianceAgent",
            version="2.1.0",
            capabilities=["compliance"],
            tenant_id=uuid4(),
        )
        result = await registry.register_agent(reg)

        assert result.version == "2.1.0"

    @pytest.mark.asyncio
    async def test_allows_multiple_versions(self):
        """Should allow multiple versions of same agent type"""
        registry = AgentRegistry()
        tenant_id = uuid4()

        # Register v1
        reg_v1 = AgentRegistration(
            agent_type="planner",
            agent_name="PlannerAgent",
            version="1.0.0",
            capabilities=["planning"],
            tenant_id=tenant_id,
        )
        await registry.register_agent(reg_v1)

        # Register v2
        reg_v2 = AgentRegistration(
            agent_type="planner",
            agent_name="PlannerAgent",
            version="2.0.0",
            capabilities=["planning", "advanced"],
            tenant_id=tenant_id,
        )
        await registry.register_agent(reg_v2)

        # Both should exist
        agents = await registry.find_agents_by_type("planner", tenant_id)
        versions = [a.version for a in agents]

        assert "1.0.0" in versions
        assert "2.0.0" in versions


# ============================================================================
# TEST SUITE 7: Agent Listing
# ============================================================================


class TestAgentListing:
    """Test listing all agents"""

    @pytest.mark.asyncio
    async def test_lists_all_agents(self):
        """Should list all agents for tenant"""
        registry = AgentRegistry()
        tenant_id = uuid4()

        # Register multiple agents
        for i in range(3):
            reg = AgentRegistration(
                agent_type=f"type_{i}",
                agent_name=f"Agent{i}",
                version="1.0.0",
                capabilities=["test"],
                tenant_id=tenant_id,
            )
            await registry.register_agent(reg)

        # List all
        agents = await registry.list_agents(tenant_id)

        assert len(agents) == 3

    @pytest.mark.asyncio
    async def test_returns_empty_list_for_new_tenant(self):
        """Should return empty list for tenant with no agents"""
        registry = AgentRegistry()
        tenant_id = uuid4()

        agents = await registry.list_agents(tenant_id)

        assert isinstance(agents, list)
        assert len(agents) == 0


# ============================================================================
# TEST SUITE 8: Agent Unregistration
# ============================================================================


class TestAgentUnregistration:
    """Test agent unregistration"""

    @pytest.mark.asyncio
    async def test_unregisters_agent(self):
        """Should unregister an agent"""
        registry = AgentRegistry()
        tenant_id = uuid4()

        # Register agent
        reg = AgentRegistration(
            agent_type="executor",
            agent_name="ExecutorAgent",
            version="1.0.0",
            capabilities=["execution"],
            tenant_id=tenant_id,
        )
        registered = await registry.register_agent(reg)

        # Unregister
        success = await registry.unregister_agent(registered.agent_id, tenant_id)

        assert success is True

        # Should not be retrievable
        agent = await registry.get_agent(registered.agent_id, tenant_id)
        assert agent is None

    @pytest.mark.asyncio
    async def test_prevents_cross_tenant_unregistration(self):
        """Should prevent unregistering other tenant's agents"""
        registry = AgentRegistry()
        tenant_a = uuid4()
        tenant_b = uuid4()

        # Register for tenant A
        reg = AgentRegistration(
            agent_type="planner",
            agent_name="PlannerAgent",
            version="1.0.0",
            capabilities=["planning"],
            tenant_id=tenant_a,
        )
        registered = await registry.register_agent(reg)

        # Try to unregister from tenant B
        success = await registry.unregister_agent(registered.agent_id, tenant_b)

        assert success is False


# ============================================================================
# TEST SUITE 9: Edge Cases
# ============================================================================


class TestEdgeCases:
    """Test edge cases and error handling"""

    @pytest.mark.asyncio
    async def test_handles_duplicate_registration(self):
        """Should handle duplicate agent registration"""
        registry = AgentRegistry()
        tenant_id = uuid4()

        reg = AgentRegistration(
            agent_type="planner",
            agent_name="PlannerAgent",
            version="1.0.0",
            capabilities=["planning"],
            tenant_id=tenant_id,
        )

        # Register twice
        result1 = await registry.register_agent(reg)
        result2 = await registry.register_agent(reg)

        # Should get different IDs
        assert result1.agent_id != result2.agent_id

    @pytest.mark.asyncio
    async def test_handles_empty_capabilities(self):
        """Should handle agent with no capabilities"""
        registry = AgentRegistry()

        reg = AgentRegistration(
            agent_type="test",
            agent_name="TestAgent",
            version="1.0.0",
            capabilities=[],  # Empty
            tenant_id=uuid4(),
        )

        result = await registry.register_agent(reg)

        assert result is not None
        assert result.capabilities == []


# ============================================================================
# TEST SUITE 10: Validation
# ============================================================================


class TestValidation:
    """Test input validation"""

    @pytest.mark.asyncio
    async def test_requires_agent_type(self):
        """Should require agent_type"""
        registry = AgentRegistry()

        try:
            reg = AgentRegistration(
                agent_type="",  # Empty
                agent_name="TestAgent",
                version="1.0.0",
                capabilities=["test"],
                tenant_id=uuid4(),
            )
            await registry.register_agent(reg)
            assert False, "Should have raised validation error"
        except (ValueError, TypeError):
            pass  # Expected

    @pytest.mark.asyncio
    async def test_requires_tenant_id(self):
        """Should require tenant_id"""
        registry = AgentRegistry()

        try:
            reg = AgentRegistration(
                agent_type="test",
                agent_name="TestAgent",
                version="1.0.0",
                capabilities=["test"],
                tenant_id=None,  # Missing
            )
            await registry.register_agent(reg)
            assert False, "Should have raised validation error"
        except (ValueError, TypeError):
            pass  # Expected

    @pytest.mark.asyncio
    async def test_requires_version(self):
        """Should require version"""
        registry = AgentRegistry()

        try:
            reg = AgentRegistration(
                agent_type="test",
                agent_name="TestAgent",
                version="",  # Empty
                capabilities=["test"],
                tenant_id=uuid4(),
            )
            await registry.register_agent(reg)
            assert False, "Should have raised validation error"
        except (ValueError, TypeError):
            pass  # Expected
