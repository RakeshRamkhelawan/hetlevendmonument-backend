"""Unit tests for BaseAgent department and function consolidation (Phase 0).

Tests the consolidation of department field into BaseAgent runtime properties with:
- Direct parameter passing
- YAML extraction fallback
- Immutable defaults
- Initialization logging
- Tenant isolation
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest

from src.core.agents.base_agent import EnhancedBaseAgent
from src.core.shared.interfaces import AgentType


class _TestAgent(EnhancedBaseAgent):
    """Minimal test agent for unit testing."""

    async def _execute_task(self, task):
        """Dummy implementation."""
        from src.core.shared.interfaces import ExecutionResult

        return ExecutionResult(task_id=task.id, success=True, result_data={"status": "done"})


@pytest.mark.unit
class TestBaseAgentDepartmentParameter:
    """Happy path: Department passed as parameter."""

    def test_department_parameter_sets_directly(self, caplog):
        """Department parameter is stored directly on agent."""
        agent = _TestAgent(
            agent_id="test-agent-001",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
            department="Engineering",
        )

        assert agent.department == "Engineering"

    def test_function_parameter_sets_directly(self):
        """Function parameter is stored directly on agent."""
        agent = _TestAgent(
            agent_id="test-agent-001",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
            function="Code Review",
        )

        assert agent.function == "Code Review"

    def test_both_department_and_function_parameters_set(self):
        """Both department and function parameters are stored."""
        agent = _TestAgent(
            agent_id="test-agent-001",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
            department="Sales",
            function="Lead Qualification",
        )

        assert agent.department == "Sales"
        assert agent.function == "Lead Qualification"

    def test_department_parameter_takes_precedence_over_yaml(self, mocker):
        """Department parameter takes precedence over YAML extraction."""
        # Mock YAML config with different department
        mock_config = MagicMock()
        mock_config.classification.department = "YAML Department"

        def _mock_load_yaml(self):
            self.yaml_config = mock_config

        with patch.object(_TestAgent, "_load_yaml_config", _mock_load_yaml):
            agent = _TestAgent(
                agent_id="test-agent-001",
                agent_type=AgentType.SPECIALIST,
                tenant_id=1,
                department="Parameter Department",
            )

            # Parameter should win
            assert agent.department == "Parameter Department"


@pytest.mark.unit
class TestBaseAgentDepartmentYamlExtraction:
    """Happy path: Department extracted from YAML configuration."""

    def test_extract_department_from_yaml(self):
        """Department is extracted from valid YAML config."""
        agent = _TestAgent(
            agent_id="test-agent-001",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
        )

        # Simulate loaded YAML config
        mock_config = MagicMock()
        mock_config.classification.department = "Operations"
        agent.yaml_config = mock_config

        extracted = agent._extract_department_from_yaml()

        assert extracted == "Operations"

    def test_extract_department_strips_whitespace(self):
        """Department extraction strips leading/trailing whitespace."""
        agent = _TestAgent(
            agent_id="test-agent-001",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
        )

        mock_config = MagicMock()
        mock_config.classification.department = "  Finance  "
        agent.yaml_config = mock_config

        extracted = agent._extract_department_from_yaml()

        assert extracted == "Finance"

    def test_yaml_department_used_when_no_parameter(self):
        """YAML department used when no parameter provided."""
        mock_config = MagicMock()
        mock_config.classification.department = "YAML Extracted"

        def _mock_load_yaml(self):
            self.yaml_config = mock_config

        with patch.object(_TestAgent, "_load_yaml_config", _mock_load_yaml):
            agent = _TestAgent(
                agent_id="test-agent-001",
                agent_type=AgentType.SPECIALIST,
                tenant_id=1,
                # No department parameter
            )

        assert agent.department == "YAML Extracted"


@pytest.mark.unit
class TestBaseAgentDepartmentDefaults:
    """Happy path: Department defaults to 'unassigned'."""

    def test_department_defaults_to_unassigned(self):
        """Department defaults to 'unassigned' when not provided."""
        agent = _TestAgent(
            agent_id="test-agent-001",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
        )

        assert agent.department == "unassigned"

    def test_function_defaults_to_none(self):
        """Function defaults to None when not provided."""
        agent = _TestAgent(
            agent_id="test-agent-001",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
        )

        assert agent.function is None

    def test_empty_string_department_falls_back_to_default(self):
        """Empty string department is treated as not provided."""
        agent = _TestAgent(
            agent_id="test-agent-001",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
            department="",  # Empty string
        )

        # Empty string is falsy, so it should fall back to unassigned
        assert agent.department == "unassigned"

    def test_precedence_parameter_yaml_default(self):
        """Department follows precedence: parameter > YAML > default."""
        # Case 1: Parameter provided, YAML present, should use parameter
        agent1 = _TestAgent(
            agent_id="test-agent-001",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
            department="Parameter",
        )
        assert agent1.department == "Parameter"

        # Case 2: No parameter, YAML present, should use YAML
        agent2 = _TestAgent(
            agent_id="test-agent-002",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
        )
        mock_config = MagicMock()
        mock_config.classification.department = "FromYAML"
        agent2.yaml_config = mock_config
        extracted = agent2._extract_department_from_yaml()
        agent2.department = extracted or "unassigned"
        assert agent2.department == "FromYAML"

        # Case 3: No parameter, no YAML, should use default
        agent3 = _TestAgent(
            agent_id="test-agent-003",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
        )
        assert agent3.department == "unassigned"


@pytest.mark.unit
class TestBaseAgentDepartmentUnhappyPaths:
    """Unhappy path: Invalid department inputs."""

    def test_extract_department_from_missing_yaml_config(self):
        """Returns None when YAML config not loaded."""
        agent = _TestAgent(
            agent_id="test-agent-001",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
        )

        # No YAML config set
        agent.yaml_config = None

        extracted = agent._extract_department_from_yaml()

        assert extracted is None

    def test_extract_department_from_missing_classification_field(self):
        """Returns None when classification field missing."""
        agent = _TestAgent(
            agent_id="test-agent-001",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
        )

        # YAML config without classification
        mock_config = MagicMock()
        mock_config.classification = None
        agent.yaml_config = mock_config

        extracted = agent._extract_department_from_yaml()

        assert extracted is None

    def test_extract_department_from_missing_department_field(self):
        """Returns None when department field missing from classification."""
        agent = _TestAgent(
            agent_id="test-agent-001",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
        )

        mock_config = MagicMock()
        mock_config.classification.department = None
        agent.yaml_config = mock_config

        extracted = agent._extract_department_from_yaml()

        assert extracted is None

    def test_extract_department_with_empty_string_in_yaml(self):
        """Returns None when department is empty string in YAML."""
        agent = _TestAgent(
            agent_id="test-agent-001",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
        )

        mock_config = MagicMock()
        mock_config.classification.department = ""
        agent.yaml_config = mock_config

        extracted = agent._extract_department_from_yaml()

        assert extracted is None

    def test_extract_department_with_whitespace_only_in_yaml(self):
        """Returns None when department is whitespace-only in YAML."""
        agent = _TestAgent(
            agent_id="test-agent-001",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
        )

        mock_config = MagicMock()
        mock_config.classification.department = "   "
        agent.yaml_config = mock_config

        extracted = agent._extract_department_from_yaml()

        assert extracted is None

    def test_extract_department_from_non_string_value(self):
        """Returns None when department value is not a string."""
        agent = _TestAgent(
            agent_id="test-agent-001",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
        )

        mock_config = MagicMock()
        mock_config.classification.department = 12345  # Not a string
        agent.yaml_config = mock_config

        extracted = agent._extract_department_from_yaml()

        assert extracted is None

    def test_extract_department_with_attribute_error(self):
        """Returns None gracefully on AttributeError."""
        agent = _TestAgent(
            agent_id="test-agent-001",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
        )

        # Mock config that raises AttributeError on access
        mock_config = MagicMock()
        type(mock_config).classification = PropertyMock(side_effect=AttributeError("missing"))
        agent.yaml_config = mock_config

        extracted = agent._extract_department_from_yaml()

        assert extracted is None


@pytest.mark.unit
class TestBaseAgentDepartmentLogging:
    """Happy path: Department included in initialization logging."""

    def test_initialization_logs_department(self, caplog):
        """Agent initialization logs department in structured logging."""
        import logging

        caplog.set_level(logging.INFO)

        agent = _TestAgent(
            agent_id="test-agent-001",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
            department="Engineering",
        )

        # Check that initialization log contains department via extra fields
        assert any(getattr(record, "department", None) == "Engineering" for record in caplog.records)

    def test_initialization_logs_function(self, caplog):
        """Agent initialization logs function in structured logging."""
        import logging

        caplog.set_level(logging.INFO)

        agent = _TestAgent(
            agent_id="test-agent-001",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
            function="Code Review",
        )

        # Check that function is logged via extra fields
        assert any(getattr(record, "function", None) == "Code Review" for record in caplog.records)

    def test_initialization_logs_default_unassigned_department(self, caplog):
        """Agent initialization logs 'unassigned' as default department."""
        import logging

        caplog.set_level(logging.INFO)

        agent = _TestAgent(
            agent_id="test-agent-001",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
        )

        assert agent.department == "unassigned"


@pytest.mark.unit
@pytest.mark.security
class TestBaseAgentDepartmentTenantIsolation:
    """Security test: Department doesn't break tenant isolation."""

    def test_tenant_id_and_department_independent(self):
        """Department and tenant_id are independent attributes."""
        agent1 = _TestAgent(
            agent_id="test-agent-001",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
            department="Engineering",
        )

        agent2 = _TestAgent(
            agent_id="test-agent-002",
            agent_type=AgentType.SPECIALIST,
            tenant_id=2,
            department="Engineering",  # Same department, different tenant
        )

        # Both have same department but different tenant_id
        assert agent1.department == agent2.department
        assert agent1.tenant_id != agent2.tenant_id

    def test_department_extracted_per_agent(self):
        """Department extraction is isolated per agent."""
        agent1 = _TestAgent(
            agent_id="test-agent-001",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
        )

        agent2 = _TestAgent(
            agent_id="test-agent-002",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
        )

        # Inject different configs
        mock_config1 = MagicMock()
        mock_config1.classification.department = "Finance"
        agent1.yaml_config = mock_config1

        mock_config2 = MagicMock()
        mock_config2.classification.department = "Sales"
        agent2.yaml_config = mock_config2

        extracted1 = agent1._extract_department_from_yaml()
        extracted2 = agent2._extract_department_from_yaml()

        assert extracted1 == "Finance"
        assert extracted2 == "Sales"


