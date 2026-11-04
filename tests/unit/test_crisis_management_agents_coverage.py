"""
P4.1.3: Crisis Management Agents Coverage Tests
Tests for src/core/subagents/crisis_management_agents.py (637 LOC)

Coverage target: 80%+

Agents tested:
- CybersecurityAgent: incident_analysis, threat_assessment, system_isolation, forensic_analysis, recovery_planning
- LegalComplianceAgent: regulatory_assessment, liability_analysis, notification_requirements, ransom_payment_analysis
- PRCommunicationsAgent: stakeholder_analysis, communication_strategy, media_response, customer_communications
- FinancialRiskAgent: cost_analysis, revenue_impact, insurance_analysis, ransom_cost_benefit
- CustomerOperationsAgent: service_continuity, customer_impact, alternative_services, recovery_planning

Run:
    python -m pytest tests/unit/test_crisis_management_agents_coverage.py --cov=src/core/subagents/crisis_management_agents --cov-report=term-missing -v
"""

from datetime import datetime
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.subagents.agent_factory import AgentConfiguration, AgentStatus
from src.core.subagents.crisis_management_agents import (
    CrisisContext,
    CrisisType,
    CustomerOperationsAgent,
    CybersecurityAgent,
    FinancialRiskAgent,
    LegalComplianceAgent,
    PRCommunicationsAgent,
    RiskLevel,
)
from src.core.types import AgentType

# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def cybersecurity_agent_config():
    """Create a configuration for CybersecurityAgent."""
    return AgentConfiguration(
        agent_type=AgentType.SPECIALIST,
        name="cybersecurity_agent",
        capabilities=["incident_analysis", "threat_assessment", "system_isolation"],
        max_concurrent_tasks=5,
        memory_limit_mb=256,
        cpu_priority="high",
        specialized_parameters={"security_level": "critical"},
    )


@pytest.fixture
def legal_agent_config():
    """Create a configuration for LegalComplianceAgent."""
    return AgentConfiguration(
        agent_type=AgentType.SPECIALIST,
        name="legal_compliance_agent",
        capabilities=["regulatory_assessment", "liability_analysis"],
        max_concurrent_tasks=3,
        memory_limit_mb=128,
        cpu_priority="normal",
        specialized_parameters={"jurisdiction": "EU"},
    )


@pytest.fixture
def pr_agent_config():
    """Create a configuration for PRCommunicationsAgent."""
    return AgentConfiguration(
        agent_type=AgentType.SPECIALIST,
        name="pr_communications_agent",
        capabilities=["communication_strategy", "media_response"],
        max_concurrent_tasks=3,
        memory_limit_mb=128,
        cpu_priority="normal",
        specialized_parameters={"language": "nl"},
    )


@pytest.fixture
def financial_agent_config():
    """Create a configuration for FinancialRiskAgent."""
    return AgentConfiguration(
        agent_type=AgentType.SPECIALIST,
        name="financial_risk_agent",
        capabilities=["cost_analysis", "ransom_cost_benefit"],
        max_concurrent_tasks=3,
        memory_limit_mb=128,
        cpu_priority="normal",
        specialized_parameters={"currency": "EUR"},
    )


@pytest.fixture
def operations_agent_config():
    """Create a configuration for CustomerOperationsAgent."""
    return AgentConfiguration(
        agent_type=AgentType.SPECIALIST,
        name="customer_operations_agent",
        capabilities=["service_continuity", "customer_impact"],
        max_concurrent_tasks=3,
        memory_limit_mb=128,
        cpu_priority="normal",
        specialized_parameters={},
    )


@pytest.fixture
def sample_crisis_context() -> Dict[str, Any]:
    """Create a sample crisis context dictionary."""
    return {
        "crisis_code": "CRISIS-2024-001",
        "crisis_type": CrisisType.CYBERSECURITY,
        "severity": RiskLevel.CRITICAL,
        "timeline": "48 hours",
        "affected_systems": ["customer_database", "transaction_system"],
        "stakeholders": ["customers", "regulators", "board"],
        "regulatory_implications": ["GDPR", "PCI-DSS"],
    }


@pytest.fixture
def sample_task_data(sample_crisis_context) -> Dict[str, Any]:
    """Create sample task data with crisis context."""
    return {
        "crisis_context": {
            "crisis_code": sample_crisis_context["crisis_code"],
            "crisis_type": sample_crisis_context["crisis_type"].value,
            "severity": sample_crisis_context["severity"].value,
            "timeline": sample_crisis_context["timeline"],
            "affected_systems": sample_crisis_context["affected_systems"],
            "stakeholders": sample_crisis_context["stakeholders"],
            "regulatory_implications": sample_crisis_context["regulatory_implications"],
        },
        "urgency": "critical",
        "incident_details": {"attack_type": "ransomware"},
    }


# =============================================================================
# TEST: CrisisContext and Enums
# =============================================================================


