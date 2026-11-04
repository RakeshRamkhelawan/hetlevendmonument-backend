"""
Sprint B Tests - Departments & Routing

Tests for:
- DeterministicRouter (rule-based, no LLM)
- EnterpriseOrchestrator (3 depts, 10K prana each)
- Cross-department A2A contracts
- Prana economy
"""

import pytest

from src.core.als.enterprise.contracts.models import ContractState
from src.core.als.enterprise.contracts.schema_registry import SchemaRef
from src.core.als.enterprise.departments.department_orchestrator import Department
from src.core.als.enterprise.departments.deterministic_router import (
    DeterministicRouter,
    TaskCategory,
    route_task,
)
from src.core.als.enterprise.departments.enterprise_orchestrator import (
    DepartmentStatus,
    EnterpriseOrchestrator,
)


class TestDeterministicRouter:
    """Test deterministic routing - NO LLM allowed."""

    def test_route_finance_invoice(self):
        """Invoice tasks route to Finance department."""
        router = DeterministicRouter()
        result = router.route("invoice_processing", "Process vendor invoice")
        assert result == Department.FINANCE

    def test_route_finance_budget(self):
        """Budget tasks route to Finance department."""
        router = DeterministicRouter()
        result = router.route("budget_analysis")
        assert result == Department.FINANCE

    def test_route_finance_forecast(self):
        """Forecast tasks route to Finance department."""
        router = DeterministicRouter()
        result = router.route("financial_forecast")
        assert result == Department.FINANCE

    def test_route_hr_hiring(self):
        """Hiring tasks route to HR department."""
        router = DeterministicRouter()
        result = router.route("hiring", "New engineer position")
        assert result == Department.HR, f"Expected HR, got {result}"

    def test_route_hr_payroll(self):
        """Payroll tasks route to HR department."""
        router = DeterministicRouter()
        result = router.route("payroll_processing")
        assert result == Department.HR

    def test_route_hr_training(self):
        """Training tasks route to HR department."""
        router = DeterministicRouter()
        result = router.route("training_coordination")
        assert result == Department.HR

    def test_route_security_vulnerability(self):
        """Vulnerability tasks route to IT Security department."""
        router = DeterministicRouter()
        result = router.route("vulnerability_assessment")
        assert result == Department.IT_SECURITY

    def test_route_security_threat(self):
        """Threat detection routes to IT Security department."""
        router = DeterministicRouter()
        result = router.route("threat_detection")
        assert result == Department.IT_SECURITY

    def test_route_security_compliance(self):
        """Compliance tasks route to IT Security department."""
        router = DeterministicRouter()
        result = router.route("compliance_auditing", "SOC2 assessment")
        assert result == Department.IT_SECURITY

    def test_route_with_prana_budget_check(self):
        """Routing respects prana budget constraints."""
        router = DeterministicRouter()

        # Finance has no budget
        available_prana = {
            Department.FINANCE: 0,  # No budget
            Department.HR: 10000,
            Department.IT_SECURITY: 10000,
        }

        # Should fall through to fallback (OPERATIONS) since Finance has no budget
        result = router.route("invoice_processing", available_prana=available_prana)
        assert result == Department.OPERATIONS, f"Expected OPERATIONS fallback, got {result}"

    def test_route_with_sufficient_prana(self):
        """Routing succeeds when budget available."""
        router = DeterministicRouter()

        available_prana = {
            Department.FINANCE: 100,  # Sufficient
            Department.HR: 10000,
            Department.IT_SECURITY: 10000,
        }

        result = router.route("invoice_processing", available_prana=available_prana)
        assert result == Department.FINANCE

    def test_can_handle_capability_check(self):
        """can_handle respects department capabilities."""
        router = DeterministicRouter()

        assert router.can_handle(Department.FINANCE, "budget_analysis")
        assert router.can_handle(Department.FINANCE, "audit")
        assert not router.can_handle(Department.FINANCE, "hiring")

        assert router.can_handle(Department.HR, "hiring")
        assert router.can_handle(Department.HR, "payroll_processing")
        assert not router.can_handle(Department.HR, "threat_detection")

        assert router.can_handle(Department.IT_SECURITY, "threat_detection")
        assert router.can_handle(Department.IT_SECURITY, "vulnerability_assessment")
        assert not router.can_handle(Department.IT_SECURITY, "budget_analysis")

    def test_get_capabilities_returns_expected(self):
        """get_capabilities returns expected capabilities."""
        router = DeterministicRouter()

        finance_caps = router.get_capabilities(Department.FINANCE)
        assert "budget_analysis" in finance_caps
        assert "audit" in finance_caps

        hr_caps = router.get_capabilities(Department.HR)
        assert "hiring" in hr_caps
        assert "payroll_processing" in hr_caps

    def test_static_route_function(self):
        """Static route_task function works correctly."""
        result = route_task("invoice_processing")
        assert result == Department.FINANCE


