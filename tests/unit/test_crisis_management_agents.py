#!/usr/bin/env python3
"""
Test suite for Crisis Management Agents
Tests 5 specialized crisis response agents: Cybersecurity, Legal, PR, Financial, Operations
Target: 80%+ code coverage
"""

import pytest

from src.core.subagents.agent_factory import AgentConfiguration
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

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
async def crisis_context():
    """Create a standard crisis context"""
    return CrisisContext(
        crisis_code="CRISIS-2025-001",
        crisis_type=CrisisType.CYBERSECURITY,
        severity=RiskLevel.CRITICAL,
        timeline="2025-01-15T10:00:00Z",
        affected_systems=[
            "customer_database",
            "transaction_system",
            "algorithm_service",
        ],
        stakeholders=["customers", "regulators", "board", "employees"],
        regulatory_implications=["GDPR_breach_notification", "PCI_DSS_violation"],
    )


@pytest.fixture
async def financial_crisis_context():
    """Create a financial crisis context"""
    return CrisisContext(
        crisis_code="CRISIS-2025-002",
        crisis_type=CrisisType.FINANCIAL,
        severity=RiskLevel.HIGH,
        timeline="2025-01-14T14:00:00Z",
        affected_systems=["trading_platform", "settlement_system"],
        stakeholders=["investors", "partners", "regulators"],
        regulatory_implications=["financial_market_disruption"],
    )


@pytest.fixture
async def operational_crisis_context():
    """Create an operational crisis context"""
    return CrisisContext(
        crisis_code="CRISIS-2025-003",
        crisis_type=CrisisType.OPERATIONAL,
        severity=RiskLevel.HIGH,
        timeline="2025-01-15T08:00:00Z",
        affected_systems=["order_processing", "inventory_system", "payment_processing"],
        stakeholders=["customers", "staff", "suppliers"],
        regulatory_implications=[],
    )


@pytest.fixture
async def cybersecurity_agent():
    """Create a cybersecurity agent"""
    config = AgentConfiguration(
        agent_type=AgentType.SPECIALIST,
        name="Cybersecurity Crisis Agent",
        capabilities=["incident_analysis", "threat_assessment", "system_isolation"],
        max_concurrent_tasks=5,
        memory_limit_mb=512,
        cpu_priority="high",
        specialized_parameters={"crisis_domain": "cybersecurity"},
    )
    agent = CybersecurityAgent(agent_id="cybersec-001", config=config)
    await agent.initialize()
    return agent


@pytest.fixture
async def legal_agent():
    """Create a legal compliance agent"""
    config = AgentConfiguration(
        agent_type=AgentType.SPECIALIST,
        name="Legal Compliance Agent",
        capabilities=["regulatory_assessment", "liability_analysis"],
        max_concurrent_tasks=5,
        memory_limit_mb=512,
        cpu_priority="high",
        specialized_parameters={"crisis_domain": "legal"},
    )
    agent = LegalComplianceAgent(agent_id="legal-001", config=config)
    await agent.initialize()
    return agent


@pytest.fixture
async def pr_agent():
    """Create a PR communications agent"""
    config = AgentConfiguration(
        agent_type=AgentType.SPECIALIST,
        name="PR Communications Agent",
        capabilities=["stakeholder_analysis", "media_response"],
        max_concurrent_tasks=5,
        memory_limit_mb=512,
        cpu_priority="high",
        specialized_parameters={"crisis_domain": "pr"},
    )
    agent = PRCommunicationsAgent(agent_id="pr-001", config=config)
    await agent.initialize()
    return agent


@pytest.fixture
async def financial_agent():
    """Create a financial risk agent"""
    config = AgentConfiguration(
        agent_type=AgentType.SPECIALIST,
        name="Financial Risk Agent",
        capabilities=["cost_analysis", "revenue_impact"],
        max_concurrent_tasks=5,
        memory_limit_mb=512,
        cpu_priority="high",
        specialized_parameters={"crisis_domain": "financial"},
    )
    agent = FinancialRiskAgent(agent_id="financial-001", config=config)
    await agent.initialize()
    return agent


@pytest.fixture
async def operations_agent():
    """Create a customer operations agent"""
    config = AgentConfiguration(
        agent_type=AgentType.SPECIALIST,
        name="Customer Operations Agent",
        capabilities=["service_continuity", "recovery_planning"],
        max_concurrent_tasks=5,
        memory_limit_mb=512,
        cpu_priority="high",
        specialized_parameters={"crisis_domain": "operations"},
    )
    agent = CustomerOperationsAgent(agent_id="ops-001", config=config)
    await agent.initialize()
    return agent