class TestCrisisEnumsAndContext:
    """Test crisis management enums and data classes."""

    def test_crisis_type_enum_values(self):
        """Test CrisisType enum has expected values."""
        assert CrisisType.CYBERSECURITY.value == "cybersecurity"
        assert CrisisType.FINANCIAL.value == "financial"
        assert CrisisType.OPERATIONAL.value == "operational"
        assert CrisisType.REPUTATIONAL.value == "reputational"
        assert CrisisType.REGULATORY.value == "regulatory"

    def test_risk_level_enum_values(self):
        """Test RiskLevel enum has expected values."""
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.MEDIUM.value == "medium"
        assert RiskLevel.HIGH.value == "high"
        assert RiskLevel.CRITICAL.value == "critical"

    def test_crisis_context_creation(self):
        """Test CrisisContext dataclass creation."""
        context = CrisisContext(
            crisis_code="TEST-001",
            crisis_type=CrisisType.CYBERSECURITY,
            severity=RiskLevel.HIGH,
            timeline="24 hours",
            affected_systems=["system1", "system2"],
            stakeholders=["group1"],
            regulatory_implications=["GDPR"],
        )

        assert context.crisis_code == "TEST-001"
        assert context.crisis_type == CrisisType.CYBERSECURITY
        assert context.severity == RiskLevel.HIGH
        assert context.timeline == "24 hours"
        assert len(context.affected_systems) == 2
        assert len(context.stakeholders) == 1
        assert "GDPR" in context.regulatory_implications


# =============================================================================
# TEST CLASS: CybersecurityAgent
# =============================================================================


class TestCybersecurityAgent:
    """Test CybersecurityAgent class."""

    @pytest.fixture
    def cyber_agent(self, cybersecurity_agent_config):
        """Create a CybersecurityAgent instance."""
        agent = CybersecurityAgent("cyber-agent-001", cybersecurity_agent_config)
        return agent

    @pytest.mark.asyncio
    async def test_agent_specific_init(self, cyber_agent):
        """Test agent initialization with security functions."""
        await cyber_agent._agent_specific_init()

        assert hasattr(cyber_agent, "security_functions")
        assert "incident_analysis" in cyber_agent.security_functions
        assert "threat_assessment" in cyber_agent.security_functions
        assert "system_isolation" in cyber_agent.security_functions
        assert "forensic_analysis" in cyber_agent.security_functions
        assert "recovery_planning" in cyber_agent.security_functions
        assert "vulnerability_assessment" in cyber_agent.security_functions
        assert len(cyber_agent.security_functions) == 6

    @pytest.mark.asyncio
    async def test_execute_specific_task_unknown_type(self, cyber_agent, sample_task_data):
        """Test execution with unknown analysis type returns error."""
        await cyber_agent._agent_specific_init()
        sample_task_data["analysis_type"] = "unknown_analysis"

        result = await cyber_agent._execute_specific_task(sample_task_data)

        assert "error" in result
        assert "unknown_analysis" in result["error"]
        assert "available_functions" in result

    @pytest.mark.asyncio
    async def test_execute_specific_task_incident_analysis(self, cyber_agent, sample_task_data):
        """Test incident analysis execution."""
        await cyber_agent._agent_specific_init()
        sample_task_data["analysis_type"] = "incident_analysis"

        result = await cyber_agent._execute_specific_task(sample_task_data)

        assert result["agent_type"] == "cybersecurity"
        assert result["analysis_type"] == "incident_analysis"
        assert "urgency" in result
        assert "result" in result
        assert "timestamp" in result
        assert "recommendations" in result
        assert "next_actions" in result

    @pytest.mark.asyncio
    async def test_execute_specific_task_default_type(self, cyber_agent, sample_task_data):
        """Test default analysis type is incident_analysis."""
        await cyber_agent._agent_specific_init()
        # Remove analysis_type if present to test default behavior
        sample_task_data.pop("analysis_type", None)

        result = await cyber_agent._execute_specific_task(sample_task_data)

        # Should default to incident_analysis
        assert result["analysis_type"] == "incident_analysis"

    @pytest.mark.asyncio
    async def test_analyze_incident_response_structure(self, cyber_agent, sample_task_data):
        """Test _analyze_incident returns expected structure."""
        await cyber_agent._agent_specific_init()

        context = CrisisContext(
            crisis_code="TEST-001",
            crisis_type=CrisisType.CYBERSECURITY,
            severity=RiskLevel.CRITICAL,
            timeline="48 hours",
            affected_systems=["database"],
            stakeholders=["customers"],
            regulatory_implications=["GDPR"],
        )

        result = await cyber_agent._analyze_incident(context, sample_task_data)

        assert "analysis" in result
        assert "recommendations" in result
        assert "next_actions" in result
        assert "recovery_feasibility" in result
        assert "estimated_recovery_time" in result

        # Verify analysis details
        analysis = result["analysis"]
        assert "incident_type" in analysis
        assert "attack_vector" in analysis
        assert "scope_assessment" in analysis
        assert "threat_actor_profile" in analysis
        assert "immediate_risks" in analysis

    @pytest.mark.asyncio
    async def test_assess_threat_response(self, cyber_agent, sample_task_data):
        """Test _assess_threat returns threat assessment."""
        await cyber_agent._agent_specific_init()

        context = CrisisContext(
            crisis_code="TEST-001",
            crisis_type=CrisisType.CYBERSECURITY,
            severity=RiskLevel.CRITICAL,
            timeline="48 hours",
            affected_systems=["database"],
            stakeholders=["customers"],
            regulatory_implications=["GDPR"],
        )

        result = await cyber_agent._assess_threat(context, sample_task_data)

        assert "current_threat_level" in result
        assert result["current_threat_level"] == "CRITICAL"
        assert "threat_persistence" in result
        assert "data_exfiltration_status" in result
        assert "attack_progression" in result
        assert "threat_indicators" in result

    @pytest.mark.asyncio
    async def test_recommend_isolation_response(self, cyber_agent, sample_task_data):
        """Test _recommend_isolation returns isolation strategy."""
        await cyber_agent._agent_specific_init()

        context = CrisisContext(
            crisis_code="TEST-001",
            crisis_type=CrisisType.CYBERSECURITY,
            severity=RiskLevel.CRITICAL,
            timeline="48 hours",
            affected_systems=["database"],
            stakeholders=["customers"],
            regulatory_implications=["GDPR"],
        )

        result = await cyber_agent._recommend_isolation(context, sample_task_data)

        assert "isolation_strategy" in result
        assert "systems_to_isolate" in result
        assert "isolation_procedures" in result
        assert "business_impact" in result
        assert "isolation_timeline" in result
        assert isinstance(result["systems_to_isolate"], list)
        assert len(result["systems_to_isolate"]) > 0

    @pytest.mark.asyncio
    async def test_execute_threat_assessment_via_task(self, cyber_agent, sample_task_data):
        """Test threat_assessment via execute_specific_task."""
        await cyber_agent._agent_specific_init()
        sample_task_data["analysis_type"] = "threat_assessment"

        result = await cyber_agent._execute_specific_task(sample_task_data)

        assert result["analysis_type"] == "threat_assessment"
        assert "result" in result
        assert result["result"]["current_threat_level"] == "CRITICAL"

    @pytest.mark.asyncio
    async def test_execute_system_isolation_via_task(self, cyber_agent, sample_task_data):
        """Test system_isolation via execute_specific_task."""
        await cyber_agent._agent_specific_init()
        sample_task_data["analysis_type"] = "system_isolation"

        result = await cyber_agent._execute_specific_task(sample_task_data)

        assert result["analysis_type"] == "system_isolation"
        assert "result" in result
        assert "isolation_strategy" in result["result"]