class TestEnterpriseOrchestrator:
    """Test EnterpriseOrchestrator with 3 departments."""

    @pytest.fixture
    def enterprise(self):
        """Create enterprise orchestrator for testing."""
        return EnterpriseOrchestrator(tenant_id=1)

    def test_initializes_three_departments(self, enterprise):
        """Sprint B: Exactly 3 departments initialized."""
        assert len(enterprise.DEPARTMENTS) == 3
        assert Department.FINANCE in enterprise.DEPARTMENTS
        assert Department.HR in enterprise.DEPARTMENTS
        assert Department.IT_SECURITY in enterprise.DEPARTMENTS

    def test_prana_budget_initialized(self, enterprise):
        """Each department starts with 10,000 prana."""
        for dept in enterprise.DEPARTMENTS:
            prana = enterprise.get_department_prana(dept)
            assert prana == 10000, f"{dept.value} should have 10000 prana, got {prana}"

    def test_get_all_prana_status(self, enterprise):
        """get_all_prana_status returns all departments."""
        status = enterprise.get_all_prana_status()
        assert len(status) == 3
        assert all(status[dept] == 10000 for dept in enterprise.DEPARTMENTS)

    def test_route_task_finance(self, enterprise):
        """Enterprise routes finance tasks to Finance department."""
        result = enterprise.route_task("budget_analysis")
        assert result == Department.FINANCE

    def test_route_task_hr(self, enterprise):
        """Enterprise routes HR tasks to HR department."""
        result = enterprise.route_task("hiring")
        assert result == Department.HR

    def test_route_task_security(self, enterprise):
        """Enterprise routes security tasks to IT Security department."""
        result = enterprise.route_task("threat_detection")
        assert result == Department.IT_SECURITY

    def test_create_contract_proposal_success(self, enterprise):
        """Can create contract proposal between departments."""
        schema_ref = SchemaRef.parse("hr.skill_matrix@1.0.0")

        proposal = enterprise.create_contract_proposal(
            producer=Department.HR,
            consumer=Department.FINANCE,
            schema_ref=schema_ref,
            deadline_ms=5000,
            prana_cost=100,
        )

        # Check proposal attributes
        assert proposal.consumer_department == Department.FINANCE
        assert proposal.prana_offer == 100  # ContractProposal uses prana_offer, not prana_cost
        assert proposal.schema_ref == schema_ref
        assert proposal.deadline_ms == 5000
        assert hasattr(proposal, "proposal_id")  # We add this dynamically

    def test_create_contract_prana_validation(self, enterprise):
        """Cannot create contract if consumer has insufficient prana."""
        # Drain Finance prana
        enterprise.prana_ledger.withdraw("dept_finance_1", 10000)

        schema_ref = SchemaRef.parse("finance.metrics@1.0.0")

        with pytest.raises(ValueError, match="insufficient prana"):
            enterprise.create_contract_proposal(
                producer=Department.IT_SECURITY,
                consumer=Department.FINANCE,  # No prana
                schema_ref=schema_ref,
                prana_cost=100,
            )

    def test_accept_proposal_creates_contract(self, enterprise):
        """Accepting proposal creates AGREED contract."""
        schema_ref = SchemaRef.parse("hr.skill_matrix@1.0.0")

        proposal = enterprise.create_contract_proposal(
            producer=Department.HR,
            consumer=Department.FINANCE,
            schema_ref=schema_ref,
            prana_cost=50,
        )

        contract = enterprise.accept_proposal(proposal.proposal_id)

        assert contract.state == ContractState.AGREED
        assert contract.producer_department == Department.HR
        assert contract.consumer_department == Department.FINANCE
        assert contract.prana_cost == 50

    def test_reject_proposal_removes_it(self, enterprise):
        """Rejecting proposal removes it from pending."""
        schema_ref = SchemaRef.parse("hr.skill_matrix@1.0.0")

        proposal = enterprise.create_contract_proposal(
            producer=Department.HR, consumer=Department.FINANCE, schema_ref=schema_ref
        )

        enterprise.reject_proposal(proposal.proposal_id, "Not needed")

        # Proposal should be removed
        assert proposal.proposal_id not in enterprise._pending_proposals

    def test_department_status_structure(self, enterprise):
        """DepartmentStatus has expected structure."""
        status = enterprise.get_department_status(Department.FINANCE)

        assert status.department == Department.FINANCE
        assert status.prana_total == 10000
        assert status.prana_available == 10000
        assert status.health_score == 1.0  # 100% healthy

    def test_department_status_offline(self, enterprise):
        """DepartmentStatus reflects offline when not initialized but prana still 100%."""
        status = enterprise.get_department_status(Department.HR)

        assert not status.is_online
        # Sprint B: Health based on prana, not online status
        assert status.health_score == 1.0  # 100% prana = healthy

    def test_enterprise_health_metrics(self, enterprise):
        """get_enterprise_health returns comprehensive metrics."""
        health = enterprise.get_enterprise_health()

        assert health["tenant_id"] == 1
        assert health["total_departments"] == 3
        assert health["total_prana_available"] == 30000  # 3 * 10000
        assert health["total_prana_capacity"] == 30000
        assert health["prana_utilization"] == 0.0  # Nothing used yet

        # Check all departments in health report
        for dept in ["finance", "hr", "it_security"]:
            assert dept in health["health_by_department"]