# ============================================================================
# TEST: ENUMERATIONS
# ============================================================================


class TestCrisisTypeEnum:
    """Test CrisisType enumeration"""

    def test_crisis_type_values(self):
        """Test all crisis type values exist"""
        assert CrisisType.CYBERSECURITY.value == "cybersecurity"
        assert CrisisType.FINANCIAL.value == "financial"
        assert CrisisType.OPERATIONAL.value == "operational"
        assert CrisisType.REPUTATIONAL.value == "reputational"
        assert CrisisType.REGULATORY.value == "regulatory"

    def test_crisis_type_members(self):
        """Test all expected crisis types are defined"""
        members = [e.value for e in CrisisType]
        assert len(members) == 5
        assert "cybersecurity" in members
        assert "financial" in members
        assert "operational" in members
        assert "reputational" in members
        assert "regulatory" in members

    def test_crisis_type_from_value(self):
        """Test accessing crisis types by value"""
        assert CrisisType("cybersecurity") == CrisisType.CYBERSECURITY
        assert CrisisType("financial") == CrisisType.FINANCIAL


class TestRiskLevelEnum:
    """Test RiskLevel enumeration"""

    def test_risk_level_values(self):
        """Test all risk level values exist"""
        assert RiskLevel.LOW.value == "low"
        assert RiskLevel.MEDIUM.value == "medium"
        assert RiskLevel.HIGH.value == "high"
        assert RiskLevel.CRITICAL.value == "critical"

    def test_risk_level_members(self):
        """Test all expected risk levels are defined"""
        members = [e.value for e in RiskLevel]
        assert len(members) == 4


# ============================================================================
# TEST: CRISIS CONTEXT DATACLASS
# ============================================================================


class TestCrisisContext:
    """Test CrisisContext dataclass"""

    def test_crisis_context_creation(self, crisis_context):
        """Test creating a crisis context"""
        assert crisis_context.crisis_code == "CRISIS-2025-001"
        assert crisis_context.crisis_type == CrisisType.CYBERSECURITY
        assert crisis_context.severity == RiskLevel.CRITICAL

    def test_crisis_context_fields(self, crisis_context):
        """Test all crisis context fields"""
        assert hasattr(crisis_context, "crisis_code")
        assert hasattr(crisis_context, "crisis_type")
        assert hasattr(crisis_context, "severity")
        assert hasattr(crisis_context, "timeline")
        assert hasattr(crisis_context, "affected_systems")
        assert hasattr(crisis_context, "stakeholders")
        assert hasattr(crisis_context, "regulatory_implications")

    def test_crisis_context_lists(self, crisis_context):
        """Test crisis context list fields"""
        assert len(crisis_context.affected_systems) > 0
        assert len(crisis_context.stakeholders) > 0
        assert isinstance(crisis_context.affected_systems, list)
        assert isinstance(crisis_context.stakeholders, list)


# ============================================================================
# TEST: CYBERSECURITY AGENT
# ============================================================================