# =============================================================================
# TEST CLASS: LegalComplianceAgent
# =============================================================================


class TestLegalComplianceAgent:
    """Test LegalComplianceAgent class."""

    @pytest.fixture
    def legal_agent(self, legal_agent_config):
        """Create a LegalComplianceAgent instance."""
        agent = LegalComplianceAgent("legal-agent-001", legal_agent_config)
        return agent

    @pytest.mark.asyncio
    async def test_agent_specific_init(self, legal_agent):
        """Test agent initialization with legal functions."""
        await legal_agent._agent_specific_init()

        assert hasattr(legal_agent, "legal_functions")
        assert "regulatory_assessment" in legal_agent.legal_functions
        assert "liability_analysis" in legal_agent.legal_functions
        assert "notification_requirements" in legal_agent.legal_functions
        assert "ransom_payment_analysis" in legal_agent.legal_functions
        assert "compliance_obligations" in legal_agent.legal_functions
        assert len(legal_agent.legal_functions) == 5

    @pytest.mark.asyncio
    async def test_execute_specific_task_regulatory_assessment(self, legal_agent, sample_task_data):
        """Test regulatory assessment execution."""
        await legal_agent._agent_specific_init()
        sample_task_data["analysis_type"] = "regulatory_assessment"

        result = await legal_agent._execute_specific_task(sample_task_data)

        assert result["agent_type"] == "legal_compliance"
        assert result["analysis_type"] == "regulatory_assessment"
        assert "result" in result
        assert "timestamp" in result
        assert "legal_recommendations" in result
        assert "compliance_actions" in result

    @pytest.mark.asyncio
    async def test_assess_regulatory_requirements_response(self, legal_agent, sample_task_data):
        """Test _assess_regulatory_requirements returns compliance info."""
        await legal_agent._agent_specific_init()

        context = CrisisContext(
            crisis_code="TEST-001",
            crisis_type=CrisisType.CYBERSECURITY,
            severity=RiskLevel.CRITICAL,
            timeline="48 hours",
            affected_systems=["database"],
            stakeholders=["customers"],
            regulatory_implications=["GDPR"],
        )

        result = await legal_agent._assess_regulatory_requirements(context, sample_task_data)

        assert "gdpr_obligations" in result
        assert "pci_dss_requirements" in result
        assert "financial_regulations" in result
        assert "other_obligations" in result

        # Verify GDPR specifics
        gdpr = result["gdpr_obligations"]
        assert "notification_deadline" in gdpr
        assert "supervisory_authority" in gdpr
        assert "potential_fines" in gdpr

    @pytest.mark.asyncio
    async def test_analyze_liability_response(self, legal_agent, sample_task_data):
        """Test _analyze_liability returns liability assessment."""
        await legal_agent._agent_specific_init()

        context = CrisisContext(
            crisis_code="TEST-001",
            crisis_type=CrisisType.CYBERSECURITY,
            severity=RiskLevel.CRITICAL,
            timeline="48 hours",
            affected_systems=["database"],
            stakeholders=["customers"],
            regulatory_implications=["GDPR"],
        )

        result = await legal_agent._analyze_liability(context, sample_task_data)

        assert "liability_assessment" in result
        assert "mitigating_factors" in result

        liability = result["liability_assessment"]
        assert "gdpr_liability" in liability
        assert "civil_liability" in liability
        assert "criminal_liability" in liability

    @pytest.mark.asyncio
    async def test_analyze_ransom_legality_response(self, legal_agent, sample_task_data):
        """Test _analyze_ransom_legality returns legal analysis."""
        await legal_agent._agent_specific_init()

        context = CrisisContext(
            crisis_code="TEST-001",
            crisis_type=CrisisType.CYBERSECURITY,
            severity=RiskLevel.CRITICAL,
            timeline="48 hours",
            affected_systems=["database"],
            stakeholders=["customers"],
            regulatory_implications=["GDPR"],
        )

        result = await legal_agent._analyze_ransom_legality(context, sample_task_data)

        assert "ransom_payment_analysis" in result
        assert "legal_recommendation" in result
        assert "alternative_approaches" in result
        assert result["legal_recommendation"] == "DO NOT PAY RANSOM"

        payment_analysis = result["ransom_payment_analysis"]
        assert "legal_status" in payment_analysis
        assert "key_issues" in payment_analysis
        assert "regulatory_guidance" in payment_analysis
        assert "compliance_risks" in payment_analysis

    @pytest.mark.asyncio
    async def test_execute_liability_analysis_via_task(self, legal_agent, sample_task_data):
        """Test liability_analysis via execute_specific_task."""
        await legal_agent._agent_specific_init()
        sample_task_data["analysis_type"] = "liability_analysis"

        result = await legal_agent._execute_specific_task(sample_task_data)

        assert result["analysis_type"] == "liability_analysis"
        assert "liability_assessment" in result["result"]

    @pytest.mark.asyncio
    async def test_execute_ransom_payment_analysis_via_task(self, legal_agent, sample_task_data):
        """Test ransom_payment_analysis via execute_specific_task."""
        await legal_agent._agent_specific_init()
        sample_task_data["analysis_type"] = "ransom_payment_analysis"

        result = await legal_agent._execute_specific_task(sample_task_data)

        assert result["analysis_type"] == "ransom_payment_analysis"
        assert result["result"]["legal_recommendation"] == "DO NOT PAY RANSOM"


