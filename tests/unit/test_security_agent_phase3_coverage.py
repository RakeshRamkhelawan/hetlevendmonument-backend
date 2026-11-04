"""
Unit Tests for src/core/agents/security_agent.py - Phase 3 Coverage Expansion
Target: 80%+ coverage with happy path, edge cases, error handling
"""

from datetime import datetime
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.agents.security_agent import SecurityAgent, create_security_agent
from src.core.shared.interfaces import AgentCapability, AgentType, ExecutionResult, TaskData
from src.core.shared.llm_client import LLMMessage, LLMResponse


class TestSecurityAgentInitialization:
    """Test SecurityAgent initialization and setup"""

    def test_security_agent_initialization_default_id(self):
        """Test: SecurityAgent initializes with default agent_id"""
        agent = SecurityAgent()

        assert agent.agent_id == "security_agent_001"
        assert agent.agent_type == AgentType.SPECIALIST
        assert agent.specialization == "cybersecurity_compliance"
        assert len(agent.security_domains) == 8
        assert len(agent.compliance_frameworks) == 6

    def test_security_agent_initialization_custom_id(self):
        """Test: SecurityAgent initializes with custom agent_id"""
        custom_id = "security_agent_custom_123"
        agent = SecurityAgent(agent_id=custom_id)

        assert agent.agent_id == custom_id
        assert agent.agent_type == AgentType.SPECIALIST

    def test_security_agent_has_risk_levels(self):
        """Test: SecurityAgent has proper risk level configuration"""
        agent = SecurityAgent()

        assert "CRITICAL" in agent.risk_levels
        assert agent.risk_levels["CRITICAL"]["score"] == 9
        assert agent.risk_levels["HIGH"]["score"] == 7
        assert agent.risk_levels["MEDIUM"]["score"] == 5
        assert agent.risk_levels["LOW"]["score"] == 3
        assert agent.risk_levels["MINIMAL"]["score"] == 1

    def test_security_agent_has_security_domains(self):
        """Test: SecurityAgent has all required security domains"""
        agent = SecurityAgent()

        expected_domains = [
            "vulnerability_assessment",
            "risk_analysis",
            "compliance_audit",
            "threat_modeling",
            "security_testing",
            "incident_response",
            "access_control",
            "data_protection",
        ]

        for domain in expected_domains:
            assert domain in agent.security_domains

    def test_security_agent_has_compliance_frameworks(self):
        """Test: SecurityAgent supports major compliance frameworks"""
        agent = SecurityAgent()

        expected_frameworks = ["ISO27001", "GDPR", "SOC2", "PCI-DSS", "HIPAA", "NIST"]

        for framework in expected_frameworks:
            assert framework in agent.compliance_frameworks

    @pytest.mark.asyncio
    async def test_security_agent_initialize_success(self):
        """Test: SecurityAgent initialize creates LLM client"""
        agent = SecurityAgent()

        with patch("src.core.agents.security_agent.TenantTaalmodel") as mock_create_client:
            mock_client = MagicMock()
            mock_create_client.return_value = mock_client

            result = await agent.initialize()

            assert result is True
            assert agent.llm_client is mock_client
            mock_create_client.assert_called_once_with(agent.tenant_id)

    @pytest.mark.asyncio
    async def test_security_agent_initialize_failure(self):
        """Een storing bij het opvragen van het tenantmodel laat initialize mislukken zonder client."""
        agent = SecurityAgent()

        with patch(
            "src.core.agents.security_agent.TenantTaalmodel",
            side_effect=Exception("LLM unavailable"),
        ):
            result = await agent.initialize()

            assert result is False
            assert agent.llm_client is None


