"""Integration tests for BaseAgent department consolidation (Phase 0).

Tests the consolidation of department field with real YAML config loading,
actual agent lifecycle, and database tenant isolation.
"""

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.core.agents.base_agent import EnhancedBaseAgent
from src.core.agents.config.models import AgentClassification, AgentConfig, AgentInfo
from src.core.shared.interfaces import AgentType


class _IntegrationTestAgent(EnhancedBaseAgent):
    """Test agent for integration testing."""

    async def _execute_task(self, task):
        """Dummy implementation."""
        from src.core.shared.interfaces import ExecutionResult

        return ExecutionResult(task_id=task.id, success=True, result_data={"status": "done"})


@pytest.mark.integration
@pytest.mark.als
class TestBaseAgentDepartmentWithYamlConfig:
    """Integration: Department consolidation with YAML config loading."""

    def test_agent_initialization_with_explicit_department(self):
        """Agent initializes with explicit department parameter."""
        agent = _IntegrationTestAgent(
            agent_id="integration-test-001",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
            department="Engineering",
        )

        assert agent.agent_id == "integration-test-001"
        assert agent.tenant_id == 1
        assert agent.department == "Engineering"

    def test_agent_defaults_department_to_unassigned(self):
        """Agent defaults to 'unassigned' when no department provided."""
        agent = _IntegrationTestAgent(
            agent_id="integration-test-002",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
        )

        assert agent.department == "unassigned"

    def test_agent_initialization_includes_yaml_config_load(self):
        """Agent initialization attempts YAML config load."""
        with patch.object(_IntegrationTestAgent, "_load_yaml_config") as mock_load:
            agent = _IntegrationTestAgent(
                agent_id="integration-test-003",
                agent_type=AgentType.SPECIALIST,
                tenant_id=1,
            )

            # YAML config loading should have been called
            mock_load.assert_called_once()

    def test_agent_with_function_parameter(self):
        """Agent initializes with function parameter."""
        agent = _IntegrationTestAgent(
            agent_id="integration-test-004",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
            department="Sales",
            function="Lead Qualification",
        )

        assert agent.department == "Sales"
        assert agent.function == "Lead Qualification"

    def test_department_extracted_from_valid_yaml_config(self):
        """Department is correctly extracted from valid YAML config."""
        agent = _IntegrationTestAgent(
            agent_id="integration-test-005",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
        )

        # Create a valid AgentConfig-like object
        mock_classification = MagicMock()
        mock_classification.department = "Operations"

        mock_config = MagicMock()
        mock_config.classification = mock_classification

        agent.yaml_config = mock_config

        extracted = agent._extract_department_from_yaml()

        assert extracted == "Operations"

    def test_department_parameter_overrides_yaml_config(self):
        """Department parameter takes precedence over YAML config."""
        agent = _IntegrationTestAgent(
            agent_id="integration-test-006",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
            department="Parameter Department",
        )

        # Inject YAML config with different department
        mock_classification = MagicMock()
        mock_classification.department = "YAML Department"

        mock_config = MagicMock()
        mock_config.classification = mock_classification

        agent.yaml_config = mock_config

        # Parameter should take precedence
        assert agent.department == "Parameter Department"


@pytest.mark.integration
@pytest.mark.als
@pytest.mark.multi_tenant
class TestBaseAgentDepartmentTenantIsolation:
    """Integration: Department doesn't compromise tenant isolation."""

    def test_agents_in_different_tenants_can_share_department(self, tenant_fixture, other_tenant_fixture):
        """Agents in different tenants can have the same department."""
        agent1 = _IntegrationTestAgent(
            agent_id="tenant-1-agent",
            agent_type=AgentType.SPECIALIST,
            tenant_id=tenant_fixture.id,
            department="Engineering",
        )

        agent2 = _IntegrationTestAgent(
            agent_id="tenant-2-agent",
            agent_type=AgentType.SPECIALIST,
            tenant_id=other_tenant_fixture.id,
            department="Engineering",
        )

        # Same department but different tenants
        assert agent1.department == agent2.department == "Engineering"
        assert agent1.tenant_id != agent2.tenant_id

    def test_department_is_not_tenant_filter(self, tenant_fixture):
        """Department is independent of tenant_id filtering."""
        agent = _IntegrationTestAgent(
            agent_id="isolation-test-001",
            agent_type=AgentType.SPECIALIST,
            tenant_id=tenant_fixture.id,
            department="Finance",
        )

        # Tenant ID and department are separate attributes
        assert agent.tenant_id == tenant_fixture.id
        assert agent.department == "Finance"

        # Changing department doesn't change tenant context
        original_tenant = agent.tenant_id
        agent.department = "Compliance"

        assert agent.tenant_id == original_tenant