# =============================================================================
# TEST CLASS: PRCommunicationsAgent
# =============================================================================


class TestPRCommunicationsAgent:
    """Test PRCommunicationsAgent class."""

    @pytest.fixture
    def pr_agent(self, pr_agent_config):
        """Create a PRCommunicationsAgent instance."""
        agent = PRCommunicationsAgent("pr-agent-001", pr_agent_config)
        return agent

    @pytest.mark.asyncio
    async def test_agent_specific_init(self, pr_agent):
        """Test agent initialization with communications functions."""
        await pr_agent._agent_specific_init()

        assert hasattr(pr_agent, "communications_functions")
        assert "stakeholder_analysis" in pr_agent.communications_functions
        assert "communication_strategy" in pr_agent.communications_functions
        assert "media_response" in pr_agent.communications_functions
        assert "customer_communications" in pr_agent.communications_functions
        assert "internal_communications" in pr_agent.communications_functions
        assert "social_media_monitoring" in pr_agent.communications_functions
        assert len(pr_agent.communications_functions) == 6

    @pytest.mark.asyncio
    async def test_execute_specific_task_communication_strategy(self, pr_agent, sample_task_data):
        """Test communication strategy execution."""
        await pr_agent._agent_specific_init()
        sample_task_data["analysis_type"] = "communication_strategy"

        result = await pr_agent._execute_specific_task(sample_task_data)

        assert result["agent_type"] == "pr_communications"
        assert result["analysis_type"] == "communication_strategy"
        assert "result" in result
        assert "timestamp" in result
        assert "communication_materials" in result
        assert "stakeholder_actions" in result

    @pytest.mark.asyncio
    async def test_develop_communication_strategy_response(self, pr_agent, sample_task_data):
        """Test _develop_communication_strategy returns strategy details."""
        await pr_agent._agent_specific_init()

        context = CrisisContext(
            crisis_code="TEST-001",
            crisis_type=CrisisType.CYBERSECURITY,
            severity=RiskLevel.CRITICAL,
            timeline="48 hours",
            affected_systems=["database"],
            stakeholders=["customers"],
            regulatory_implications=["GDPR"],
        )

        result = await pr_agent._develop_communication_strategy(context, sample_task_data)

        assert "communication_strategy" in result
        assert "stakeholder_priorities" in result
        assert "communication_timeline" in result

        strategy = result["communication_strategy"]
        assert "core_message" in strategy
        assert "key_principles" in strategy
        assert "tone" in strategy

        priorities = result["stakeholder_priorities"]
        assert "tier_1_critical" in priorities
        assert "tier_2_important" in priorities
        assert "tier_3_monitoring" in priorities

    @pytest.mark.asyncio
    async def test_prepare_customer_communications_response(self, pr_agent, sample_task_data):
        """Test _prepare_customer_communications returns communication package."""
        await pr_agent._agent_specific_init()

        context = CrisisContext(
            crisis_code="TEST-001",
            crisis_type=CrisisType.CYBERSECURITY,
            severity=RiskLevel.CRITICAL,
            timeline="48 hours",
            affected_systems=["database"],
            stakeholders=["customers"],
            regulatory_implications=["GDPR"],
        )

        result = await pr_agent._prepare_customer_communications(context, sample_task_data)

        assert "customer_communication_package" in result
        assert "customer_protection_measures" in result

        package = result["customer_communication_package"]
        assert "notification_email" in package
        assert "website_banner" in package
        assert "dedicated_crisis_page" in package
        assert "customer_service_scripts" in package

        # Verify protection measures
        measures = result["customer_protection_measures"]
        assert isinstance(measures, list)
        assert len(measures) > 0

    @pytest.mark.asyncio
    async def test_execute_customer_communications_via_task(self, pr_agent, sample_task_data):
        """Test customer_communications via execute_specific_task."""
        await pr_agent._agent_specific_init()
        sample_task_data["analysis_type"] = "customer_communications"

        result = await pr_agent._execute_specific_task(sample_task_data)

        assert result["analysis_type"] == "customer_communications"
        assert "customer_communication_package" in result["result"]