class TestSecurityAgentCapabilities:
    """Test SecurityAgent capabilities"""

    @pytest.mark.asyncio
    async def test_get_capabilities_returns_all_capabilities(self):
        """Test: get_capabilities returns all 8 security capabilities"""
        agent = SecurityAgent()

        capabilities = await agent.get_capabilities()

        assert len(capabilities) == 8
        assert all(isinstance(cap, AgentCapability) for cap in capabilities)

    @pytest.mark.asyncio
    async def test_get_capabilities_includes_vulnerability_assessment(self):
        """Test: Capabilities include vulnerability_assessment"""
        agent = SecurityAgent()

        capabilities = await agent.get_capabilities()
        capability_names = [cap.name for cap in capabilities]

        assert "vulnerability_assessment" in capability_names

    @pytest.mark.asyncio
    async def test_get_capabilities_includes_all_expected(self):
        """Test: Capabilities include all expected security functions"""
        agent = SecurityAgent()

        expected_capabilities = [
            "vulnerability_assessment",
            "risk_analysis",
            "compliance_audit",
            "threat_modeling",
            "code_security_review",
            "security_testing",
            "incident_response",
            "access_control_analysis",
        ]

        capabilities = await agent.get_capabilities()
        capability_names = [cap.name for cap in capabilities]

        for expected in expected_capabilities:
            assert expected in capability_names


class TestSecurityAgentTaskProcessing:
    """Test SecurityAgent task processing"""

    @pytest.mark.asyncio
    async def test_process_task_is_not_overridden_by_subclass(self):
        """SecurityAgent must NOT override process_task() -- doing so would bypass
        EnhancedBaseAgent's governance pipeline (GDPR opt-out, EU-AI-006
        governance-contract check, prompt-injection sanitisation). process_task must
        stay the inherited base-class template method, which itself calls
        _execute_task() (the real business logic, tested separately below)."""
        from src.core.agents.base_agent import EnhancedBaseAgent

        assert SecurityAgent.process_task is EnhancedBaseAgent.process_task

    @pytest.mark.asyncio
    async def test_process_task_vulnerability_assessment(self):
        """Test: process_task routes vulnerability_assessment correctly"""
        agent = SecurityAgent()
        agent.llm_client = MagicMock()

        task = TaskData(
            id="task_001",
            title="Vulnerability Assessment",
            description="Assess vulnerabilities",
            metadata={"type": "vulnerability_assessment", "framework": "OWASP"},
        )

        with patch.object(
            agent, "_process_vulnerability_assessment", new_callable=AsyncMock
        ) as mock_process:
            mock_process.return_value = {"vulnerabilities_found": []}

            result = await agent.process_task(task)

            mock_process.assert_called_once_with(task)
            assert result.success is True
            assert result.result_data["agent_type"] == "security_agent"

    @pytest.mark.asyncio
    async def test_process_task_handles_errors(self):
        """Test: process_task handles processing errors gracefully"""
        agent = SecurityAgent()
        agent.llm_client = MagicMock()

        task = TaskData(
            id="task_001",
            title="Test Task",
            description="Test description",
            metadata={"type": "vulnerability_assessment"},
        )

        with patch.object(
            agent,
            "_process_vulnerability_assessment",
            side_effect=Exception("Processing error"),
        ):
            result = await agent.process_task(task)

            assert result.success is False
            assert "Processing error" in result.error_message
            assert result.task_id == task.id


class TestVulnerabilityAssessment:
    """Test vulnerability assessment functionality"""

    @pytest.mark.asyncio
    async def test_process_vulnerability_assessment_with_code(self):
        """Test: Vulnerability assessment processes code content"""
        agent = SecurityAgent()
        mock_client = AsyncMock()
        mock_response = LLMResponse(
            content="Critical vulnerability: SQL injection in login function",
            model="claude-3",
            provider="anthropic",
            usage={"input_tokens": 100, "output_tokens": 50},
        )
        mock_client.chat_completion = AsyncMock(return_value=mock_response)
        agent.llm_client = mock_client

        task = TaskData(
            id="task_001",
            title="Code Vulnerability Scan",
            description="Scan for vulnerabilities",
            metadata={
                "target_type": "code",
                "code": "SELECT * FROM users WHERE username = '" + "user_input" + "'",
                "system_info": "",
            },
        )

        result = await agent._process_vulnerability_assessment(task)

        assert result["target_type"] == "code"
        assert "assessment_results" in result
        assert "vulnerabilities_found" in result
        assert "risk_score" in result
        mock_client.chat_completion.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_vulnerability_assessment_with_system_info(self):
        """Test: Vulnerability assessment processes system information"""
        agent = SecurityAgent()
        mock_client = AsyncMock()
        mock_response = LLMResponse(
            content="Medium risk: Outdated SSL/TLS configuration",
            model="claude-3",
            provider="anthropic",
            usage={"input_tokens": 100, "output_tokens": 50},
        )
        mock_client.chat_completion = AsyncMock(return_value=mock_response)
        agent.llm_client = mock_client

        task = TaskData(
            id="task_002",
            title="System Vulnerability Assessment",
            description="Assess system vulnerabilities",
            metadata={
                "target_type": "system",
                "system_info": "Ubuntu 20.04 with Apache 2.4",
                "code": "",
            },
        )

        result = await agent._process_vulnerability_assessment(task)

        assert result["target_type"] == "system"
        assert isinstance(result["vulnerabilities_found"], list)


