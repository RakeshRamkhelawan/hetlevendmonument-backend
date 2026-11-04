"""Task #4: Tests for department assignment validation in OversightGate.

Tests that department constraints work correctly in pre-execution governance.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, AsyncMock
from dataclasses import dataclass

from src.core.governance.oversight_gate import (
    OversightGate,
    OversightResult,
)
from src.core.governance.ai_act_classifier import AIActRiskLevel


@dataclass
class MockAuditService:
    """Mock audit service for testing."""

    logged_events: list = None

    def __post_init__(self):
        if self.logged_events is None:
            self.logged_events = []

    def log_security_event(self, event_type: str, details: dict) -> None:
        """Log security event."""
        self.logged_events.append({"event_type": event_type, "details": details})


def _make_oversight_gate(audit_service=None):
    """Build an OversightGate with optional audit service."""
    return OversightGate(policy_engine=None, audit_service=audit_service)


# =============================================================================
# Task 4a: Happy path - department validation works
# =============================================================================


@pytest.mark.governance
class TestDepartmentValidationHappyPath:
    """Happy path: department validation passes when departments match."""

    @pytest.mark.asyncio
    async def test_validation_passes_when_department_matches(self):
        """Validation passes when agent department matches required department."""
        gate = _make_oversight_gate()

        result = await gate.check(
            agent_name="finance_agent",
            agent_department="FINANCE",
            agent_specialisation="analyst",
            agent_capabilities=["data_analysis"],
            task_action="report_generation",
            task_params={"required_department": "FINANCE"},
        )

        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_validation_passes_when_no_requirement_specified(self):
        """Validation passes when task has no required_department."""
        gate = _make_oversight_gate()

        result = await gate.check(
            agent_name="any_agent",
            agent_department="FINANCE",
            agent_specialisation="analyst",
            agent_capabilities=["data_analysis"],
            task_action="report_generation",
            task_params={},  # No required_department
        )

        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_unassigned_agent_can_execute_any_department_task(self):
        """Unassigned agents are universal and can execute any department task."""
        gate = _make_oversight_gate()

        result = await gate.check(
            agent_name="universal_agent",
            agent_department="unassigned",
            agent_specialisation="general",
            agent_capabilities=["any_capability"],
            task_action="generic_task",
            task_params={"required_department": "FINANCE"},
        )

        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_unassigned_agent_lowercase_can_execute_any_department_task(self):
        """Unassigned agents work in any case variation."""
        gate = _make_oversight_gate()

        result = await gate.check(
            agent_name="universal_agent",
            agent_department="UNASSIGNED",  # Uppercase
            agent_specialisation="general",
            agent_capabilities=["any_capability"],
            task_action="generic_task",
            task_params={"required_department": "sales"},  # Lowercase requirement
        )

        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_case_insensitive_department_matching(self):
        """Department matching is case-insensitive."""
        gate = _make_oversight_gate()

        result = await gate.check(
            agent_name="finance_agent",
            agent_department="finance",  # Lowercase
            agent_specialisation="analyst",
            agent_capabilities=["data_analysis"],
            task_action="report_generation",
            task_params={"required_department": "FINANCE"},  # Uppercase requirement
        )

        assert result.allowed is True

    @pytest.mark.asyncio
    async def test_department_field_alias_support(self):
        """Task params can use 'department' as alias for 'required_department'."""
        gate = _make_oversight_gate()

        result = await gate.check(
            agent_name="finance_agent",
            agent_department="FINANCE",
            agent_specialisation="analyst",
            agent_capabilities=["data_analysis"],
            task_action="report_generation",
            task_params={"department": "FINANCE"},  # Using 'department' instead
        )

        assert result.allowed is True


# =============================================================================
# Task 4b: Unhappy paths - department validation rejects mismatches
# =============================================================================


@pytest.mark.governance
class TestDepartmentValidationUnhappyPaths:
    """Unhappy paths: department validation rejects mismatches."""

    @pytest.mark.asyncio
    async def test_validation_rejects_department_mismatch(self):
        """Validation rejects when agent department does not match required."""
        gate = _make_oversight_gate()

        result = await gate.check(
            agent_name="sales_agent",
            agent_department="SALES_MARKETING",
            agent_specialisation="specialist",
            agent_capabilities=["customer_engagement"],
            task_action="finance_report",
            task_params={"required_department": "FINANCE"},
        )

        assert result.allowed is False
        assert "Department mismatch" in result.reason
        assert "SALES_MARKETING" in result.reason
        assert "FINANCE" in result.reason

    @pytest.mark.asyncio
    async def test_mismatch_error_message_is_clear(self):
        """Error message clearly indicates the mismatch."""
        gate = _make_oversight_gate()

        result = await gate.check(
            agent_name="hr_agent",
            agent_department="HR",
            agent_specialisation="recruiter",
            agent_capabilities=["recruiting"],
            task_action="compliance_audit",
            task_params={"required_department": "LEGAL_COMPLIANCE"},
        )

        expected_message = "Department mismatch: Agent (HR) cannot execute LEGAL_COMPLIANCE task"
        assert result.reason == expected_message

    @pytest.mark.asyncio
    async def test_multiple_department_mismatches(self):
        """All department mismatches are caught (not just first agent type)."""
        gate = _make_oversight_gate()

        mismatches = [
            ("OPERATIONS", "FINANCE"),
            ("IT_SECURITY", "SALES_MARKETING"),
            ("PRODUCT_INNOVATION", "CUSTOMER_EXPERIENCE"),
            ("STRATEGY", "DATA_AI_GOVERNANCE"),
        ]

        for agent_dept, required_dept in mismatches:
            result = await gate.check(
                agent_name="test_agent",
                agent_department=agent_dept,
                agent_specialisation="test",
                agent_capabilities=["test"],
                task_action="test_action",
                task_params={"required_department": required_dept},
            )
            assert result.allowed is False, f"{agent_dept} should not match {required_dept}"

    @pytest.mark.asyncio
    async def test_mismatch_blocks_with_high_risk_level(self):
        """Department mismatch blocks execution with HIGH_RISK risk level."""
        gate = _make_oversight_gate()

        result = await gate.check(
            agent_name="sales_agent",
            agent_department="SALES_MARKETING",
            agent_specialisation="specialist",
            agent_capabilities=["customer_engagement"],
            task_action="sensitive_action",
            task_params={"required_department": "LEGAL_COMPLIANCE"},
        )

        assert result.allowed is False
        assert result.risk_level == AIActRiskLevel.HIGH_RISK
        assert result.requires_human_approval is False  # Blocked, not approval-required


# =============================================================================
# Task 4c: Audit logging - department validation attempts are logged
# =============================================================================


@pytest.mark.governance
@pytest.mark.security
class TestDepartmentValidationAuditLogging:
    """Audit logging: department validation attempts are recorded."""

    @pytest.mark.asyncio
    async def test_department_mismatch_logged_to_audit_trail(self):
        """Department mismatch is logged as security event."""
        audit_service = MockAuditService()
        gate = OversightGate(policy_engine=None, audit_service=audit_service)

        await gate.check(
            agent_name="sales_agent",
            agent_department="SALES_MARKETING",
            agent_specialisation="specialist",
            agent_capabilities=["customer_engagement"],
            task_action="finance_report",
            task_params={"required_department": "FINANCE"},
            tenant_id=42,
        )

        # Check that event was logged
        assert len(audit_service.logged_events) == 1
        event = audit_service.logged_events[0]
        assert event["event_type"] == "OVERSIGHT_DECISION"
        assert event["details"]["allowed"] is False
        assert event["details"]["department_validation"] is True
        assert event["details"]["tenant_id"] == 42

    @pytest.mark.asyncio
    async def test_successful_department_validation_not_marked_as_mismatch(self):
        """Successful validation not flagged as department_validation event."""
        audit_service = MockAuditService()
        gate = OversightGate(policy_engine=None, audit_service=audit_service)

        await gate.check(
            agent_name="finance_agent",
            agent_department="FINANCE",
            agent_specialisation="analyst",
            agent_capabilities=["data_analysis"],
            task_action="report_generation",
            task_params={"required_department": "FINANCE"},
        )

        # Check that event was logged but not as department_validation
        assert len(audit_service.logged_events) == 1
        event = audit_service.logged_events[0]
        assert event["details"]["department_validation"] is False


# =============================================================================
# Task 4d: Integration - department validation with other checks
# =============================================================================


@pytest.mark.governance
@pytest.mark.integration
class TestDepartmentValidationIntegration:
    """Integration: department validation works with other oversight checks."""

    @pytest.mark.asyncio
    async def test_department_validation_blocks_before_approval_logic(self):
        """Department validation runs early, blocks before approval checks."""
        gate = _make_oversight_gate()

        result = await gate.check(
            agent_name="sales_agent",
            agent_department="SALES_MARKETING",
            agent_specialisation="specialist",
            agent_capabilities=["customer_engagement"],
            task_action="code_generation",  # Breakthrough action
            task_params={"required_department": "FINANCE"},
        )

        # Blocked by department validation, not by breakthrough action
        assert result.allowed is False
        assert "Department mismatch" in result.reason

    @pytest.mark.asyncio
    async def test_unassigned_agent_passes_through_all_validations(self):
        """Unassigned agents pass department validation, proceed through pipeline."""
        gate = _make_oversight_gate()

        # "unassigned" agent can execute ANY department task
        result = await gate.check(
            agent_name="universal_agent",
            agent_department="unassigned",
            agent_specialisation="general",
            agent_capabilities=["any"],
            task_action="generic_action",
            task_params={"required_department": "FINANCE"},
        )

        assert result.allowed is True


# =============================================================================
# Task 4e: User behavioral tests
# =============================================================================


@pytest.mark.governance
class TestDepartmentValidationUserBehavioral:
    """User behavioral: realistic governance scenarios."""

    @pytest.mark.asyncio
    async def test_scenario_finance_agent_blocked_from_legal_task(self):
        """Scenario: Finance agent cannot execute Legal department task."""
        gate = _make_oversight_gate()

        result = await gate.check(
            agent_name="auditor",
            agent_department="FINANCE",
            agent_specialisation="auditor",
            agent_capabilities=["financial_review"],
            task_action="contract_review",
            task_params={"required_department": "LEGAL_COMPLIANCE"},
        )

        assert result.allowed is False
        assert "cannot execute LEGAL_COMPLIANCE task" in result.reason

    @pytest.mark.asyncio
    async def test_scenario_hr_agent_blocked_from_it_security_task(self):
        """Scenario: HR agent cannot execute IT Security department task."""
        gate = _make_oversight_gate()

        result = await gate.check(
            agent_name="recruiter",
            agent_department="HR",
            agent_specialisation="recruiter",
            agent_capabilities=["recruiting"],
            task_action="security_audit",
            task_params={"required_department": "IT_SECURITY"},
        )

        assert result.allowed is False

    @pytest.mark.asyncio
    async def test_scenario_data_ai_agent_can_execute_own_department_task(self):
        """Scenario: Data/AI agent can execute Data/AI Governance task."""
        gate = _make_oversight_gate()

        result = await gate.check(
            agent_name="ml_specialist",
            agent_department="DATA_AI_GOVERNANCE",
            agent_specialisation="ml_engineer",
            agent_capabilities=["model_training", "data_analysis"],
            task_action="model_evaluation",
            task_params={"required_department": "DATA_AI_GOVERNANCE"},
        )

        assert result.allowed is True


# =============================================================================
# Task 4f: Department validation with all Department enum values
# =============================================================================


@pytest.mark.governance
class TestDepartmentValidationAllDepartments:
    """Verify validation works for all department values."""

    DEPARTMENTS = [
        "STRATEGY",
        "OPERATIONS",
        "FINANCE",
        "HR",
        "SALES_MARKETING",
        "PRODUCT_INNOVATION",
        "IT_SECURITY",
        "LEGAL_COMPLIANCE",
        "CUSTOMER_EXPERIENCE",
        "DATA_AI_GOVERNANCE",
    ]

    @pytest.mark.parametrize("department", DEPARTMENTS)
    @pytest.mark.asyncio
    async def test_agent_can_execute_own_department_task(self, department):
        """Agent can execute task in its own department."""
        gate = _make_oversight_gate()

        result = await gate.check(
            agent_name=f"{department.lower()}_agent",
            agent_department=department,
            agent_specialisation="specialist",
            agent_capabilities=["capability"],
            task_action="action",
            task_params={"required_department": department},
        )

        assert result.allowed is True

    @pytest.mark.parametrize("agent_dept", ["FINANCE"])
    @pytest.mark.parametrize(
        "required_dept",
        ["LEGAL_COMPLIANCE", "IT_SECURITY", "OPERATIONS", "HR"],
    )
    @pytest.mark.asyncio
    async def test_agent_blocked_from_different_departments(self, agent_dept, required_dept):
        """Agent blocked when required department differs from agent department."""
        gate = _make_oversight_gate()

        result = await gate.check(
            agent_name="test_agent",
            agent_department=agent_dept,
            agent_specialisation="specialist",
            agent_capabilities=["capability"],
            task_action="action",
            task_params={"required_department": required_dept},
        )

        assert result.allowed is False
        assert required_dept in result.reason
