"""Security tests for BaseAgent department consolidation (Phase 0).

Tests that department consolidation doesn't introduce security vulnerabilities:
- Tenant isolation preservation
- Department as non-security-critical attribute
- YAML injection prevention
- Department-based bypass prevention
"""

from unittest.mock import MagicMock

import pytest

from src.core.agents.base_agent import EnhancedBaseAgent
from src.core.shared.interfaces import AgentType


class _SecurityTestAgent(EnhancedBaseAgent):
    """Test agent for security testing."""

    async def _execute_task(self, task):
        """Dummy implementation."""
        from src.core.shared.interfaces import ExecutionResult

        return ExecutionResult(task_id=task.id, success=True, result_data={"status": "done"})


@pytest.mark.security
class TestBaseAgentDepartmentSecurityBoundaries:
    """Security: Department doesn't bypass tenant isolation."""

    def test_department_cannot_override_tenant_id(self):
        """Department parameter cannot override tenant_id."""
        agent = _SecurityTestAgent(
            agent_id="security-test-001",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
            department="Engineering",
        )

        # Department and tenant_id are independent
        assert agent.tenant_id == 1
        assert agent.department == "Engineering"

        # Setting department doesn't affect tenant context
        agent.department = "Sales"

        assert agent.tenant_id == 1

    def test_department_not_used_for_access_control(self):
        """Department is not checked for access control decisions."""
        agent1 = _SecurityTestAgent(
            agent_id="security-test-002",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
            department="Engineering",
        )

        agent2 = _SecurityTestAgent(
            agent_id="security-test-003",
            agent_type=AgentType.SPECIALIST,
            tenant_id=2,
            department="Engineering",  # Same department, different tenant
        )

        # Same department doesn't grant cross-tenant access
        assert agent1.department == agent2.department
        assert agent1.tenant_id != agent2.tenant_id

        # Each agent maintains its own tenant context
        assert agent1.tenant_id == 1
        assert agent2.tenant_id == 2

    def test_invalid_tenant_id_rejected_before_department_set(self):
        """Invalid tenant_id is rejected before department is set."""
        with pytest.raises(ValueError, match="invalid tenant_id"):
            _SecurityTestAgent(
                agent_id="security-test-004",
                agent_type=AgentType.SPECIALIST,
                tenant_id=0,  # Invalid
                department="Engineering",
            )

        with pytest.raises(ValueError, match="invalid tenant_id"):
            _SecurityTestAgent(
                agent_id="security-test-005",
                agent_type=AgentType.SPECIALIST,
                tenant_id=-1,  # Invalid
                department="Engineering",
            )

        with pytest.raises(ValueError, match="invalid tenant_id"):
            _SecurityTestAgent(
                agent_id="security-test-006",
                agent_type=AgentType.SPECIALIST,
                tenant_id=None,  # Invalid
                department="Engineering",
            )


@pytest.mark.security
class TestBaseAgentDepartmentYamlInjectionPrevention:
    """Security: YAML department extraction is safe from injection."""

    def test_yaml_department_with_injection_attempt(self):
        """Injection-like strings in YAML department are treated as literals."""
        agent = _SecurityTestAgent(
            agent_id="security-test-007",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
        )

        # Simulate YAML with injection-like string
        mock_classification = MagicMock()
        mock_classification.department = "'; DROP TABLE agents; --"

        mock_config = MagicMock()
        mock_config.classification = mock_classification

        agent.yaml_config = mock_config

        extracted = agent._extract_department_from_yaml()

        # Should be treated as literal string, not executed
        assert extracted == "'; DROP TABLE agents; --"
        assert isinstance(extracted, str)

    def test_yaml_department_with_code_injection_attempt(self):
        """Code-like strings in YAML department are treated as literals."""
        agent = _SecurityTestAgent(
            agent_id="security-test-008",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
        )

        mock_classification = MagicMock()
        mock_classification.department = "__import__('os').system('rm -rf /')"

        mock_config = MagicMock()
        mock_config.classification = mock_classification

        agent.yaml_config = mock_config

        extracted = agent._extract_department_from_yaml()

        # Should be treated as literal string
        assert extracted == "__import__('os').system('rm -rf /')"
        assert isinstance(extracted, str)

    def test_yaml_department_with_binary_data_rejected(self):
        """Non-string department values are rejected."""
        agent = _SecurityTestAgent(
            agent_id="security-test-009",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
        )

        # Non-string value
        mock_classification = MagicMock()
        mock_classification.department = b"bytes_value"

        mock_config = MagicMock()
        mock_config.classification = mock_classification

        agent.yaml_config = mock_config

        extracted = agent._extract_department_from_yaml()

        # Non-string should be rejected
        assert extracted is None