class TestCybersecurityAgent:
    """Test CybersecurityAgent"""

    @pytest.mark.asyncio
    async def test_agent_initialization(self, cybersecurity_agent):
        """Test agent initializes correctly"""
        assert cybersecurity_agent.agent_id == "cybersec-001"
        assert cybersecurity_agent.config.name == "Cybersecurity Crisis Agent"
        assert hasattr(cybersecurity_agent, "security_functions")
        assert len(cybersecurity_agent.security_functions) > 0

    @pytest.mark.asyncio
    async def test_security_functions_available(self, cybersecurity_agent):
        """Test all security functions are registered"""
        expected_functions = [
            "incident_analysis",
            "threat_assessment",
            "system_isolation",
            "forensic_analysis",
            "recovery_planning",
            "vulnerability_assessment",
        ]
        for func_name in expected_functions:
            assert func_name in cybersecurity_agent.security_functions

    @pytest.mark.asyncio
    async def test_analyze_incident(self, cybersecurity_agent, crisis_context):
        """Test incident analysis execution"""
        task_data = {
            "crisis_context": {
                "crisis_code": crisis_context.crisis_code,
                "crisis_type": crisis_context.crisis_type,
                "severity": crisis_context.severity,
                "timeline": crisis_context.timeline,
                "affected_systems": crisis_context.affected_systems,
                "stakeholders": crisis_context.stakeholders,
                "regulatory_implications": crisis_context.regulatory_implications,
            },
            "analysis_type": "incident_analysis",
        }
        result = await cybersecurity_agent._execute_specific_task(task_data)
        assert result["agent_type"] == "cybersecurity"
        assert result["analysis_type"] == "incident_analysis"
        assert "result" in result
        assert "timestamp" in result

    @pytest.mark.asyncio
    async def test_threat_assessment(self, cybersecurity_agent, crisis_context):
        """Test threat assessment"""
        task_data = {
            "crisis_context": {
                "crisis_code": crisis_context.crisis_code,
                "crisis_type": crisis_context.crisis_type,
                "severity": crisis_context.severity,
                "timeline": crisis_context.timeline,
                "affected_systems": crisis_context.affected_systems,
                "stakeholders": crisis_context.stakeholders,
                "regulatory_implications": crisis_context.regulatory_implications,
            },
            "analysis_type": "threat_assessment",
        }
        result = await cybersecurity_agent._execute_specific_task(task_data)
        assert result["analysis_type"] == "threat_assessment"
        assert "result" in result
        assert "current_threat_level" in result["result"]

    @pytest.mark.asyncio
    async def test_system_isolation(self, cybersecurity_agent, crisis_context):
        """Test system isolation recommendations"""
        task_data = {
            "crisis_context": {
                "crisis_code": crisis_context.crisis_code,
                "crisis_type": crisis_context.crisis_type,
                "severity": crisis_context.severity,
                "timeline": crisis_context.timeline,
                "affected_systems": crisis_context.affected_systems,
                "stakeholders": crisis_context.stakeholders,
                "regulatory_implications": crisis_context.regulatory_implications,
            },
            "analysis_type": "system_isolation",
        }
        result = await cybersecurity_agent._execute_specific_task(task_data)
        assert result["analysis_type"] == "system_isolation"
        assert "isolation_strategy" in result["result"]

    @pytest.mark.asyncio
    async def test_forensic_analysis(self, cybersecurity_agent, crisis_context):
        """Test forensic analysis"""
        task_data = {
            "crisis_context": {
                "crisis_code": crisis_context.crisis_code,
                "crisis_type": crisis_context.crisis_type,
                "severity": crisis_context.severity,
                "timeline": crisis_context.timeline,
                "affected_systems": crisis_context.affected_systems,
                "stakeholders": crisis_context.stakeholders,
                "regulatory_implications": crisis_context.regulatory_implications,
            },
            "analysis_type": "forensic_analysis",
        }
        result = await cybersecurity_agent._execute_specific_task(task_data)
        assert result["analysis_type"] == "forensic_analysis"
        assert "forensic_analysis" in result["result"]

    @pytest.mark.asyncio
    async def test_recovery_planning(self, cybersecurity_agent, crisis_context):
        """Test recovery planning"""
        task_data = {
            "crisis_context": {
                "crisis_code": crisis_context.crisis_code,
                "crisis_type": crisis_context.crisis_type,
                "severity": crisis_context.severity,
                "timeline": crisis_context.timeline,
                "affected_systems": crisis_context.affected_systems,
                "stakeholders": crisis_context.stakeholders,
                "regulatory_implications": crisis_context.regulatory_implications,
            },
            "analysis_type": "recovery_planning",
        }
        result = await cybersecurity_agent._execute_specific_task(task_data)
        assert result["analysis_type"] == "recovery_planning"
        assert "recovery_plan" in result["result"]

    @pytest.mark.asyncio
    async def test_vulnerability_assessment(self, cybersecurity_agent, crisis_context):
        """Test vulnerability assessment"""
        task_data = {
            "crisis_context": {
                "crisis_code": crisis_context.crisis_code,
                "crisis_type": crisis_context.crisis_type,
                "severity": crisis_context.severity,
                "timeline": crisis_context.timeline,
                "affected_systems": crisis_context.affected_systems,
                "stakeholders": crisis_context.stakeholders,
                "regulatory_implications": crisis_context.regulatory_implications,
            },
            "analysis_type": "vulnerability_assessment",
        }
        result = await cybersecurity_agent._execute_specific_task(task_data)
        assert result["analysis_type"] == "vulnerability_assessment"
        assert "vulnerability_assessment" in result["result"]


# ============================================================================
# TEST: LEGAL COMPLIANCE AGENT
# ============================================================================