class TestRiskAnalysis:
    """Test risk analysis functionality"""

    @pytest.mark.asyncio
    async def test_process_risk_analysis_with_assets(self):
        """Test: Risk analysis processes assets and threats"""
        agent = SecurityAgent()
        mock_client = AsyncMock()
        mock_response = LLMResponse(
            content="High risk: Customer database exposed to internet",
            model="claude-3",
            provider="anthropic",
            usage={"input_tokens": 100, "output_tokens": 50},
        )
        mock_client.chat_completion = AsyncMock(return_value=mock_response)
        agent.llm_client = mock_client

        task = TaskData(
            id="task_003",
            title="Risk Analysis",
            description="Analyze security risks",
            metadata={
                "domain": "data_security",
                "assets": ["customer_database", "api_keys"],
                "threats": ["data_breach", "unauthorized_access"],
            },
        )

        result = await agent._process_risk_analysis(task)

        assert result["risk_domain"] == "data_security"
        assert "risk_analysis" in result
        assert "identified_risks" in result
        assert "overall_risk_level" in result
        mock_client.chat_completion.assert_called_once()


class TestComplianceAudit:
    """Test compliance audit functionality"""

    @pytest.mark.asyncio
    async def test_process_compliance_audit_with_framework(self):
        """Test: Compliance audit processes framework requirements"""
        agent = SecurityAgent()
        mock_client = AsyncMock()
        mock_response = LLMResponse(
            content="ISO27001 compliance: Gap in access control policies",
            model="claude-3",
            provider="anthropic",
            usage={"input_tokens": 100, "output_tokens": 50},
        )
        mock_client.chat_completion = AsyncMock(return_value=mock_response)
        agent.llm_client = mock_client
        agent._extract_compliance_findings = MagicMock(return_value=[])
        agent._identify_compliance_gaps = MagicMock(return_value=[])
        agent._calculate_compliance_score = MagicMock(return_value=85.0)
        agent._generate_remediation_timeline = MagicMock(return_value={})
        agent._calculate_next_audit_date = MagicMock(return_value="2026-03-01")
        agent._assess_certification_readiness = MagicMock(return_value="ready")

        task = TaskData(
            id="task_004",
            title="ISO27001 Audit",
            description="Audit ISO27001 compliance",
            metadata={
                "framework": "ISO27001",
                "scope": "full_audit",
                "controls": {"access_control": "partial", "encryption": "compliant"},
            },
        )

        result = await agent._process_compliance_audit(task)

        assert result["framework"] == "ISO27001"
        assert result["audit_scope"] == "full_audit"
        assert "compliance_findings" in result
        assert "identified_gaps" in result
        mock_client.chat_completion.assert_called_once()


class TestThreatModeling:
    """Test threat modeling functionality"""

    @pytest.mark.asyncio
    async def test_process_threat_modeling_with_architecture(self):
        """Test: Threat modeling processes system architecture"""
        agent = SecurityAgent()
        mock_client = AsyncMock()
        mock_response = LLMResponse(
            content="STRIDE analysis: Spoofing risk in authentication flow",
            model="claude-3",
            provider="anthropic",
            usage={"input_tokens": 100, "output_tokens": 50},
        )
        mock_client.chat_completion = AsyncMock(return_value=mock_response)
        agent.llm_client = mock_client
        agent._extract_threats = MagicMock(return_value=[])
        agent._extract_attack_vectors = MagicMock(return_value=[])
        agent._categorize_by_stride = MagicMock(return_value={})
        agent._generate_countermeasures = MagicMock(return_value=[])

        task = TaskData(
            id="task_005",
            title="Threat Model",
            description="Model threats for web application",
            metadata={
                "architecture": "microservices",
                "attack_surface": "web_application",
                "threat_actors": ["script_kiddie", "organized_crime"],
            },
        )

        result = await agent._process_threat_modeling(task)

        assert result["attack_surface"] == "web_application"
        assert "threat_model" in result
        assert "identified_threats" in result
        assert "attack_vectors" in result
        mock_client.chat_completion.assert_called_once()