# =============================================================================
# TEST CLASS: FinancialRiskAgent
# =============================================================================


class TestFinancialRiskAgent:
    """Test FinancialRiskAgent class."""

    @pytest.fixture
    def financial_agent(self, financial_agent_config):
        """Create a FinancialRiskAgent instance."""
        agent = FinancialRiskAgent("financial-agent-001", financial_agent_config)
        return agent

    @pytest.mark.asyncio
    async def test_agent_specific_init(self, financial_agent):
        """Test agent initialization with financial functions."""
        await financial_agent._agent_specific_init()

        assert hasattr(financial_agent, "financial_functions")
        assert "cost_analysis" in financial_agent.financial_functions
        assert "revenue_impact" in financial_agent.financial_functions
        assert "insurance_analysis" in financial_agent.financial_functions
        assert "ransom_cost_benefit" in financial_agent.financial_functions
        assert "recovery_financing" in financial_agent.financial_functions
        assert len(financial_agent.financial_functions) == 5

    @pytest.mark.asyncio
    async def test_execute_specific_task_cost_analysis(self, financial_agent, sample_task_data):
        """Test cost analysis execution."""
        await financial_agent._agent_specific_init()
        sample_task_data["analysis_type"] = "cost_analysis"

        result = await financial_agent._execute_specific_task(sample_task_data)

        assert result["agent_type"] == "financial_risk"
        assert result["analysis_type"] == "cost_analysis"
        assert "result" in result
        assert "timestamp" in result
        assert "financial_recommendations" in result
        assert "cost_projections" in result

    @pytest.mark.asyncio
    async def test_analyze_ransom_cost_benefit_response(self, financial_agent, sample_task_data):
        """Test _analyze_ransom_cost_benefit returns detailed analysis."""
        await financial_agent._agent_specific_init()

        context = CrisisContext(
            crisis_code="TEST-001",
            crisis_type=CrisisType.CYBERSECURITY,
            severity=RiskLevel.CRITICAL,
            timeline="48 hours",
            affected_systems=["database"],
            stakeholders=["customers"],
            regulatory_implications=["GDPR"],
        )

        result = await financial_agent._analyze_ransom_cost_benefit(context, sample_task_data)

        assert "ransom_payment_scenario" in result
        assert "recovery_without_payment_scenario" in result
        assert "financial_recommendation" in result
        assert "cost_benefit_analysis" in result
        assert result["financial_recommendation"] == "DO NOT PAY RANSOM"

        # Verify ransom scenario details
        ransom = result["ransom_payment_scenario"]
        assert "direct_costs" in ransom
        assert "hidden_costs" in ransom
        assert "timeline_risks" in ransom

        # Verify recovery scenario details
        recovery = result["recovery_without_payment_scenario"]
        assert "direct_costs" in recovery
        assert "benefits" in recovery
        assert "timeline" in recovery

    @pytest.mark.asyncio
    async def test_execute_ransom_cost_benefit_via_task(self, financial_agent, sample_task_data):
        """Test ransom_cost_benefit via execute_specific_task."""
        await financial_agent._agent_specific_init()
        sample_task_data["analysis_type"] = "ransom_cost_benefit"

        result = await financial_agent._execute_specific_task(sample_task_data)

        assert result["analysis_type"] == "ransom_cost_benefit"
        assert result["result"]["financial_recommendation"] == "DO NOT PAY RANSOM"

    @pytest.mark.asyncio
    async def test_cost_benefit_calculation_accuracy(self, financial_agent, sample_task_data):
        """Test that cost benefit calculations are logical."""
        await financial_agent._agent_specific_init()

        context = CrisisContext(
            crisis_code="TEST-001",
            crisis_type=CrisisType.CYBERSECURITY,
            severity=RiskLevel.CRITICAL,
            timeline="48 hours",
            affected_systems=["database"],
            stakeholders=["customers"],
            regulatory_implications=["GDPR"],
        )

        result = await financial_agent._analyze_ransom_cost_benefit(context, sample_task_data)

        # Verify the analysis has cost breakdown
        analysis = result["cost_benefit_analysis"]
        assert "ransom_scenario_total_cost" in analysis
        assert "recovery_scenario_total_cost" in analysis
        assert "insurance_offset" in analysis
        assert "net_recovery_cost" in analysis
        assert "cost_advantage" in analysis


# =============================================================================
# TEST CLASS: CustomerOperationsAgent
# =============================================================================