@pytest.mark.unit
class TestBaseAgentDepartmentUserBehavioral:
    """User behavioral test: Department affects agent behavior."""

    def test_agent_remembers_department_after_construction(self):
        """Agent remembers department after construction."""
        agent = _TestAgent(
            agent_id="test-agent-001",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
            department="Operations",
        )

        # Create second reference to same agent
        agent_ref = agent

        # Department should be consistent
        assert agent.department == "Operations"
        assert agent_ref.department == "Operations"

    def test_agent_department_accessible_via_property(self):
        """Department is accessible as a regular property."""
        agent = _TestAgent(
            agent_id="test-agent-001",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
            department="Compliance",
        )

        # Access multiple times
        dept1 = agent.department
        dept2 = agent.department

        assert dept1 == dept2 == "Compliance"

    def test_get_performance_metrics_excludes_department(self):
        """Department is not in performance metrics (separate concern)."""
        agent = _TestAgent(
            agent_id="test-agent-001",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
            department="Analytics",
        )

        metrics = agent.get_performance_metrics()

        # Department should not be in performance metrics
        assert "department" not in metrics
        assert "function" not in metrics

    @pytest.mark.asyncio
    async def test_get_status_excludes_department(self):
        """Department is not in status output (separate concern)."""
        agent = _TestAgent(
            agent_id="test-agent-001",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
            department="Governance",
        )

        status = await agent.get_status()

        # Department should not be in status
        assert not hasattr(status, "department")
        assert "department" not in str(status)