class TestCrossDepartmentContracts:
    """Test cross-department A2A contract scenarios."""

    @pytest.fixture
    def enterprise(self):
        return EnterpriseOrchestrator(tenant_id=42)

    def test_hr_to_finance_contract(self, enterprise):
        """HR can contract with Finance for salary analysis."""
        schema_ref = SchemaRef.parse("finance.salary_benchmark@1.0.0")

        proposal = enterprise.create_contract_proposal(
            producer=Department.FINANCE,
            consumer=Department.HR,
            schema_ref=schema_ref,
            deadline_ms=3000,
            prana_cost=75,
        )

        contract = enterprise.accept_proposal(proposal.proposal_id)

        assert contract.producer_agent == "dept_finance"
        assert contract.consumer_agent == "dept_hr"

    def test_security_to_finance_compliance_audit(self, enterprise):
        """IT Security can audit Finance for compliance."""
        schema_ref = SchemaRef.parse("security.compliance_report@1.0.0")

        proposal = enterprise.create_contract_proposal(
            producer=Department.IT_SECURITY,
            consumer=Department.FINANCE,
            schema_ref=schema_ref,
            prana_cost=200,
        )

        contract = enterprise.accept_proposal(proposal.proposal_id)

        assert contract.producer_department == Department.IT_SECURITY
        assert contract.consumer_department == Department.FINANCE

    def test_finance_to_hr_budget_training(self, enterprise):
        """Finance can contract HR for budget training."""
        schema_ref = SchemaRef.parse("hr.training_module@1.0.0")

        proposal = enterprise.create_contract_proposal(
            producer=Department.HR,
            consumer=Department.FINANCE,
            schema_ref=schema_ref,
            prana_cost=50,
        )

        assert proposal.prana_offer == 50  # ContractProposal uses prana_offer
        assert proposal.deadline_ms == 5000  # Default


class TestPranaEconomy:
    """Test prana token economy mechanics."""

    @pytest.fixture
    def enterprise(self):
        return EnterpriseOrchestrator(tenant_id=1)

    def test_initial_balances(self, enterprise):
        """All departments start with 10,000 prana."""
        for dept in enterprise.DEPARTMENTS:
            balance = enterprise.prana_ledger.get_balance(f"dept_{dept.value}_1")
            assert balance == 10000

    def test_prana_transfer_between_departments(self, enterprise):
        """Prana can be transferred between departments."""
        from_id = "dept_finance_1"
        to_id = "dept_hr_1"

        initial_from = enterprise.prana_ledger.get_balance(from_id)
        initial_to = enterprise.prana_ledger.get_balance(to_id)

        enterprise.prana_ledger.transfer(from_id, to_id, 1000)

        assert enterprise.prana_ledger.get_balance(from_id) == initial_from - 1000
        assert enterprise.prana_ledger.get_balance(to_id) == initial_to + 1000

    def test_insufficient_prana_raises_error(self, enterprise):
        """Cannot withdraw more than balance."""
        from_id = "dept_finance_1"

        # Withdraw all
        enterprise.prana_ledger.withdraw(from_id, 10000)

        # Try to withdraw more
        with pytest.raises(Exception):  # InsufficientPranaError
            enterprise.prana_ledger.withdraw(from_id, 1)

    def test_contract_proposal_validates_prana(self, enterprise):
        """Creating proposal validates consumer has enough prana."""
        # Drain Finance
        enterprise.prana_ledger.withdraw("dept_finance_1", 10000)

        with pytest.raises(ValueError, match="insufficient prana"):
            enterprise.create_contract_proposal(
                producer=Department.HR,
                consumer=Department.FINANCE,
                schema_ref=SchemaRef.parse("hr.skill_matrix@1.0.0"),
                prana_cost=1,
            )