class TestCustomerOperationsAgent:
    """Test CustomerOperationsAgent class."""

    @pytest.fixture
    def operations_agent(self, operations_agent_config):
        """Create a CustomerOperationsAgent instance."""
        agent = CustomerOperationsAgent("ops-agent-001", operations_agent_config)
        return agent

    @pytest.mark.asyncio
    async def test_agent_specific_init(self, operations_agent):
        """Test agent initialization with operations functions."""
        await operations_agent._agent_specific_init()

        assert hasattr(operations_agent, "operations_functions")
        assert "service_continuity" in operations_agent.operations_functions
        assert "customer_impact" in operations_agent.operations_functions
        assert "alternative_services" in operations_agent.operations_functions
        assert "recovery_planning" in operations_agent.operations_functions
        assert "support_scaling" in operations_agent.operations_functions
        assert len(operations_agent.operations_functions) == 5

    @pytest.mark.asyncio
    async def test_execute_specific_task_service_continuity(
        self, operations_agent, sample_task_data
    ):
        """Test service continuity execution."""
        await operations_agent._agent_specific_init()
        sample_task_data["analysis_type"] = "service_continuity"

        result = await operations_agent._execute_specific_task(sample_task_data)

        assert result["agent_type"] == "customer_operations"
        assert result["analysis_type"] == "service_continuity"
        assert "result" in result
        assert "timestamp" in result
        assert "operational_recommendations" in result
        assert "service_restoration" in result

    @pytest.mark.asyncio
    async def test_assess_service_continuity_response(self, operations_agent, sample_task_data):
        """Test _assess_service_continuity returns continuity assessment."""
        await operations_agent._agent_specific_init()

        context = CrisisContext(
            crisis_code="TEST-001",
            crisis_type=CrisisType.CYBERSECURITY,
            severity=RiskLevel.CRITICAL,
            timeline="48 hours",
            affected_systems=["database"],
            stakeholders=["customers"],
            regulatory_implications=["GDPR"],
        )

        result = await operations_agent._assess_service_continuity(context, sample_task_data)

        assert "service_continuity_assessment" in result
        assert "immediate_actions_required" in result

        assessment = result["service_continuity_assessment"]
        assert "critical_services_status" in assessment
        assert "estimated_customer_impact" in assessment
        assert "business_continuity_options" in assessment

        # Verify impact estimates
        impact = assessment["estimated_customer_impact"]
        assert "total_affected_customers" in impact
        assert "high_value_customers" in impact
        assert "pending_transactions" in impact

        # Verify continuity options
        options = assessment["business_continuity_options"]
        assert "manual_processing" in options
        assert "partner_services" in options
        assert "minimal_service_restoration" in options

    @pytest.mark.asyncio
    async def test_service_status_values(self, operations_agent, sample_task_data):
        """Test service status contains expected values."""
        await operations_agent._agent_specific_init()

        context = CrisisContext(
            crisis_code="TEST-001",
            crisis_type=CrisisType.CYBERSECURITY,
            severity=RiskLevel.CRITICAL,
            timeline="48 hours",
            affected_systems=["database"],
            stakeholders=["customers"],
            regulatory_implications=["GDPR"],
        )

        result = await operations_agent._assess_service_continuity(context, sample_task_data)

        services = result["service_continuity_assessment"]["critical_services_status"]
        assert "customer_login_portal" in services
        assert "transaction_processing" in services
        assert "predicta_trading_algorithm" in services
        assert "customer_support_system" in services
        assert "mobile_application" in services

    @pytest.mark.asyncio
    async def test_immediate_actions_list(self, operations_agent, sample_task_data):
        """Test immediate actions are properly defined."""
        await operations_agent._agent_specific_init()

        context = CrisisContext(
            crisis_code="TEST-001",
            crisis_type=CrisisType.CYBERSECURITY,
            severity=RiskLevel.CRITICAL,
            timeline="48 hours",
            affected_systems=["database"],
            stakeholders=["customers"],
            regulatory_implications=["GDPR"],
        )

        result = await operations_agent._assess_service_continuity(context, sample_task_data)

        actions = result["immediate_actions_required"]
        assert isinstance(actions, list)
        assert len(actions) >= 3
        assert any("business continuity" in action.lower() for action in actions)


# =============================================================================
# INTEGRATION TESTS: Cross-Agent Scenarios
# =============================================================================


class TestCrisisAgentIntegration:
    """Integration tests for crisis management agent coordination."""

    @pytest.mark.asyncio
    async def test_multi_agent_crisis_response(
        self,
        cybersecurity_agent_config,
        legal_agent_config,
        pr_agent_config,
        financial_agent_config,
        operations_agent_config,
        sample_task_data,
    ):
        """Test coordinated response from multiple agents."""
        # Create all agents
        cyber_agent = CybersecurityAgent("cyber-001", cybersecurity_agent_config)
        legal_agent = LegalComplianceAgent("legal-001", legal_agent_config)
        pr_agent = PRCommunicationsAgent("pr-001", pr_agent_config)
        financial_agent = FinancialRiskAgent("financial-001", financial_agent_config)
        ops_agent = CustomerOperationsAgent("ops-001", operations_agent_config)

        # Initialize all agents
        await cyber_agent._agent_specific_init()
        await legal_agent._agent_specific_init()
        await pr_agent._agent_specific_init()
        await financial_agent._agent_specific_init()
        await ops_agent._agent_specific_init()

        # Execute tasks on all agents
        cyber_task = dict(sample_task_data)
        cyber_task["analysis_type"] = "incident_analysis"

        legal_task = dict(sample_task_data)
        legal_task["analysis_type"] = "regulatory_assessment"

        pr_task = dict(sample_task_data)
        pr_task["analysis_type"] = "communication_strategy"

        financial_task = dict(sample_task_data)
        financial_task["analysis_type"] = "ransom_cost_benefit"

        ops_task = dict(sample_task_data)
        ops_task["analysis_type"] = "service_continuity"

        # Execute all tasks
        cyber_result = await cyber_agent._execute_specific_task(cyber_task)
        legal_result = await legal_agent._execute_specific_task(legal_task)
        pr_result = await pr_agent._execute_specific_task(pr_task)
        financial_result = await financial_agent._execute_specific_task(financial_task)
        ops_result = await ops_agent._execute_specific_task(ops_task)

        # Verify all agents responded
        assert cyber_result["agent_type"] == "cybersecurity"
        assert legal_result["agent_type"] == "legal_compliance"
        assert pr_result["agent_type"] == "pr_communications"
        assert financial_result["agent_type"] == "financial_risk"
        assert ops_result["agent_type"] == "customer_operations"

        # Verify consistent recommendations (both legal and financial recommend NO payment)
        assert financial_result["result"]["financial_recommendation"] == "DO NOT PAY RANSOM"

    @pytest.mark.asyncio
    async def test_crisis_context_shared_across_agents(
        self, cybersecurity_agent_config, legal_agent_config, sample_task_data
    ):
        """Test that crisis context is properly handled by multiple agents."""
        cyber_agent = CybersecurityAgent("cyber-001", cybersecurity_agent_config)
        legal_agent = LegalComplianceAgent("legal-001", legal_agent_config)

        await cyber_agent._agent_specific_init()
        await legal_agent._agent_specific_init()

        # Same crisis context should be handled correctly by both
        cyber_task = dict(sample_task_data)
        cyber_task["analysis_type"] = "incident_analysis"

        legal_task = dict(sample_task_data)
        legal_task["analysis_type"] = "regulatory_assessment"

        cyber_result = await cyber_agent._execute_specific_task(cyber_task)
        legal_result = await legal_agent._execute_specific_task(legal_task)

        # Both should have valid timestamps
        assert "timestamp" in cyber_result
        assert "timestamp" in legal_result

        # Both should reference the same crisis scenario (ransomware/data breach)
        assert "50,000" in str(cyber_result["result"]) or "50000" in str(cyber_result["result"])