class TestCodeSecurityReview:
    """Test code security review functionality"""

    @pytest.mark.asyncio
    async def test_process_code_security_review_with_code(self):
        """Test: Code security review processes code content"""
        agent = SecurityAgent()
        mock_client = AsyncMock()
        mock_response = LLMResponse(
            content="Security issue: Hardcoded credentials detected",
            model="claude-3",
            provider="anthropic",
            usage={"input_tokens": 100, "output_tokens": 50},
        )
        mock_client.chat_completion = AsyncMock(return_value=mock_response)
        agent.llm_client = mock_client
        agent._extract_security_issues = MagicMock(return_value=[])
        agent._map_to_owasp_top10 = MagicMock(return_value={})
        agent._prioritize_remediations = MagicMock(return_value=[])
        agent._calculate_security_score = MagicMock(return_value=75.0)

        task = TaskData(
            id="task_006",
            title="Code Security Review",
            description="Review code for security issues",
            metadata={
                "code": "password = 'admin123'",
                "language": "python",
                "focus": "authentication",
            },
        )

        result = await agent._process_code_security_review(task)

        assert result["language"] == "python"
        assert result["security_focus"] == "authentication"
        assert "security_issues" in result
        assert "owasp_top10_mapping" in result
        mock_client.chat_completion.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_code_security_review_no_code_fails(self):
        """Test: Code security review fails without code"""
        agent = SecurityAgent()

        task = TaskData(
            id="task_007",
            title="Code Security Review",
            description="Review code",
            metadata={"language": "python"},
        )

        result = await agent._process_code_security_review(task)

        assert "error" in result
        assert result["status"] == "failed"


class TestSecurityTesting:
    """Test security testing functionality"""

    @pytest.mark.asyncio
    async def test_process_security_testing_penetration_test(self):
        """Test: Security testing processes penetration test plans"""
        agent = SecurityAgent()
        mock_client = AsyncMock()
        mock_response = LLMResponse(
            content="Penetration testing plan: Network scanning and exploitation",
            model="claude-3",
            provider="anthropic",
            usage={"input_tokens": 100, "output_tokens": 50},
        )
        mock_client.chat_completion = AsyncMock(return_value=mock_response)
        agent.llm_client = mock_client
        agent._extract_testing_phases = MagicMock(return_value=[])
        agent._extract_testing_tools = MagicMock(return_value=[])
        agent._estimate_testing_duration = MagicMock(return_value="2 weeks")

        task = TaskData(
            id="task_008",
            title="Penetration Test Plan",
            description="Design penetration test",
            metadata={"test_type": "penetration_testing", "target": "web_application"},
        )

        result = await agent._process_security_testing(task)

        assert result["test_type"] == "penetration_testing"
        assert result["target_system"] == "web_application"
        assert "testing_plan" in result
        assert "required_tools" in result
        mock_client.chat_completion.assert_called_once()


class TestIncidentResponse:
    """Test incident response functionality"""

    @pytest.mark.asyncio
    async def test_process_incident_response_security_breach(self):
        """Test: Incident response handles security breach"""
        agent = SecurityAgent()
        mock_client = AsyncMock()
        mock_response = LLMResponse(
            content="Immediate containment: Isolate affected systems",
            model="claude-3",
            provider="anthropic",
            usage={"input_tokens": 100, "output_tokens": 50},
        )
        mock_client.chat_completion = AsyncMock(return_value=mock_response)
        agent.llm_client = mock_client
        agent._extract_immediate_actions = MagicMock(return_value=[])
        agent._extract_investigation_steps = MagicMock(return_value=[])
        agent._estimate_recovery_timeline = MagicMock(return_value="24-48 hours")
        agent._determine_notifications = MagicMock(return_value=[])
        agent._define_escalation_triggers = MagicMock(return_value=[])

        task = TaskData(
            id="task_009",
            title="Security Breach Response",
            description="Respond to data breach",
            metadata={
                "incident_type": "data_breach",
                "severity": "high",
                "affected_systems": ["database_server", "api_gateway"],
            },
        )

        result = await agent._process_incident_response(task)

        assert result["incident_type"] == "data_breach"
        assert result["severity"] == "high"
        assert "response_plan" in result
        assert "immediate_actions" in result
        assert result["follow_up_required"] is True
        mock_client.chat_completion.assert_called_once()


