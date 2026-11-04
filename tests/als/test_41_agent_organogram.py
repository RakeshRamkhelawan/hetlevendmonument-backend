"""
Test 41-Agent Organogram Implementation

Tests for the complete organism registry:
- 1 Chief Orchestrator
- 40 Department Agents across 10 departments
"""

import pytest

from src.core.als.agents import AgentPriority, OrganismRegistry, get_organism_registry
from src.core.als.agents.departments import (
    AgentTechnology,
    DataQualitySentinelAgent,
    DepartmentAgent,
    DepartmentType,
    GDPRPrivacyGuardAgent,
    InventoryForecasterAgent,
    SentimentSupportAgent,
    TechnicalArchitectAgent,
    ThreatHunterAgent,
)


class TestOrganismRegistry:
    """Test the OrganismRegistry."""

    def test_registry_singleton(self):
        """Test that registry follows singleton pattern."""
        reg1 = get_organism_registry()
        reg2 = get_organism_registry()
        assert reg1 is reg2

    def test_total_agent_count(self):
        """Test that all 40 department agents are registered."""
        registry = get_organism_registry()
        stats = registry.get_stats()
        assert stats["total_agents"] == 40

    def test_department_count(self):
        """Test that all departments are covered."""
        from src.core.als.agents.departments import DepartmentType
        registry = get_organism_registry()
        stats = registry.get_stats()
        assert stats["departments"] == len(DepartmentType)

    def test_critical_agents_count(self):
        """Test that 8 critical priority agents are registered."""
        registry = get_organism_registry()
        stats = registry.get_stats()
        assert stats["critical_agents"] == 8

    def test_human_role_count(self):
        """Test that exactly 1 human role is registered."""
        registry = get_organism_registry()
        stats = registry.get_stats()
        assert stats["human_roles"] == 1

    def test_agents_per_department(self):
        """Test that each active department has exactly 4 agents."""
        registry = get_organism_registry()

        for dept in DepartmentType:
            if dept.value == "unassigned" or dept.name == "UNASSIGNED":
                continue
            agents = registry.get_department_agents(dept)
            assert len(agents) == 4, f"Department {dept.value} should have 4 agents"

    def test_critical_agents_list(self):
        """Test that all expected critical agents exist."""
        registry = get_organism_registry()
        critical = registry.list_agents(priority=AgentPriority.CRITICAL)
        critical_ids = {r.agent_id for r in critical}

        expected_critical = {
            "technical_architect",
            "inventory_forecaster",
            "fraud_detector",
            "threat_hunter",
            "gdpr_privacy_guard",
            "sentiment_support",
            "growth_lead",
            "data_quality_sentinel",
        }

        assert critical_ids == expected_critical

    def test_growth_lead_is_human_role(self):
        """Test that growth_lead is marked as human role."""
        registry = get_organism_registry()
        reg = registry.get_registration("growth_lead")
        assert reg is not None
        assert reg.human_role is True