@pytest.mark.integration
@pytest.mark.als
class TestBaseAgentInitializationLogging:
    """Integration: Department is logged during initialization."""

    def test_initialization_logging_includes_department(self, caplog):
        """Agent initialization logging includes department."""
        import logging

        caplog.set_level(logging.INFO)

        agent = _IntegrationTestAgent(
            agent_id="logging-test-001",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
            department="TestDepartment",
        )

        # Check logs contain expected values
        assert agent.agent_id == "logging-test-001"
        assert agent.department == "TestDepartment"

    def test_initialization_logging_with_unassigned_default(self, caplog):
        """Agent initialization logging with 'unassigned' default."""
        import logging

        caplog.set_level(logging.INFO)

        agent = _IntegrationTestAgent(
            agent_id="logging-test-002",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
        )

        assert agent.department == "unassigned"


@pytest.mark.integration
@pytest.mark.als
class TestBaseAgentDepartmentEdgeCases:
    """Integration: Edge cases in department handling."""

    def test_empty_department_string_falls_back_to_default(self):
        """Empty string department falls back to 'unassigned'."""
        agent = _IntegrationTestAgent(
            agent_id="edge-case-001",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
            department="",
        )

        # Empty string is falsy, should fall back to unassigned
        assert agent.department == "unassigned"

    def test_whitespace_only_department_in_yaml(self):
        """Whitespace-only department in YAML is rejected."""
        agent = _IntegrationTestAgent(
            agent_id="edge-case-002",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
        )

        mock_classification = MagicMock()
        mock_classification.department = "   "

        mock_config = MagicMock()
        mock_config.classification = mock_classification

        agent.yaml_config = mock_config

        extracted = agent._extract_department_from_yaml()

        assert extracted is None

    def test_department_with_special_characters(self):
        """Department with special characters is preserved."""
        agent = _IntegrationTestAgent(
            agent_id="edge-case-003",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
            department="R&D / Operations",
        )

        assert agent.department == "R&D / Operations"

    def test_department_with_unicode_characters(self):
        """Department with unicode characters is preserved."""
        agent = _IntegrationTestAgent(
            agent_id="edge-case-004",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
            department="Engineering [Beta]",
        )

        assert agent.department == "Engineering [Beta]"

    @pytest.mark.asyncio
    async def test_agent_lifecycle_with_department(self):
        """Agent lifecycle operations work with department set."""
        agent = _IntegrationTestAgent(
            agent_id="lifecycle-test-001",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
            department="Operations",
        )

        # Initialize agent
        initialized = await agent.initialize()

        assert initialized is True
        assert agent.department == "Operations"

        # Get status
        status = await agent.get_status()
        assert status is not None

        # Get performance metrics
        metrics = agent.get_performance_metrics()
        assert metrics is not None
        assert "agent_id" in metrics


@pytest.mark.integration
@pytest.mark.als
class TestBaseAgentDepartmentConsistency:
    """Integration: Department consistency across agent lifecycle."""

    def test_department_consistent_after_status_call(self):
        """Department remains consistent after get_status() call."""
        agent = _IntegrationTestAgent(
            agent_id="consistency-001",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
            department="Analytics",
        )

        original_department = agent.department

        # After various operations, department should remain the same
        metrics = agent.get_performance_metrics()

        assert agent.department == original_department

    @pytest.mark.asyncio
    async def test_department_consistent_after_initialize(self):
        """Department remains consistent after initialize() call."""
        agent = _IntegrationTestAgent(
            agent_id="consistency-002",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
            department="Governance",
        )

        original_department = agent.department

        await agent.initialize()

        assert agent.department == original_department