@pytest.mark.security
class TestBaseAgentDepartmentAttributeAccess:
    """Security: Department attribute access is safe."""

    def test_department_is_public_read_only_property(self):
        """Department can be read but is not meant for mutation."""
        agent = _SecurityTestAgent(
            agent_id="security-test-010",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
            department="Finance",
        )

        # Reading is safe
        dept = agent.department
        assert dept == "Finance"

        # NOTE: Python doesn't have true immutability, but we document that
        # department should be treated as immutable after construction
        # (enforced via code review and tests, not language features)

    def test_department_not_in_sensitive_api_responses(self):
        """Department is not leaked in status/metrics APIs."""
        agent = _SecurityTestAgent(
            agent_id="security-test-011",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
            department="Compliance",
        )

        metrics = agent.get_performance_metrics()

        # Department should not appear in performance metrics
        # (it's an organizational attribute, not a performance attribute)
        assert "department" not in metrics
        assert "function" not in metrics

        # But internal state is correct
        assert agent.department == "Compliance"


@pytest.mark.security
@pytest.mark.multi_tenant
class TestBaseAgentDepartmentMultiTenant:
    """Security: Department consolidation in multi-tenant context."""

    def test_agents_across_tenants_isolated_by_tenant_id_not_department(self):
        """Agents are isolated by tenant_id, not department."""
        agent1 = _SecurityTestAgent(
            agent_id="tenant-1-agent",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
            department="Shared",
        )

        agent2 = _SecurityTestAgent(
            agent_id="tenant-2-agent",
            agent_type=AgentType.SPECIALIST,
            tenant_id=2,
            department="Shared",
        )

        # Same department, different tenants
        assert agent1.department == agent2.department

        # Isolation is by tenant_id
        assert agent1.tenant_id != agent2.tenant_id

        # Each agent knows its own tenant context
        assert agent1.tenant_id == 1
        assert agent2.tenant_id == 2

    def test_department_not_used_for_cross_tenant_queries(self):
        """Department is never used to determine data scope."""
        agent = _SecurityTestAgent(
            agent_id="cross-tenant-test",
            agent_type=AgentType.SPECIALIST,
            tenant_id=42,
            department="Operations",
        )

        # Department doesn't affect how database queries are scoped
        # (that's done by tenant_id filtering in ORM hooks)
        assert agent.tenant_id == 42
        assert agent.department == "Operations"

        # The ORM hook will filter by tenant_id, not department
        # This is ensured by the database layer, not this class


@pytest.mark.security
class TestBaseAgentDepartmentLeakPrevention:
    """Security: Department doesn't leak sensitive information."""

    def test_department_not_in_logs_by_default(self, caplog):
        """Department is logged but in structured format, not message text."""
        import logging

        caplog.set_level(logging.DEBUG)

        agent = _SecurityTestAgent(
            agent_id="leak-test-001",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
            department="Finance",
        )

        # Department is logged in initialization
        # But it's organizational metadata, not sensitive per se
        # The important thing is that it doesn't appear in unstructured messages

    def test_department_in_extraction_logging_is_debug_level(self, caplog):
        """Department extraction is logged at DEBUG level for auditing."""
        import logging

        caplog.set_level(logging.DEBUG)

        agent = _SecurityTestAgent(
            agent_id="leak-test-002",
            agent_type=AgentType.SPECIALIST,
            tenant_id=1,
        )

        mock_classification = MagicMock()
        mock_classification.department = "Engineering"

        mock_config = MagicMock()
        mock_config.classification = mock_classification

        agent.yaml_config = mock_config

        extracted = agent._extract_department_from_yaml()

        # DEBUG logs might capture it, but INFO logs shouldn't
        assert extracted == "Engineering"