class TestHelperMethods:
    """Test helper methods"""

    def test_extract_vulnerabilities_from_text(self):
        """Test: Extract vulnerabilities from assessment text"""
        agent = SecurityAgent()

        text = """
        Critical vulnerability: SQL injection in login function
        High severity: XSS in user profile
        Low risk: Information disclosure in error messages
        """

        vulnerabilities = agent._extract_vulnerabilities(text)

        assert len(vulnerabilities) > 0
        assert any(v["severity"] == "critical" for v in vulnerabilities)

    def test_calculate_risk_score_high_risk(self):
        """Test: Calculate risk score for high-risk assessment"""
        agent = SecurityAgent()

        text = "Critical vulnerability found. High risk of exploitation. Critical issue with authentication. Critical security flaw detected. High severity issue. High priority fix required."

        score = agent._calculate_risk_score(text)

        assert score >= 4.0
        assert score <= 10.0

    def test_calculate_risk_score_low_risk(self):
        """Test: Calculate risk score for low-risk assessment"""
        agent = SecurityAgent()

        text = "No critical issues. Low risk. System appears secure."

        score = agent._calculate_risk_score(text)

        assert score >= 0.0
        assert score < 5.0

    def test_calculate_overall_risk_critical(self):
        """Test: Calculate overall risk returns CRITICAL level"""
        agent = SecurityAgent()

        result = {"risk_score": 9.0}

        risk = agent._calculate_overall_risk(result)

        assert risk["level"] == "CRITICAL"
        assert risk["recommendation"] == "immediate_action"

    def test_calculate_overall_risk_low(self):
        """Test: Calculate overall risk returns LOW level"""
        agent = SecurityAgent()

        result = {"risk_score": 3.0}

        risk = agent._calculate_overall_risk(result)

        assert risk["level"] == "LOW"
        assert risk["recommendation"] == "planned_remediation"

    def test_categorize_by_severity(self):
        """Test: Categorize vulnerabilities by severity"""
        agent = SecurityAgent()

        vulnerabilities = [
            {"severity": "critical", "description": "SQL injection"},
            {"severity": "high", "description": "XSS"},
            {"severity": "medium", "description": "CSRF"},
            {"severity": "low", "description": "Info disclosure"},
        ]

        categories = agent._categorize_by_severity(vulnerabilities)

        assert categories["critical"] == 1
        assert categories["high"] == 1
        assert categories["medium"] == 1
        assert categories["low"] == 1

    def test_assess_compliance_impact_non_compliant(self):
        """Test: Assess compliance impact with critical vulnerabilities"""
        agent = SecurityAgent()

        vulnerabilities = [{"severity": "critical", "description": "Data breach risk"}]

        impact = agent._assess_compliance_impact(vulnerabilities)

        assert impact == "non_compliant"

    def test_assess_compliance_impact_compliant(self):
        """Test: Assess compliance impact with few vulnerabilities"""
        agent = SecurityAgent()

        vulnerabilities = [{"severity": "low", "description": "Minor issue"}]

        impact = agent._assess_compliance_impact(vulnerabilities)

        assert impact == "compliant"


class TestFactoryFunction:
    """Test factory function"""

    @pytest.mark.asyncio
    async def test_create_security_agent_with_default_id(self):
        """Test: Factory creates agent with generated ID"""
        with patch("src.core.agents.security_agent.TenantTaalmodel"):
            agent = await create_security_agent()

            assert agent is not None
            assert isinstance(agent, SecurityAgent)
            assert "security_agent_" in agent.agent_id

    @pytest.mark.asyncio
    async def test_create_security_agent_with_custom_id(self):
        """Test: Factory creates agent with custom ID"""
        custom_id = "security_agent_custom"

        with patch("src.core.agents.security_agent.TenantTaalmodel"):
            agent = await create_security_agent(agent_id=custom_id)

            assert agent.agent_id == custom_id