class TestLegalComplianceAgent:
    """Test LegalComplianceAgent"""

    @pytest.mark.asyncio
    async def test_agent_initialization(self, legal_agent):
        """Test agent initializes correctly"""
        assert legal_agent.agent_id == "legal-001"
        assert legal_agent.config.name == "Legal Compliance Agent"
        assert hasattr(legal_agent, "legal_functions")

    @pytest.mark.asyncio
    async def test_legal_functions_available(self, legal_agent):
        """Test all legal functions are registered"""
        expected_functions = [
            "regulatory_assessment",
            "liability_analysis",
            "notification_requirements",
            "ransom_payment_analysis",
            "compliance_obligations",
        ]
        for func_name in expected_functions:
            assert func_name in legal_agent.legal_functions

    @pytest.mark.asyncio
    async def test_regulatory_assessment(self, legal_agent, crisis_context):
        """Test regulatory assessment"""
        task_data = {
            "crisis_context": {
                "crisis_code": crisis_context.crisis_code,
                "crisis_type": crisis_context.crisis_type,
                "severity": crisis_context.severity,
                "timeline": crisis_context.timeline,
                "affected_systems": crisis_context.affected_systems,
                "stakeholders": crisis_context.stakeholders,
                "regulatory_implications": crisis_context.regulatory_implications,
            },
            "analysis_type": "regulatory_assessment",
        }
        result = await legal_agent._execute_specific_task(task_data)
        assert result["agent_type"] == "legal_compliance"
        assert result["analysis_type"] == "regulatory_assessment"


# ============================================================================
# TEST: PR COMMUNICATIONS AGENT
# ============================================================================


class TestPRCommunicationsAgent:
    """Test PRCommunicationsAgent"""

    @pytest.mark.asyncio
    async def test_agent_initialization(self, pr_agent):
        """Test agent initializes correctly"""
        assert pr_agent.agent_id == "pr-001"
        assert pr_agent.config.name == "PR Communications Agent"
        assert hasattr(pr_agent, "communications_functions")

    @pytest.mark.asyncio
    async def test_communications_functions_available(self, pr_agent):
        """Test all communication functions are registered"""
        expected_functions = [
            "stakeholder_analysis",
            "communication_strategy",
            "media_response",
            "customer_communications",
            "internal_communications",
            "social_media_monitoring",
        ]
        for func_name in expected_functions:
            assert func_name in pr_agent.communications_functions

    @pytest.mark.asyncio
    async def test_communication_strategy(self, pr_agent, crisis_context):
        """Test communication strategy development"""
        task_data = {
            "crisis_context": {
                "crisis_code": crisis_context.crisis_code,
                "crisis_type": crisis_context.crisis_type,
                "severity": crisis_context.severity,
                "timeline": crisis_context.timeline,
                "affected_systems": crisis_context.affected_systems,
                "stakeholders": crisis_context.stakeholders,
                "regulatory_implications": crisis_context.regulatory_implications,
            },
            "analysis_type": "communication_strategy",
        }
        result = await pr_agent._execute_specific_task(task_data)
        assert result["agent_type"] == "pr_communications"
        assert result["analysis_type"] == "communication_strategy"


# ============================================================================
# TEST: FINANCIAL RISK AGENT
# ============================================================================


class TestFinancialRiskAgent:
    """Test FinancialRiskAgent"""

    @pytest.mark.asyncio
    async def test_agent_initialization(self, financial_agent):
        """Test agent initializes correctly"""
        assert financial_agent.agent_id == "financial-001"
        assert financial_agent.config.name == "Financial Risk Agent"
        assert hasattr(financial_agent, "financial_functions")

    @pytest.mark.asyncio
    async def test_financial_functions_available(self, financial_agent):
        """Test all financial functions are registered"""
        expected_functions = [
            "cost_analysis",
            "revenue_impact",
            "insurance_analysis",
            "ransom_cost_benefit",
            "recovery_financing",
        ]
        for func_name in expected_functions:
            assert func_name in financial_agent.financial_functions

    @pytest.mark.asyncio
    async def test_cost_analysis(self, financial_agent, crisis_context):
        """Test cost analysis"""
        task_data = {
            "crisis_context": {
                "crisis_code": crisis_context.crisis_code,
                "crisis_type": crisis_context.crisis_type,
                "severity": crisis_context.severity,
                "timeline": crisis_context.timeline,
                "affected_systems": crisis_context.affected_systems,
                "stakeholders": crisis_context.stakeholders,
                "regulatory_implications": crisis_context.regulatory_implications,
            },
            "analysis_type": "cost_analysis",
        }
        result = await financial_agent._execute_specific_task(task_data)
        assert result["agent_type"] == "financial_risk"
        assert result["analysis_type"] == "cost_analysis"

    @pytest.mark.asyncio
    async def test_ransom_cost_benefit_analysis(self, financial_agent, crisis_context):
        """Test ransom cost benefit analysis"""
        task_data = {
            "crisis_context": {
                "crisis_code": crisis_context.crisis_code,
                "crisis_type": crisis_context.crisis_type,
                "severity": crisis_context.severity,
                "timeline": crisis_context.timeline,
                "affected_systems": crisis_context.affected_systems,
                "stakeholders": crisis_context.stakeholders,
                "regulatory_implications": crisis_context.regulatory_implications,
            },
            "analysis_type": "ransom_cost_benefit",
        }
        result = await financial_agent._execute_specific_task(task_data)
        assert result["agent_type"] == "financial_risk"
        assert "ransom_payment_scenario" in result["result"]
        assert "recovery_without_payment_scenario" in result["result"]


