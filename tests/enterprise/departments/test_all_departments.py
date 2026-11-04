"""
Tests for All 10 Enterprise Departments.

Comprehensive test coverage for:
- DeterministicRouter (all 10 departments)
- EnterpriseOrchestrator (all 10 departments)
- Cross-department A2A contracts
- Prana economy across all departments
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


class TestDeterministicRouterAllDepartments:
    """Test deterministic routing for all 10 departments."""

    def test_route_strategy_market_intelligence(self):
        """Market intelligence tasks route to Strategy department."""
        router = DeterministicRouter()
        result = router.route("market_intelligence", "Analyze competitor landscape")
        assert result == Department.STRATEGY

    def test_route_strategy_ma(self):
        """M&A tasks route to Strategy department."""
        router = DeterministicRouter()
        result = router.route("merger_acquisition", "Evaluate acquisition target")
        assert result == Department.STRATEGY

    def test_route_strategy_partnerships(self):
        """Partnership tasks route to Strategy department."""
        router = DeterministicRouter()
        result = router.route("partnership", "Strategic alliance opportunity")
        assert result == Department.STRATEGY

    def test_route_product_innovation_architecture(self):
        """Architecture tasks route to Product & Innovation."""
        router = DeterministicRouter()
        result = router.route("technical_architecture", "Design microservices")
        assert result == Department.PRODUCT_INNOVATION

    def test_route_product_innovation_ux(self):
        """UX tasks route to Product & Innovation."""
        router = DeterministicRouter()
        result = router.route("ux_design", "Create wireframes")
        assert result == Department.PRODUCT_INNOVATION

    def test_route_product_innovation_qa(self):
        """QA tasks route to Product & Innovation."""
        router = DeterministicRouter()
        result = router.route("qa_testing", "Automated test suite")
        assert result == Department.PRODUCT_INNOVATION

    def test_route_operations_process_mining(self):
        """Process mining tasks route to Operations."""
        router = DeterministicRouter()
        result = router.route("process_mining", "Analyze workflow")
        assert result == Department.OPERATIONS_SUPPLY_CHAIN

    def test_route_operations_inventory(self):
        """Inventory tasks route to Operations."""
        router = DeterministicRouter()
        result = router.route("inventory_forecast", "Demand planning")
        assert result == Department.OPERATIONS_SUPPLY_CHAIN

    def test_route_operations_vendor_negotiation(self):
        """Vendor negotiation tasks route to Operations."""
        router = DeterministicRouter()
        result = router.route("vendor_negotiation", "Supplier contract terms")
        assert result == Department.OPERATIONS_SUPPLY_CHAIN

    def test_route_operations_logistics(self):
        """Logistics tasks route to Operations."""
        router = DeterministicRouter()
        result = router.route("logistics_optimization", "Route planning")
        assert result == Department.OPERATIONS_SUPPLY_CHAIN

    def test_route_sales_marketing_sdr(self):
        """SDR tasks route to Sales & Marketing."""
        router = DeterministicRouter()
        result = router.route("sdr_outreach", "Lead qualification")
        assert result == Department.SALES_MARKETING

    def test_route_sales_marketing_pricing(self):
        """Pricing tasks route to Sales & Marketing."""
        router = DeterministicRouter()
        result = router.route("dynamic_pricing", "Price optimization")
        assert result == Department.SALES_MARKETING

    def test_route_sales_marketing_content(self):
        """Content tasks route to Sales & Marketing."""
        router = DeterministicRouter()
        result = router.route("content_creation", "Blog post writing")
        assert result == Department.SALES_MARKETING

    def test_route_sales_marketing_lead_gen(self):
        """Lead gen tasks route to Sales & Marketing."""
        router = DeterministicRouter()
        result = router.route("lead_generation", "Campaign management")
        assert result == Department.SALES_MARKETING

    def test_route_finance_ar_ap(self):
        """AR/AP tasks route to Finance."""
        router = DeterministicRouter()
        result = router.route("accounts_receivable", "Invoice processing")
        assert result == Department.FINANCE

    def test_route_finance_tax(self):
        """Tax tasks route to Finance."""
        router = DeterministicRouter()
        result = router.route("tax_compliance", "VAT reporting")
        assert result == Department.FINANCE

    def test_route_finance_investment(self):
        """Investment tasks route to Finance."""
        router = DeterministicRouter()
        result = router.route("investment_allocation", "Portfolio optimization")
        assert result == Department.FINANCE

    def test_route_hr_talent(self):
        """Talent acquisition tasks route to HR."""
        router = DeterministicRouter()
        result = router.route("talent_acquisition", "Candidate screening")
        assert result == Department.HR

    def test_route_hr_sentiment(self):
        """Employee sentiment tasks route to HR."""
        router = DeterministicRouter()
        result = router.route("employee_sentiment", "Engagement survey")
        assert result == Department.HR

    def test_route_hr_skills(self):
        """Skills gap tasks route to HR."""
        router = DeterministicRouter()
        result = router.route("skills_gap", "Training needs analysis")
        assert result == Department.HR

    def test_route_it_security_threat(self):
        """Threat hunting tasks route to IT Security."""
        router = DeterministicRouter()
        result = router.route("threat_hunting", "IOC analysis")
        assert result == Department.IT_SECURITY

    def test_route_it_security_cloud(self):
        """Cloud tasks route to IT Security."""
        router = DeterministicRouter()
        result = router.route("cloud_orchestration", "Resource scaling")
        assert result == Department.IT_SECURITY

    def test_route_it_security_devops(self):
        """DevOps tasks route to IT Security."""
        router = DeterministicRouter()
        result = router.route("devops", "CI/CD pipeline")
        assert result == Department.IT_SECURITY

    def test_route_legal_gdpr(self):
        """GDPR tasks route to Legal."""
        router = DeterministicRouter()
        result = router.route("gdpr_compliance", "Privacy impact assessment")
        assert result == Department.LEGAL_COMPLIANCE

    def test_route_legal_contract(self):
        """Contract tasks route to Legal."""
        router = DeterministicRouter()
        result = router.route("contract_lifecycle", "Contract drafting")
        assert result == Department.LEGAL_COMPLIANCE

    def test_route_legal_regulatory(self):
        """Regulatory tasks route to Legal."""
        router = DeterministicRouter()
        result = router.route("regulatory_tracking", "Compliance monitoring")
        assert result == Department.LEGAL_COMPLIANCE

    def test_route_cx_support(self):
        """Support tasks route to Customer Experience."""
        router = DeterministicRouter()
        result = router.route("customer_support", "Ticket resolution")
        assert result == Department.CUSTOMER_EXPERIENCE

    def test_route_cx_sentiment(self):
        """Sentiment tasks route to Customer Experience."""
        router = DeterministicRouter()
        result = router.route("sentiment_analysis", "NPS survey")
        assert result == Department.CUSTOMER_EXPERIENCE

    def test_route_cx_success(self):
        """Customer success tasks route to Customer Experience."""
        router = DeterministicRouter()
        result = router.route("customer_success", "Onboarding")
        assert result == Department.CUSTOMER_EXPERIENCE

    def test_route_data_governance_quality(self):
        """Data quality tasks route to Data & AI Governance."""
        router = DeterministicRouter()
        result = router.route("data_quality", "Quality monitoring")
        assert result == Department.DATA_AI_GOVERNANCE

    def test_route_data_governance_ml(self):
        """ML tasks route to Data & AI Governance."""
        router = DeterministicRouter()
        result = router.route("ml_model", "Model training")
        assert result == Department.DATA_AI_GOVERNANCE

    def test_route_data_governance_ethics(self):
        """AI ethics tasks route to Data & AI Governance."""
        router = DeterministicRouter()
        result = router.route("ai_ethics", "Bias detection")
        assert result == Department.DATA_AI_GOVERNANCE

    def test_get_all_departments_returns_ten(self):
        """Router returns all 10 departments."""
        router = DeterministicRouter()
        depts = router.get_all_departments()
        assert len(depts) == 10
        assert Department.STRATEGY in depts
        assert Department.PRODUCT_INNOVATION in depts
        assert Department.OPERATIONS_SUPPLY_CHAIN in depts
        assert Department.SALES_MARKETING in depts
        assert Department.FINANCE in depts
        assert Department.HR in depts
        assert Department.IT_SECURITY in depts
        assert Department.LEGAL_COMPLIANCE in depts
        assert Department.CUSTOMER_EXPERIENCE in depts
        assert Department.DATA_AI_GOVERNANCE in depts


class TestEnterpriseOrchestratorAllDepartments:
    """Test EnterpriseOrchestrator with all 10 departments."""

    @pytest.fixture
    def enterprise(self):
        """Create enterprise orchestrator for testing."""
        return EnterpriseOrchestrator(tenant_id=1)

    def test_initializes_ten_departments(self, enterprise):
        """All 10 departments initialized."""
        assert len(enterprise.DEPARTMENTS) == 10
        assert Department.STRATEGY in enterprise.DEPARTMENTS
        assert Department.PRODUCT_INNOVATION in enterprise.DEPARTMENTS
        assert Department.OPERATIONS_SUPPLY_CHAIN in enterprise.DEPARTMENTS
        assert Department.SALES_MARKETING in enterprise.DEPARTMENTS
        assert Department.FINANCE in enterprise.DEPARTMENTS
        assert Department.HR in enterprise.DEPARTMENTS
        assert Department.IT_SECURITY in enterprise.DEPARTMENTS
        assert Department.LEGAL_COMPLIANCE in enterprise.DEPARTMENTS
        assert Department.CUSTOMER_EXPERIENCE in enterprise.DEPARTMENTS
        assert Department.DATA_AI_GOVERNANCE in enterprise.DEPARTMENTS

    def test_prana_budget_initialized_for_all(self, enterprise):
        """Each department starts with 10,000 prana."""
        for dept in enterprise.DEPARTMENTS:
            prana = enterprise.get_department_prana(dept)
            assert prana == 10000, f"{dept.value} should have 10000 prana, got {prana}"

    def test_total_prana_capacity(self, enterprise):
        """Total prana capacity is 100,000 (10 depts * 10,000)."""
        status = enterprise.get_all_prana_status()
        total = sum(status.values())
        assert total == 100000

    def test_route_task_strategy(self, enterprise):
        """Enterprise routes strategy tasks to Strategy department."""
        result = enterprise.route_task("market_intelligence")
        assert result == Department.STRATEGY

    def test_route_task_product(self, enterprise):
        """Enterprise routes product tasks to Product & Innovation."""
        result = enterprise.route_task("technical_architecture")
        assert result == Department.PRODUCT_INNOVATION

    def test_route_task_operations(self, enterprise):
        """Enterprise routes operations tasks to Operations."""
        result = enterprise.route_task("process_mining")
        assert result == Department.OPERATIONS_SUPPLY_CHAIN

    def test_route_task_sales_marketing(self, enterprise):
        """Enterprise routes sales tasks to Sales & Marketing."""
        result = enterprise.route_task("lead_generation")
        assert result == Department.SALES_MARKETING

    def test_route_task_finance(self, enterprise):
        """Enterprise routes finance tasks to Finance."""
        result = enterprise.route_task("tax_compliance")
        assert result == Department.FINANCE

    def test_route_task_hr(self, enterprise):
        """Enterprise routes HR tasks to HR."""
        result = enterprise.route_task("talent_acquisition")
        assert result == Department.HR

    def test_route_task_security(self, enterprise):
        """Enterprise routes security tasks to IT Security."""
        result = enterprise.route_task("threat_hunting")
        assert result == Department.IT_SECURITY

    def test_route_task_legal(self, enterprise):
        """Enterprise routes legal tasks to Legal."""
        result = enterprise.route_task("contract_lifecycle")
        assert result == Department.LEGAL_COMPLIANCE

    def test_route_task_cx(self, enterprise):
        """Enterprise routes CX tasks to Customer Experience."""
        result = enterprise.route_task("customer_success")
        assert result == Department.CUSTOMER_EXPERIENCE

    def test_route_task_data_governance(self, enterprise):
        """Enterprise routes data tasks to Data & AI Governance."""
        result = enterprise.route_task("ai_ethics")
        assert result == Department.DATA_AI_GOVERNANCE

    def test_enterprise_health_all_departments(self, enterprise):
        """get_enterprise_health returns all 10 departments."""
        health = enterprise.get_enterprise_health()

        assert health["tenant_id"] == 1
        assert health["total_departments"] == 10
        assert health["total_prana_capacity"] == 100000

        # Check all departments in health report
        for dept in [
            "strategy",
            "product_innovation",
            "operations_supply_chain",
            "sales_marketing",
            "finance",
            "hr",
            "it_security",
            "legal_compliance",
            "customer_experience",
            "data_ai_governance",
        ]:
            assert dept in health["health_by_department"]

        # Check health categories
        assert "strategic" in health["health_by_category"]
        assert "innovation" in health["health_by_category"]
        assert "operations" in health["health_by_category"]
        assert "growth" in health["health_by_category"]
        assert "governance" in health["health_by_category"]

    def test_get_department_agents(self, enterprise):
        """get_department_agents returns agents for each department."""
        # Strategy has 3 agents
        strategy_agents = enterprise.get_department_agents(Department.STRATEGY)
        assert len(strategy_agents) == 3

        # Product Innovation has 4 agents
        product_agents = enterprise.get_department_agents(Department.PRODUCT_INNOVATION)
        assert len(product_agents) == 4

        # Sales & Marketing has 6 agents (including human)
        sales_agents = enterprise.get_department_agents(Department.SALES_MARKETING)
        assert len(sales_agents) == 6

        # Total across all departments
        all_agents = enterprise.get_all_agents()
        total = sum(len(agents) for agents in all_agents.values())
        assert total == 40  # 40 agents total


class TestCrossDepartmentContractsAll:
    """Test cross-department A2A contracts across all departments."""

    @pytest.fixture
    def enterprise(self):
        return EnterpriseOrchestrator(tenant_id=42)

    def test_strategy_to_product_contract(self, enterprise):
        """Strategy can contract with Product for market analysis."""
        schema_ref = SchemaRef.parse("strategy.market_analysis@1.0.0")

        proposal = enterprise.create_contract_proposal(
            producer=Department.PRODUCT_INNOVATION,
            consumer=Department.STRATEGY,
            schema_ref=schema_ref,
            prana_cost=100,
        )

        contract = enterprise.accept_proposal(proposal.proposal_id)
        assert contract.state == ContractState.AGREED

    def test_sales_to_operations_contract(self, enterprise):
        """Sales can contract with Operations for demand forecasting."""
        schema_ref = SchemaRef.parse("operations.demand_forecast@1.0.0")

        proposal = enterprise.create_contract_proposal(
            producer=Department.OPERATIONS_SUPPLY_CHAIN,
            consumer=Department.SALES_MARKETING,
            schema_ref=schema_ref,
            prana_cost=75,
        )

        assert proposal.consumer_department == Department.SALES_MARKETING
        assert proposal.prana_offer == 75

    def test_finance_to_legal_contract(self, enterprise):
        """Finance can contract with Legal for compliance audit."""
        schema_ref = SchemaRef.parse("legal.compliance_report@1.0.0")

        proposal = enterprise.create_contract_proposal(
            producer=Department.LEGAL_COMPLIANCE,
            consumer=Department.FINANCE,
            schema_ref=schema_ref,
            prana_cost=150,
        )

        contract = enterprise.accept_proposal(proposal.proposal_id)
        assert contract.producer_department == Department.LEGAL_COMPLIANCE
        assert contract.consumer_department == Department.FINANCE

    def test_cx_to_data_governance_contract(self, enterprise):
        """CX can contract with Data for sentiment analysis model."""
        schema_ref = SchemaRef.parse("data.sentiment_model@1.0.0")

        proposal = enterprise.create_contract_proposal(
            producer=Department.DATA_AI_GOVERNANCE,
            consumer=Department.CUSTOMER_EXPERIENCE,
            schema_ref=schema_ref,
            prana_cost=200,
        )

        assert proposal.prana_offer == 200


class TestPranaEconomyAllDepartments:
    """Test prana token economy across all 10 departments."""

    @pytest.fixture
    def enterprise(self):
        return EnterpriseOrchestrator(tenant_id=1)

    def test_initial_balances_all_departments(self, enterprise):
        """All 10 departments start with 10,000 prana."""
        for dept in enterprise.DEPARTMENTS:
            balance = enterprise.prana_ledger.get_balance(f"dept_{dept.value}_1")
            assert balance == 10000

    def test_prana_transfer_between_any_departments(self, enterprise):
        """Prana can be transferred between any departments."""
        from_dept = Department.STRATEGY
        to_dept = Department.PRODUCT_INNOVATION

        from_id = f"dept_{from_dept.value}_1"
        to_id = f"dept_{to_dept.value}_1"

        initial_from = enterprise.prana_ledger.get_balance(from_id)
        initial_to = enterprise.prana_ledger.get_balance(to_id)

        enterprise.prana_ledger.transfer(from_id, to_id, 500)

        assert enterprise.prana_ledger.get_balance(from_id) == initial_from - 500
        assert enterprise.prana_ledger.get_balance(to_id) == initial_to + 500

    def test_all_departments_can_consume_prana(self, enterprise):
        """All departments can consume prana for contracts."""
        schema_ref = SchemaRef.parse("test.schema@1.0.0")

        # Test contract creation for each department as consumer
        for dept in enterprise.DEPARTMENTS:
            # Find a different department as producer
            producer = [d for d in enterprise.DEPARTMENTS if d != dept][0]

            proposal = enterprise.create_contract_proposal(
                producer=producer, consumer=dept, schema_ref=schema_ref, prana_cost=10
            )

            assert proposal.consumer_department == dept

            # Clean up
            enterprise.reject_proposal(proposal.proposal_id)