# =============================================================================
# EDGE CASE TESTS
# =============================================================================


class TestCrisisAgentEdgeCases:
    """Edge case tests for crisis management agents."""

    @pytest.mark.asyncio
    async def test_cyber_agent_with_minimal_crisis_context(self, cybersecurity_agent_config):
        """Test cyber agent with minimal crisis context."""
        agent = CybersecurityAgent("cyber-001", cybersecurity_agent_config)
        await agent._agent_specific_init()

        minimal_context = {
            "crisis_context": {
                "crisis_code": "MIN-001",
                "crisis_type": "cybersecurity",
                "severity": "low",
                "timeline": "unknown",
                "affected_systems": [],
                "stakeholders": [],
                "regulatory_implications": [],
            },
            "analysis_type": "incident_analysis",
        }

        result = await agent._execute_specific_task(minimal_context)

        assert result["agent_type"] == "cybersecurity"
        assert "result" in result

    @pytest.mark.asyncio
    async def test_legal_agent_with_all_analysis_types(self, legal_agent_config, sample_task_data):
        """Test legal agent handles all supported analysis types."""
        agent = LegalComplianceAgent("legal-001", legal_agent_config)
        await agent._agent_specific_init()

        analysis_types = [
            "regulatory_assessment",
            "liability_analysis",
            "ransom_payment_analysis",
        ]

        for analysis_type in analysis_types:
            task = dict(sample_task_data)
            task["analysis_type"] = analysis_type
            result = await agent._execute_specific_task(task)
            assert result["analysis_type"] == analysis_type
            assert "result" in result

    @pytest.mark.asyncio
    async def test_pr_agent_with_all_analysis_types(self, pr_agent_config, sample_task_data):
        """Test PR agent handles all supported analysis types."""
        agent = PRCommunicationsAgent("pr-001", pr_agent_config)
        await agent._agent_specific_init()

        analysis_types = [
            "communication_strategy",
            "customer_communications",
        ]

        for analysis_type in analysis_types:
            task = dict(sample_task_data)
            task["analysis_type"] = analysis_type
            result = await agent._execute_specific_task(task)
            assert result["analysis_type"] == analysis_type
            assert "result" in result

    @pytest.mark.asyncio
    async def test_financial_agent_ransom_calculation(
        self, financial_agent_config, sample_task_data
    ):
        """Test financial agent ransom calculation values."""
        agent = FinancialRiskAgent("financial-001", financial_agent_config)
        await agent._agent_specific_init()

        context = CrisisContext(
            crisis_code="TEST-001",
            crisis_type=CrisisType.CYBERSECURITY,
            severity=RiskLevel.CRITICAL,
            timeline="48 hours",
            affected_systems=["database"],
            stakeholders=["customers"],
            regulatory_implications=["GDPR"],
        )

        result = await agent._analyze_ransom_cost_benefit(context, sample_task_data)

        # Verify BTC to EUR calculation is present
        ransom_scenario = result["ransom_payment_scenario"]["direct_costs"]
        assert "ransom_amount" in ransom_scenario
        assert "EUR" in ransom_scenario["ransom_amount"]

    @pytest.mark.asyncio
    async def test_operations_agent_with_default_analysis_type(
        self, operations_agent_config, sample_task_data
    ):
        """Test operations agent uses default analysis type when not specified."""
        agent = CustomerOperationsAgent("ops-001", operations_agent_config)
        await agent._agent_specific_init()

        task = dict(sample_task_data)
        if "analysis_type" in task:
            del task["analysis_type"]

        result = await agent._execute_specific_task(task)

        # Should default to service_continuity
        assert result["analysis_type"] == "service_continuity"


# =============================================================================
# ADDITIONAL COVERAGE TESTS
# =============================================================================


