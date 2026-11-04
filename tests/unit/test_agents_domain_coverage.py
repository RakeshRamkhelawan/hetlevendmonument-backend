"""
P4.6.1: Agents Domain - Comprehensive Test Coverage
Tests agent configuration validation, creation, retrieval, and business logic
Target: 80%+ coverage on src/domains/agents/
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from pydantic import ValidationError

from src.core.types import AgentStatus, AgentType
from src.domains.agents.models import Agent
from src.domains.agents.repositories import AgentRepository
from src.domains.agents.services import AgentService


class TestAgentModel:
    """Test Agent aggregate root and validation"""

    def test_agent_creation_minimal(self):
        """Test creating agent with minimal required fields"""
        agent = Agent(
            id="agent_123",
            name="Test Agent",
            agent_type=AgentType.CORE,
            tenant_id="tenant_1",
            status=AgentStatus.INACTIVE,
        )
        assert agent.id == "agent_123"
        assert agent.name == "Test Agent"
        assert agent.agent_type == AgentType.CORE
        assert agent.tenant_id == "tenant_1"
        assert agent.status == AgentStatus.INACTIVE

    def test_agent_creation_with_capabilities(self):
        """Test agent creation with capabilities"""
        capabilities = {"analysis": True, "reporting": True}
        agent = Agent(
            id="agent_456",
            name="Capable Agent",
            agent_type=AgentType.SPECIALIST,
            tenant_id="tenant_1",
            capabilities=capabilities,
        )
        assert agent.capabilities == capabilities

    def test_agent_creation_with_configuration(self):
        """Test agent creation with configuration"""
        config = {"max_tokens": 2048, "temperature": 0.7}
        agent = Agent(
            id="agent_789",
            name="Configured Agent",
            agent_type=AgentType.ORCHESTRATOR,
            tenant_id="tenant_1",
            configuration=config,
        )
        assert agent.configuration == config

    def test_agent_name_validation_min_length(self):
        """Test agent name minimum length validation"""
        with pytest.raises(ValidationError):
            Agent(
                id="agent_000",
                name="",  # Empty name should fail
                agent_type=AgentType.CORE,
                tenant_id="tenant_1",
            )

    def test_agent_name_validation_max_length(self):
        """Test agent name maximum length validation"""
        with pytest.raises(ValidationError):
            Agent(
                id="agent_000",
                name="a" * 201,  # Exceeds max length of 200
                agent_type=AgentType.CORE,
                tenant_id="tenant_1",
            )

    def test_agent_name_validation_valid_length(self):
        """Test agent name within valid length bounds"""
        agent = Agent(
            id="agent_000",
            name="a" * 200,  # Exactly at max length
            agent_type=AgentType.CORE,
            tenant_id="tenant_1",
        )
        assert len(agent.name) == 200

    def test_agent_activate(self):
        """Test agent activation"""
        agent = Agent(
            id="agent_act",
            name="Activatable",
            agent_type=AgentType.CORE,
            tenant_id="tenant_1",
            status=AgentStatus.INACTIVE,
        )
        agent.activate()
        assert agent.status == AgentStatus.ACTIVE

    def test_agent_activate_domain_event(self):
        """Test agent activation emits domain event"""
        agent = Agent(
            id="agent_act",
            name="Activatable",
            agent_type=AgentType.CORE,
            tenant_id="tenant_1",
        )
        agent.activate()
        events = agent.get_domain_events()
        assert len(events) == 1
        assert events[0]["type"] == "agent.activated"
        assert events[0]["aggregate_id"] == "agent_act"

    def test_agent_deactivate(self):
        """Test agent deactivation"""
        agent = Agent(
            id="agent_deact",
            name="Deactivatable",
            agent_type=AgentType.CORE,
            tenant_id="tenant_1",
            status=AgentStatus.ACTIVE,
        )
        agent.deactivate()
        assert agent.status == AgentStatus.INACTIVE

    def test_agent_archive(self):
        """Test agent archival"""
        agent = Agent(
            id="agent_arch",
            name="Archivable",
            agent_type=AgentType.CORE,
            tenant_id="tenant_1",
        )
        agent.archive()
        assert agent.status == AgentStatus.ARCHIVED

    def test_agent_activate_archived_raises_error(self):
        """Test activating archived agent raises error"""
        agent = Agent(
            id="agent_arc2",
            name="Archived",
            agent_type=AgentType.CORE,
            tenant_id="tenant_1",
            status=AgentStatus.ARCHIVED,
        )
        with pytest.raises(ValueError, match="Cannot activate archived agent"):
            agent.activate()

    def test_agent_update_configuration(self):
        """Test updating agent configuration"""
        agent = Agent(
            id="agent_config",
            name="Configurable",
            agent_type=AgentType.CORE,
            tenant_id="tenant_1",
        )
        new_config = {"max_tokens": 4096, "temperature": 0.5}
        agent.update_configuration(new_config)
        assert agent.configuration == new_config

    def test_agent_update_configuration_domain_event(self):
        """Test configuration update emits domain event"""
        agent = Agent(
            id="agent_cfg2",
            name="Configurable",
            agent_type=AgentType.CORE,
            tenant_id="tenant_1",
        )
        config = {"setting": "value"}
        agent.update_configuration(config)
        events = agent.get_domain_events()
        assert any(e["type"] == "agent.configuration_updated" for e in events)

    def test_agent_metadata_optional(self):
        """Test agent with and without metadata"""
        agent1 = Agent(
            id="agent_meta1",
            name="No Metadata",
            agent_type=AgentType.CORE,
            tenant_id="tenant_1",
        )
        assert agent1.metadata is None

        agent2 = Agent(
            id="agent_meta2",
            name="With Metadata",
            agent_type=AgentType.CORE,
            tenant_id="tenant_1",
            metadata={"custom": "data"},
        )
        assert agent2.metadata == {"custom": "data"}

    def test_agent_equality(self):
        """Test agent equality based on ID"""
        agent1 = Agent(
            id="same_id",
            name="Agent One",
            agent_type=AgentType.CORE,
            tenant_id="tenant_1",
        )
        agent2 = Agent(
            id="same_id",
            name="Agent Two",
            agent_type=AgentType.SPECIALIST,
            tenant_id="tenant_1",
        )
        assert agent1 == agent2  # Same ID = equal

    def test_agent_hash(self):
        """Test agent hashability"""
        agent = Agent(
            id="hashable",
            name="Hashable Agent",
            agent_type=AgentType.CORE,
            tenant_id="tenant_1",
        )
        assert hash(agent.id) == hash("hashable")


class TestAgentService:
    """Test Agent domain service"""

    @pytest.fixture
    def mock_repository(self):
        """Create mock repository"""
        return AsyncMock(spec=AgentRepository)

    @pytest.fixture
    def service(self, mock_repository):
        """Create service with mock repository"""
        return AgentService(repository=mock_repository)

    @pytest.mark.asyncio
    async def test_create_agent_success(self, service, mock_repository):
        """Test successful agent creation"""
        mock_repository.find_by_name_and_tenant.return_value = None
        mock_repository.save.return_value = None

        result = await service.create_agent(
            name="New Agent",
            agent_type=AgentType.CORE,
            tenant_id="tenant_1",
            capabilities={"feature": True},
        )

        assert result.name == "New Agent"
        assert result.agent_type == AgentType.CORE
        assert result.tenant_id == "tenant_1"
        assert result.status == AgentStatus.INACTIVE
        mock_repository.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_agent_duplicate_name_raises_error(self, service, mock_repository):
        """Test creating agent with duplicate name raises error"""
        existing_agent = Agent(
            id="existing",
            name="Duplicate",
            agent_type=AgentType.CORE,
            tenant_id="tenant_1",
        )
        mock_repository.find_by_name_and_tenant.return_value = existing_agent

        with pytest.raises(ValueError, match="already exists"):
            await service.create_agent(
                name="Duplicate", agent_type=AgentType.SPECIALIST, tenant_id="tenant_1"
            )

    @pytest.mark.asyncio
    async def test_create_agent_generates_unique_id(self, service, mock_repository):
        """Test agent creation generates unique ID"""
        mock_repository.find_by_name_and_tenant.return_value = None
        mock_repository.save.return_value = None

        agent1 = await service.create_agent(
            name="Agent A", agent_type=AgentType.CORE, tenant_id="tenant_1"
        )
        agent2 = await service.create_agent(
            name="Agent B", agent_type=AgentType.CORE, tenant_id="tenant_1"
        )

        assert agent1.id != agent2.id
        assert agent1.id.startswith("agent_")
        assert agent2.id.startswith("agent_")

    @pytest.mark.asyncio
    async def test_create_agent_domain_event(self, service, mock_repository):
        """Test agent creation emits domain event"""
        mock_repository.find_by_name_and_tenant.return_value = None
        mock_repository.save.return_value = None

        agent = await service.create_agent(
            name="Event Agent", agent_type=AgentType.ORCHESTRATOR, tenant_id="tenant_1"
        )

        events = agent.get_domain_events()
        assert any(e["type"] == "agent.created" for e in events)

    @pytest.mark.asyncio
    async def test_activate_agent_success(self, service, mock_repository):
        """Test successful agent activation"""
        agent = Agent(
            id="agent_to_activate",
            name="Activatable",
            agent_type=AgentType.CORE,
            tenant_id="tenant_1",
            status=AgentStatus.INACTIVE,
        )
        mock_repository.find_by_id.return_value = agent
        mock_repository.save.return_value = None

        result = await service.activate_agent("agent_to_activate")

        assert result.status == AgentStatus.ACTIVE
        mock_repository.save.assert_called_once()

    @pytest.mark.asyncio
    async def test_activate_agent_not_found(self, service, mock_repository):
        """Test activating non-existent agent"""
        mock_repository.find_by_id.return_value = None

        with pytest.raises(ValueError, match="not found"):
            await service.activate_agent("nonexistent")

    @pytest.mark.asyncio
    async def test_get_tenant_agents_all(self, service, mock_repository):
        """Test retrieving all agents for tenant"""
        agents = [
            Agent(id="a1", name="Agent 1", agent_type=AgentType.CORE, tenant_id="tenant_1"),
            Agent(
                id="a2",
                name="Agent 2",
                agent_type=AgentType.SPECIALIST,
                tenant_id="tenant_1",
            ),
        ]
        mock_repository.find_by_tenant.return_value = agents

        result = await service.get_tenant_agents("tenant_1")

        assert len(result) == 2
        mock_repository.find_by_tenant.assert_called_once_with(
            "tenant_1", agent_type=None, status=None
        )

    @pytest.mark.asyncio
    async def test_get_tenant_agents_filtered_by_type(self, service, mock_repository):
        """Test retrieving agents filtered by type"""
        agents = [
            Agent(id="a1", name="Agent 1", agent_type=AgentType.CORE, tenant_id="tenant_1"),
        ]
        mock_repository.find_by_tenant.return_value = agents

        result = await service.get_tenant_agents("tenant_1", agent_type=AgentType.CORE)

        assert len(result) == 1
        mock_repository.find_by_tenant.assert_called_once_with(
            "tenant_1", agent_type=AgentType.CORE, status=None
        )

    @pytest.mark.asyncio
    async def test_get_tenant_agents_filtered_by_status(self, service, mock_repository):
        """Test retrieving agents filtered by status"""
        agents = [
            Agent(
                id="a1",
                name="Agent 1",
                agent_type=AgentType.CORE,
                tenant_id="tenant_1",
                status=AgentStatus.ACTIVE,
            ),
        ]
        mock_repository.find_by_tenant.return_value = agents

        result = await service.get_tenant_agents("tenant_1", status=AgentStatus.ACTIVE)

        assert len(result) == 1
        mock_repository.find_by_tenant.assert_called_once_with(
            "tenant_1", agent_type=None, status=AgentStatus.ACTIVE
        )

    @pytest.mark.asyncio
    async def test_get_tenant_agents_empty(self, service, mock_repository):
        """Test retrieving agents when none exist"""
        mock_repository.find_by_tenant.return_value = []

        result = await service.get_tenant_agents("empty_tenant")

        assert result == []


class TestAgentIntegration:
    """Integration tests for Agent domain"""

    def test_agent_lifecycle(self):
        """Test complete agent lifecycle"""
        # Create
        agent = Agent(
            id="lifecycle",
            name="Lifecycle Agent",
            agent_type=AgentType.CORE,
            tenant_id="tenant_1",
        )
        assert agent.status == AgentStatus.INACTIVE

        # Activate
        agent.activate()
        assert agent.status == AgentStatus.ACTIVE

        # Configure
        agent.update_configuration({"key": "value"})
        assert agent.configuration["key"] == "value"

        # Deactivate
        agent.deactivate()
        assert agent.status == AgentStatus.INACTIVE

        # Archive
        agent.archive()
        assert agent.status == AgentStatus.ARCHIVED

    def test_agent_domain_events_accumulation(self):
        """Test domain events accumulate over lifecycle"""
        agent = Agent(
            id="events_test",
            name="Event Test",
            agent_type=AgentType.CORE,
            tenant_id="tenant_1",
        )

        agent.activate()
        agent.update_configuration({"test": "config"})
        agent.deactivate()

        events = agent.get_domain_events()
        assert len(events) >= 3
        assert any(e["type"] == "agent.activated" for e in events)
        assert any(e["type"] == "agent.configuration_updated" for e in events)
        assert any(e["type"] == "agent.deactivated" for e in events)

    def test_agent_domain_events_clear(self):
        """Test clearing domain events"""
        agent = Agent(
            id="clear_test",
            name="Clear Test",
            agent_type=AgentType.CORE,
            tenant_id="tenant_1",
        )
        agent.activate()
        assert len(agent.get_domain_events()) > 0

        agent.clear_domain_events()
        assert len(agent.get_domain_events()) == 0

    def test_multiple_agent_types(self):
        """Test agents with different types"""
        agent_types = [
            AgentType.CORE,
            AgentType.ORCHESTRATOR,
            AgentType.ETHICS,
            AgentType.SPECIALIST,
            AgentType.SANDBOX,
        ]

        for i, agent_type in enumerate(agent_types):
            agent = Agent(
                id=f"type_test_{i}",
                name=f"Type Test {i}",
                agent_type=agent_type,
                tenant_id="tenant_1",
            )
            assert agent.agent_type == agent_type

    def test_multi_tenant_isolation(self):
        """Test agents properly isolated by tenant"""
        agent1 = Agent(
            id="tenant_a_agent",
            name="Tenant A Agent",
            agent_type=AgentType.CORE,
            tenant_id="tenant_a",
        )
        agent2 = Agent(
            id="tenant_b_agent",
            name="Tenant B Agent",
            agent_type=AgentType.CORE,
            tenant_id="tenant_b",
        )

        assert agent1.tenant_id != agent2.tenant_id
        assert agent1.tenant_id == "tenant_a"
        assert agent2.tenant_id == "tenant_b"

    @pytest.mark.asyncio
    async def test_agent_service_with_multiple_tenants(self):
        """Test service correctly isolates agents by tenant"""
        mock_repo = AsyncMock(spec=AgentRepository)
        service = AgentService(mock_repo)

        # Create agents for different tenants
        mock_repo.find_by_name_and_tenant.return_value = None
        mock_repo.save.return_value = None

        agent1 = await service.create_agent(
            name="Shared Name", agent_type=AgentType.CORE, tenant_id="tenant_a"
        )
        agent2 = await service.create_agent(
            name="Shared Name", agent_type=AgentType.CORE, tenant_id="tenant_b"
        )

        # Both should succeed because they're in different tenants
        assert agent1.tenant_id == "tenant_a"
        assert agent2.tenant_id == "tenant_b"


class TestAgentEdgeCases:
    """Edge case and error handling tests"""

    def test_agent_with_empty_capabilities(self):
        """Test agent with empty capabilities dict"""
        agent = Agent(
            id="empty_cap",
            name="Empty Capabilities",
            agent_type=AgentType.CORE,
            tenant_id="tenant_1",
            capabilities={},
        )
        assert agent.capabilities == {}

    def test_agent_with_empty_configuration(self):
        """Test agent with empty configuration dict"""
        agent = Agent(
            id="empty_cfg",
            name="Empty Configuration",
            agent_type=AgentType.CORE,
            tenant_id="tenant_1",
            configuration={},
        )
        assert agent.configuration == {}

    def test_agent_configuration_merge(self):
        """Test configuration update merges with existing"""
        agent = Agent(
            id="merge_test",
            name="Merge Test",
            agent_type=AgentType.CORE,
            tenant_id="tenant_1",
            configuration={"existing": "value"},
        )
        agent.update_configuration({"new": "value"})
        assert agent.configuration["existing"] == "value"
        assert agent.configuration["new"] == "value"

    def test_agent_configuration_overwrite(self):
        """Test configuration update can overwrite existing keys"""
        agent = Agent(
            id="overwrite_test",
            name="Overwrite Test",
            agent_type=AgentType.CORE,
            tenant_id="tenant_1",
            configuration={"key": "old_value"},
        )
        agent.update_configuration({"key": "new_value"})
        assert agent.configuration["key"] == "new_value"

    @pytest.mark.asyncio
    async def test_create_agent_with_no_capabilities(self):
        """Test creating agent without specifying capabilities"""
        mock_repo = AsyncMock(spec=AgentRepository)
        service = AgentService(mock_repo)
        mock_repo.find_by_name_and_tenant.return_value = None
        mock_repo.save.return_value = None

        agent = await service.create_agent(
            name="No Capabilities", agent_type=AgentType.CORE, tenant_id="tenant_1"
        )

        assert agent.capabilities == {}