# ============================================================================
# TEST: CUSTOMER OPERATIONS AGENT
# ============================================================================


class TestCustomerOperationsAgent:
    """Test CustomerOperationsAgent"""

    @pytest.mark.asyncio
    async def test_agent_initialization(self, operations_agent):
        """Test agent initializes correctly"""
        assert operations_agent.agent_id == "ops-001"
        assert operations_agent.config.name == "Customer Operations Agent"
        assert hasattr(operations_agent, "operations_functions")

    @pytest.mark.asyncio
    async def test_operations_functions_available(self, operations_agent):
        """Test all operations functions are registered"""
        expected_functions = [
            "service_continuity",
            "customer_impact",
            "alternative_services",
            "recovery_planning",
            "support_scaling",
        ]
        for func_name in expected_functions:
            assert func_name in operations_agent.operations_functions

    @pytest.mark.asyncio
    async def test_service_continuity(self, operations_agent, crisis_context):
        """Test service continuity assessment"""
        task_data = {
            "crisis_context": {
                "crisis_code": crisis_context.crisis_code,
                "crisis_type": crisis_context.crisis_type,
                "severity": crisis_context.severity,
                "timeline": crisis_context.timeline,
                "affected_systems": crisis_context.affected_systems,
                "stakeholders": crisis_context.stakeholders,
                "regulatory_implications": crisis_context.regulatory_implications,
            },
            "analysis_type": "service_continuity",
        }
        result = await operations_agent._execute_specific_task(task_data)
        assert result["agent_type"] == "customer_operations"
        assert result["analysis_type"] == "service_continuity"


# ============================================================================
# TEST: MULTI-AGENT INTEGRATION
# ============================================================================


class TestCrisisManagementIntegration:
    """Test multi-agent crisis management coordination"""

    @pytest.mark.asyncio
    async def test_multi_agent_execution(
        self,
        cybersecurity_agent,
        legal_agent,
        pr_agent,
        financial_agent,
        operations_agent,
        crisis_context,
    ):
        """Test all agents can execute in coordinated manner"""
        agents = [
            (cybersecurity_agent, "incident_analysis"),
            (legal_agent, "regulatory_assessment"),
            (pr_agent, "communication_strategy"),
            (financial_agent, "cost_analysis"),
            (operations_agent, "service_continuity"),
        ]

        results = []
        for agent, analysis_type in agents:
            task_data = {
                "crisis_context": {
                    "crisis_code": crisis_context.crisis_code,
                    "crisis_type": crisis_context.crisis_type,
                    "severity": crisis_context.severity,
                    "timeline": crisis_context.timeline,
                    "affected_systems": crisis_context.affected_systems,
                    "stakeholders": crisis_context.stakeholders,
                    "regulatory_implications": crisis_context.regulatory_implications,
                },
                "analysis_type": analysis_type,
            }
            result = await agent._execute_specific_task(task_data)
            results.append(result)

        # Verify all agents executed successfully
        assert len(results) == 5
        for result in results:
            assert result is not None
            assert "timestamp" in result


# ============================================================================
# TEST: EDGE CASES
# ============================================================================


class TestCrisisManagementEdgeCases:
    """Test edge cases and boundary conditions"""

    def test_empty_affected_systems(self):
        """Test crisis context with empty systems list"""
        context = CrisisContext(
            crisis_code="CRISIS-EMPTY",
            crisis_type=CrisisType.OPERATIONAL,
            severity=RiskLevel.LOW,
            timeline="2025-01-15T00:00:00Z",
            affected_systems=[],
            stakeholders=["management"],
            regulatory_implications=[],
        )
        assert len(context.affected_systems) == 0

    def test_crisis_type_string_conversion(self):
        """Test converting crisis type to string"""
        for crisis_type in CrisisType:
            assert isinstance(crisis_type.value, str)
            assert len(crisis_type.value) > 0

    def test_risk_level_string_conversion(self):
        """Test converting risk level to string"""
        for risk_level in RiskLevel:
            assert isinstance(risk_level.value, str)
            assert len(risk_level.value) > 0