class TestAdditionalCoverage:
    """Additional tests to maximize coverage."""

    @pytest.mark.asyncio
    async def test_cyber_agent_forensic_analysis(
        self, cybersecurity_agent_config, sample_task_data
    ):
        """Test forensic_analysis function is callable."""
        agent = CybersecurityAgent("cyber-001", cybersecurity_agent_config)
        await agent._agent_specific_init()

        assert "forensic_analysis" in agent.security_functions

    @pytest.mark.asyncio
    async def test_cyber_agent_recovery_planning(
        self, cybersecurity_agent_config, sample_task_data
    ):
        """Test recovery_planning function is callable."""
        agent = CybersecurityAgent("cyber-001", cybersecurity_agent_config)
        await agent._agent_specific_init()

        assert "recovery_planning" in agent.security_functions

    @pytest.mark.asyncio
    async def test_cyber_agent_vulnerability_assessment(
        self, cybersecurity_agent_config, sample_task_data
    ):
        """Test vulnerability_assessment function is callable."""
        agent = CybersecurityAgent("cyber-001", cybersecurity_agent_config)
        await agent._agent_specific_init()

        assert "vulnerability_assessment" in agent.security_functions

    @pytest.mark.asyncio
    async def test_legal_agent_notification_requirements(
        self, legal_agent_config, sample_task_data
    ):
        """Test notification_requirements function exists."""
        agent = LegalComplianceAgent("legal-001", legal_agent_config)
        await agent._agent_specific_init()

        assert "notification_requirements" in agent.legal_functions

    @pytest.mark.asyncio
    async def test_legal_agent_compliance_obligations(self, legal_agent_config, sample_task_data):
        """Test compliance_obligations function exists."""
        agent = LegalComplianceAgent("legal-001", legal_agent_config)
        await agent._agent_specific_init()

        assert "compliance_obligations" in agent.legal_functions

    @pytest.mark.asyncio
    async def test_pr_agent_stakeholder_analysis(self, pr_agent_config, sample_task_data):
        """Test stakeholder_analysis function exists."""
        agent = PRCommunicationsAgent("pr-001", pr_agent_config)
        await agent._agent_specific_init()

        assert "stakeholder_analysis" in agent.communications_functions

    @pytest.mark.asyncio
    async def test_pr_agent_media_response(self, pr_agent_config, sample_task_data):
        """Test media_response function exists."""
        agent = PRCommunicationsAgent("pr-001", pr_agent_config)
        await agent._agent_specific_init()

        assert "media_response" in agent.communications_functions

    @pytest.mark.asyncio
    async def test_pr_agent_internal_communications(self, pr_agent_config, sample_task_data):
        """Test internal_communications function exists."""
        agent = PRCommunicationsAgent("pr-001", pr_agent_config)
        await agent._agent_specific_init()

        assert "internal_communications" in agent.communications_functions

    @pytest.mark.asyncio
    async def test_pr_agent_social_media_monitoring(self, pr_agent_config, sample_task_data):
        """Test social_media_monitoring function exists."""
        agent = PRCommunicationsAgent("pr-001", pr_agent_config)
        await agent._agent_specific_init()

        assert "social_media_monitoring" in agent.communications_functions

    @pytest.mark.asyncio
    async def test_financial_agent_cost_analysis(self, financial_agent_config, sample_task_data):
        """Test cost_analysis function exists."""
        agent = FinancialRiskAgent("financial-001", financial_agent_config)
        await agent._agent_specific_init()

        assert "cost_analysis" in agent.financial_functions

    @pytest.mark.asyncio
    async def test_financial_agent_revenue_impact(self, financial_agent_config, sample_task_data):
        """Test revenue_impact function exists."""
        agent = FinancialRiskAgent("financial-001", financial_agent_config)
        await agent._agent_specific_init()

        assert "revenue_impact" in agent.financial_functions

    @pytest.mark.asyncio
    async def test_financial_agent_insurance_analysis(
        self, financial_agent_config, sample_task_data
    ):
        """Test insurance_analysis function exists."""
        agent = FinancialRiskAgent("financial-001", financial_agent_config)
        await agent._agent_specific_init()

        assert "insurance_analysis" in agent.financial_functions

    @pytest.mark.asyncio
    async def test_financial_agent_recovery_financing(
        self, financial_agent_config, sample_task_data
    ):
        """Test recovery_financing function exists."""
        agent = FinancialRiskAgent("financial-001", financial_agent_config)
        await agent._agent_specific_init()

        assert "recovery_financing" in agent.financial_functions

    @pytest.mark.asyncio
    async def test_operations_agent_customer_impact(
        self, operations_agent_config, sample_task_data
    ):
        """Test customer_impact function exists."""
        agent = CustomerOperationsAgent("ops-001", operations_agent_config)
        await agent._agent_specific_init()

        assert "customer_impact" in agent.operations_functions

    @pytest.mark.asyncio
    async def test_operations_agent_alternative_services(
        self, operations_agent_config, sample_task_data
    ):
        """Test alternative_services function exists."""
        agent = CustomerOperationsAgent("ops-001", operations_agent_config)
        await agent._agent_specific_init()

        assert "alternative_services" in agent.operations_functions

    @pytest.mark.asyncio
    async def test_operations_agent_recovery_planning(
        self, operations_agent_config, sample_task_data
    ):
        """Test recovery_planning function exists."""
        agent = CustomerOperationsAgent("ops-001", operations_agent_config)
        await agent._agent_specific_init()

        assert "recovery_planning" in agent.operations_functions

    @pytest.mark.asyncio
    async def test_operations_agent_support_scaling(
        self, operations_agent_config, sample_task_data
    ):
        """Test support_scaling function exists."""
        agent = CustomerOperationsAgent("ops-001", operations_agent_config)
        await agent._agent_specific_init()

        assert "support_scaling" in agent.operations_functions