class TestCriticalAgents:
    """Test critical agent implementations."""

    def test_technical_architect_creation(self):
        """Test Technical Architect Agent can be created."""
        registry = get_organism_registry()
        agent = registry.create_agent("technical_architect", tenant_id=1)

        assert agent is not None
        assert isinstance(agent, TechnicalArchitectAgent)
        assert agent.department == DepartmentType.PRODUCT_INNOVATION
        assert agent.technology == AgentTechnology.LLM
        assert agent.priority == "critical"

    def test_inventory_forecaster_creation(self):
        """Test Inventory Forecaster Agent can be created."""
        registry = get_organism_registry()
        agent = registry.create_agent("inventory_forecaster", tenant_id=1)

        assert agent is not None
        assert isinstance(agent, InventoryForecasterAgent)
        assert agent.department == DepartmentType.OPERATIONS_SUPPLY_CHAIN
        assert agent.technology == AgentTechnology.ML
        assert agent.priority == "critical"

    def test_threat_hunter_creation(self):
        """Test Threat Hunter Agent can be created."""
        registry = get_organism_registry()
        agent = registry.create_agent("threat_hunter", tenant_id=1)

        assert agent is not None
        assert isinstance(agent, ThreatHunterAgent)
        assert agent.department == DepartmentType.IT_SECURITY
        assert agent.technology == AgentTechnology.ML
        assert agent.priority == "critical"

    def test_gdpr_privacy_guard_creation(self):
        """Test GDPR Privacy Guard Agent can be created."""
        registry = get_organism_registry()
        agent = registry.create_agent("gdpr_privacy_guard", tenant_id=1)

        assert agent is not None
        assert isinstance(agent, GDPRPrivacyGuardAgent)
        assert agent.department == DepartmentType.LEGAL_COMPLIANCE
        assert agent.technology == AgentTechnology.LLM
        assert agent.priority == "critical"

    def test_sentiment_support_creation(self):
        """Test Sentiment & Support Agent can be created."""
        registry = get_organism_registry()
        agent = registry.create_agent("sentiment_support", tenant_id=1)

        assert agent is not None
        assert isinstance(agent, SentimentSupportAgent)
        assert agent.department == DepartmentType.CUSTOMER_EXPERIENCE
        assert agent.technology == AgentTechnology.HYBRID
        assert agent.priority == "critical"

    def test_data_quality_sentinel_creation(self):
        """Test Data Quality Sentinel Agent can be created."""
        registry = get_organism_registry()
        agent = registry.create_agent("data_quality_sentinel", tenant_id=1)

        assert agent is not None
        assert isinstance(agent, DataQualitySentinelAgent)
        assert agent.department == DepartmentType.DATA_AI_GOVERNANCE
        assert agent.technology == AgentTechnology.ML
        assert agent.priority == "critical"


class TestAgentTechnologyDistribution:
    """Test agent technology type distribution."""

    def test_ml_agents_count(self):
        """Test that ML agents are majority."""
        registry = get_organism_registry()
        ml_agents = registry.list_agents(technology=AgentTechnology.ML)
        assert len(ml_agents) == 26

    def test_llm_agents_count(self):
        """Test LLM agents count."""
        registry = get_organism_registry()
        llm_agents = registry.list_agents(technology=AgentTechnology.LLM)
        assert len(llm_agents) == 12

    def test_vision_agents_count(self):
        """Test Vision agents count."""
        registry = get_organism_registry()
        vision_agents = registry.list_agents(technology=AgentTechnology.VISION)
        assert len(vision_agents) == 1

    def test_hybrid_agents_count(self):
        """Test Hybrid agents count."""
        registry = get_organism_registry()
        hybrid_agents = registry.list_agents(technology=AgentTechnology.HYBRID)
        assert len(hybrid_agents) == 1


class TestChiefOrchestrator:
    """Test Chief Orchestrator integration."""

    def test_chief_orchestrator_creation(self):
        """Test Chief Orchestrator can be created."""
        from unittest.mock import MagicMock

        registry = get_organism_registry()
        mock_signal_bus = MagicMock()
        chief = registry.create_chief_orchestrator(tenant_id=1, signal_bus=mock_signal_bus)

        assert chief is not None
        assert chief.tenant_id == 1
        assert chief.agent_id == "chief_orchestrator"

    def test_chief_in_stats(self):
        """Test Chief Orchestrator appears in stats."""
        from unittest.mock import MagicMock

        registry = get_organism_registry()
        mock_signal_bus = MagicMock()
        registry.create_chief_orchestrator(tenant_id=1, signal_bus=mock_signal_bus)
        stats = registry.get_stats()

        assert stats["chief_orchestrator"] is True


class TestAgentOODA:
    """Test that agents implement OODA loop."""

    @pytest.mark.asyncio
    async def test_technical_architect_ooda(self):
        """Test Technical Architect OODA methods."""
        registry = get_organism_registry()
        agent = registry.create_agent("technical_architect", tenant_id=1)

        from src.core.als.infrastructure.signal_bus import Signal, SignalTier

        signal = Signal(
            tenant_id=1,
            source_agent_id="test",
            target_agent_ids=["technical_architect"],
            tier=SignalTier.COGNITIVE,
            payload={"requirements": {"microservices": True}},
        )

        # Test observe
        observation = await agent.observe(signal)
        assert observation["department"] == "product_innovation"

        # Test orient
        orientation = await agent.orient(observation)
        assert "complexity_score" in orientation

        # Test decide
        decision = await agent.decide(orientation)
        assert isinstance(decision, str)

        # Test act
        result = await agent.act(decision)
        assert result.success is True
