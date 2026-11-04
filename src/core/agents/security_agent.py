"""
Security Agent Implementation
Specialist agent for security analysis, risk assessment, and compliance checks
"""

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional, TypedDict

from src.core.agents.base_agent import EnhancedBaseAgent
from src.core.agents.mixins.critic_mixin import CriticMixin, CriticMode
from src.core.shared.interfaces import AgentCapability, AgentType, ExecutionResult, TaskData
from src.core.services.llm.tenant_deur import TenantTaalmodel
from src.core.shared.llm_client import ChatTaalmodel, LLMMessage


class RiskItem(TypedDict):
    title: str
    description: str
    severity: str
    likelihood: int
    impact: int
    risk_score: int


class RiskMatrix(TypedDict):
    critical: list[RiskItem]
    high: list[RiskItem]
    medium: list[RiskItem]
    low: list[RiskItem]
    matrix_distribution: dict[str, int]


class ComplianceFinding(TypedDict):
    description: str
    severity: str
    section: str


class RemediationItem(TypedDict):
    gap: str
    severity: str
    sla_days: int
    timeline: str
    status: str


class ThreatItem(TypedDict):
    threat: str
    category: str
    impact: int
    likelihood: int


class AttackVector(TypedDict):
    type: str
    surface: str


class Countermeasure(TypedDict):
    target_threat: str
    countermeasure: str
    mitigation: str


class TestingPhaseItem(TypedDict):
    phase: int
    name: str
    details: str


logger = logging.getLogger(__name__)


class SecurityAgent(CriticMixin, EnhancedBaseAgent):
    """Specialist agent for security analysis, risk assessment, and compliance"""

    # Task types actually handled by the routing branches in _execute_task() below,
    # including its "security_assessment" fallback default. Explicit literal set, not
    # derived from security_domains (different vocabulary, e.g. no fallback entry).
    _SUPPORTED_TASK_TYPES = frozenset(
        {
            "vulnerability_assessment",
            "risk_analysis",
            "compliance_audit",
            "threat_modeling",
            "code_security_review",
            "security_testing",
            "incident_response",
            "security_assessment",
        }
    )

    def __init__(self, agent_id: str = "security_agent_001", tenant_id: int = 1) -> None:
        super().__init__(agent_id=agent_id, agent_type=AgentType.SPECIALIST, tenant_id=tenant_id)
        self.__init_critic__(mode=CriticMode.BLOCKING)

        # Security-specific configuration
        self.specialization = "cybersecurity_compliance"
        self.security_domains = [
            "vulnerability_assessment",
            "risk_analysis",
            "compliance_audit",
            "threat_modeling",
            "security_testing",
            "incident_response",
            "access_control",
            "data_protection",
        ]

        self.compliance_frameworks = [
            "ISO27001",
            "GDPR",
            "SOC2",
            "PCI-DSS",
            "HIPAA",
            "NIST",
        ]

        # Risk scoring parameters
        self.risk_levels = {
            "CRITICAL": {"score": 9, "color": "red"},
            "HIGH": {"score": 7, "color": "orange"},
            "MEDIUM": {"score": 5, "color": "yellow"},
            "LOW": {"score": 3, "color": "green"},
            "MINIMAL": {"score": 1, "color": "blue"},
        }

        # Initialize LLM client for security analysis
        self.llm_client: ChatTaalmodel | None = None

        logger.info(f"SecurityAgent {agent_id} initialized")

    def _get_llm_client(self) -> ChatTaalmodel:
        """Get LLM client, raising if not initialized."""
        if self.llm_client is None:
            raise RuntimeError("LLM client not initialized. Call initialize() first.")
        return self.llm_client

    async def initialize(self) -> bool:
        """Initialize the security agent"""
        try:
            # Initialize LLM client - use Anthropic for security analysis
            # Het model van de TENANT van deze agent (brief 2026-10-20, ADR-041 B14).
            self.llm_client = TenantTaalmodel(self.tenant_id)

            logger.info(f"SecurityAgent {self.agent_id} fully initialized")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize SecurityAgent {self.agent_id}: {e}")
            return False

    async def get_capabilities(self) -> list[AgentCapability]:
        """Get security agent capabilities"""
        return [
            AgentCapability(
                name="vulnerability_assessment",
                description="Assess vulnerabilities in code, systems, and architecture",
                input_types=["security_request", "system_info"],
                output_types=["security_report", "vulnerability_list"],
            ),
            AgentCapability(
                name="risk_analysis",
                description="Analyze and score security risks",
                input_types=["research_request", "data_source"],
                output_types=["research_report", "analysis_results"],
            ),
            AgentCapability(
                name="compliance_audit",
                description="Audit compliance with security frameworks",
                input_types=["task_request", "text_input"],
                output_types=["analysis_result", "text_output"],
            ),
            AgentCapability(
                name="threat_modeling",
                description="Model potential security threats and attack vectors",
                input_types=["task_request", "text_input"],
                output_types=["analysis_result", "text_output"],
            ),
            AgentCapability(
                name="code_security_review",
                description="Review code for security vulnerabilities",
                input_types=["code_request", "requirements"],
                output_types=["generated_code", "code_analysis"],
            ),
            AgentCapability(
                name="security_testing",
                description="Design security testing strategies",
                input_types=["security_request", "system_info"],
                output_types=["security_report", "vulnerability_list"],
            ),
            AgentCapability(
                name="incident_response",
                description="Provide incident response guidance",
                input_types=["task_request", "text_input"],
                output_types=["analysis_result", "text_output"],
            ),
            AgentCapability(
                name="access_control_analysis",
                description="Analyze access control and authentication mechanisms",
                input_types=["research_request", "data_source"],
                output_types=["research_report", "analysis_results"],
            ),
        ]

    async def validate_task(self, task: TaskData) -> bool:
        """Accept task types that _execute_task() below can actually route."""
        task_type = task.metadata.get("type", "security_assessment")
        return task_type in self._SUPPORTED_TASK_TYPES

    async def _execute_task(self, task: TaskData) -> ExecutionResult:
        """Process security-related tasks"""
        start_time = datetime.now(timezone.utc)

        try:
            task_type = task.metadata.get("type", "security_assessment")
            framework = task.metadata.get("framework", "general")
            task.metadata.get("severity", "medium")

            logger.info(
                f"SecurityAgent processing task: {task.id} (type: {task_type}, framework: {framework})"
            )

            # Route to appropriate security analysis method
            if task_type == "vulnerability_assessment":
                result = await self._process_vulnerability_assessment(task)
            elif task_type == "risk_analysis":
                result = await self._process_risk_analysis(task)
            elif task_type == "compliance_audit":
                result = await self._process_compliance_audit(task)
            elif task_type == "threat_modeling":
                result = await self._process_threat_modeling(task)
            elif task_type == "code_security_review":
                result = await self._process_code_security_review(task)
            elif task_type == "security_testing":
                result = await self._process_security_testing(task)
            elif task_type == "incident_response":
                result = await self._process_incident_response(task)
            else:
                result = await self._process_general_security_assessment(task)

            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()

            return ExecutionResult(
                task_id=task.id,
                success=True,
                result_data={
                    "agent_type": "security_agent",
                    "specialization": self.specialization,
                    "security_results": result,
                    "frameworks_supported": self.compliance_frameworks,
                    "framework_used": framework,
                    "methodology": task_type,
                    "risk_assessment": self._calculate_overall_risk(result),
                },
                execution_time=execution_time,
                logs=[
                    f"Security task {task.id} processed by SecurityAgent",
                    f"Task type: {task_type}",
                    f"Framework: {framework}",
                    f"Execution time: {execution_time:.2f}s",
                ],
            )

        except Exception as e:
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()
            logger.error(f"SecurityAgent error processing task {task.id}: {e}")

            return ExecutionResult(
                task_id=task.id,
                success=False,
                error_message=f"Security processing failed: {e}",
                execution_time=execution_time,
                logs=[f"SecurityAgent error: {e}"],
            )

    async def _process_vulnerability_assessment(
        self, task: TaskData
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Assess vulnerabilities in systems or code"""

        target_type = task.metadata.get("target_type", "system")
        code_content = task.metadata.get("code", "")
        system_info = task.metadata.get("system_info", "")

        assessment_prompt = f"""
        Perform comprehensive vulnerability assessment for:

        Target Type: {target_type}
        Assessment Focus: {task.title}
        Details: {task.description}

        {"Code to Assess:" if code_content else "System Information:"}
        {code_content if code_content else system_info}

        Provide detailed vulnerability assessment covering:
        1. Identified vulnerabilities with CVE references where applicable
        2. Risk severity scoring (Critical/High/Medium/Low)
        3. Attack vectors and exploitation methods
        4. Impact assessment (Confidentiality/Integrity/Availability)
        5. Mitigation strategies and remediation steps
        6. Priority ranking for fixes
        7. Compliance implications

        Focus on actionable security recommendations.
        """

        messages = [LLMMessage(role="user", content=assessment_prompt)]
        response = await self._get_llm_client().chat_completion(messages)

        # Parse vulnerabilities and risk scores
        vulnerabilities = self._extract_vulnerabilities(response.content)
        risk_score = self._calculate_risk_score(response.content)

        return {
            "target_type": target_type,
            "assessment_results": response.content,
            "vulnerabilities_found": vulnerabilities,
            "risk_score": risk_score,
            "severity_breakdown": self._categorize_by_severity(vulnerabilities),
            "assessment_date": datetime.now(timezone.utc).isoformat(),
            "assessor": "security_agent_ai",
            "next_assessment_due": self._calculate_next_assessment_date(),
            "compliance_status": self._assess_compliance_impact(vulnerabilities),
        }

    async def _process_risk_analysis(
        self, task: TaskData
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Analyze security risks"""

        risk_domain = task.metadata.get("domain", "general")
        assets = task.metadata.get("assets", [])
        threats = task.metadata.get("threats", [])

        risk_prompt = f"""
        Conduct comprehensive security risk analysis for:

        Risk Domain: {risk_domain}
        Analysis Request: {task.title}
        Context: {task.description}

        Assets at Risk: {", ".join(assets) if assets else "To be identified"}
        Known Threats: {", ".join(threats) if threats else "To be assessed"}

        Provide thorough risk analysis including:
        1. Risk identification and categorization
        2. Threat actor analysis
        3. Likelihood assessment (1-5 scale)
        4. Impact assessment (1-5 scale)
        5. Risk matrix and priority ranking
        6. Recommended risk treatments (Accept/Mitigate/Transfer/Avoid)
        7. Cost-benefit analysis of mitigations
        8. Residual risk assessment

        Use quantitative risk scoring where possible.
        """

        messages = [LLMMessage(role="user", content=risk_prompt)]
        response = await self._get_llm_client().chat_completion(messages)

        # Extract risk metrics
        risks = self._extract_risks(response.content)
        risk_matrix = self._build_risk_matrix(risks)

        return {
            "risk_domain": risk_domain,
            "risk_analysis": response.content,
            "identified_risks": risks,
            "risk_matrix": risk_matrix,
            "high_priority_risks": [r for r in risks if r.get("priority", "medium") == "high"],
            "overall_risk_level": self._calculate_overall_risk_level(risks),
            "treatment_recommendations": self._generate_treatment_recommendations(risks),
            "analysis_date": datetime.now(timezone.utc).isoformat(),
            "review_frequency": "quarterly",
        }

    async def _process_compliance_audit(
        self, task: TaskData
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Audit compliance with security frameworks"""

        framework = task.metadata.get("framework", "ISO27001")
        scope = task.metadata.get("scope", "full_audit")
        current_controls = task.metadata.get("controls", {})

        audit_prompt = f"""
        Conduct {framework} compliance audit for:

        Audit Scope: {scope}
        Organization/System: {task.title}
        Audit Requirements: {task.description}

        Current Controls: {json.dumps(current_controls) if current_controls else "To be assessed"}

        Provide comprehensive compliance audit covering:
        1. Framework requirements mapping
        2. Current compliance status assessment
        3. Gap analysis with specific control deficiencies
        4. Risk rating for each gap (Critical/High/Medium/Low)
        5. Remediation roadmap with timelines
        6. Cost estimates for compliance improvements
        7. Ongoing compliance monitoring recommendations
        8. Certification readiness assessment

        Focus on practical implementation guidance.
        """

        messages = [LLMMessage(role="user", content=audit_prompt)]
        response = await self._get_llm_client().chat_completion(messages)

        # Parse compliance findings
        findings = self._extract_compliance_findings(response.content)
        gaps = self._identify_compliance_gaps(response.content)

        return {
            "framework": framework,
            "audit_scope": scope,
            "audit_results": response.content,
            "compliance_findings": findings,
            "identified_gaps": gaps,
            "compliance_score": self._calculate_compliance_score(gaps),
            "critical_gaps": [g for g in gaps if g.get("severity") == "critical"],
            "remediation_timeline": self._generate_remediation_timeline(gaps),
            "audit_date": datetime.now(timezone.utc).isoformat(),
            "next_audit_due": self._calculate_next_audit_date(framework),
            "certification_readiness": self._assess_certification_readiness(gaps),
        }

    async def _process_threat_modeling(
        self, task: TaskData
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Model security threats and attack vectors"""

        system_architecture = task.metadata.get("architecture", "")
        attack_surface = task.metadata.get("attack_surface", "web_application")
        threat_actors = task.metadata.get(
            "threat_actors", ["script_kiddie", "organized_crime", "nation_state"]
        )

        threat_prompt = f"""
        Develop comprehensive threat model for:

        System: {task.title}
        Description: {task.description}
        Attack Surface: {attack_surface}
        Architecture: {system_architecture}

        Potential Threat Actors: {", ".join(threat_actors)}

        Create detailed threat model including:
        1. System decomposition and trust boundaries
        2. Threat enumeration using STRIDE methodology
        3. Attack tree analysis for each threat
        4. Threat actor capability mapping
        5. Attack vector analysis with step-by-step scenarios
        6. Impact and likelihood scoring
        7. Countermeasure identification
        8. Residual risk assessment

        Use structured threat modeling methodology.
        """

        messages = [LLMMessage(role="user", content=threat_prompt)]
        response = await self._get_llm_client().chat_completion(messages)

        # Parse threat model components
        threats = self._extract_threats(response.content)
        attack_vectors = self._extract_attack_vectors(response.content)

        return {
            "system": task.title,
            "attack_surface": attack_surface,
            "threat_model": response.content,
            "identified_threats": threats,
            "attack_vectors": attack_vectors,
            "threat_actors": threat_actors,
            "stride_analysis": self._categorize_by_stride(threats),
            "high_risk_threats": [
                t for t in threats if t.get("risk_level", "medium") in ["high", "critical"]
            ],
            "countermeasures": self._generate_countermeasures(threats),
            "model_date": datetime.now(timezone.utc).isoformat(),
            "review_cycle": "bi_annual",
        }

    async def _process_code_security_review(
        self, task: TaskData
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Review code for security vulnerabilities"""

        code_content = task.metadata.get("code", "")
        language = task.metadata.get("language", "python")
        security_focus = task.metadata.get("focus", "general")

        if not code_content:
            return {"error": "No code provided for security review", "status": "failed"}

        security_review_prompt = f"""
        Perform comprehensive security code review for {language} code:

        Security Focus: {security_focus}
        Code to Review:
        ```{language}
        {code_content}
        ```

        Conduct thorough security analysis covering:
        1. Input validation and sanitization
        2. Authentication and authorization flaws
        3. SQL injection and XSS vulnerabilities
        4. Cryptographic implementation issues
        5. Error handling and information disclosure
        6. Session management security
        7. Business logic vulnerabilities
        8. Dependency and third-party risks

        Provide OWASP Top 10 mapping and remediation code examples.
        """

        messages = [LLMMessage(role="user", content=security_review_prompt)]
        response = await self._get_llm_client().chat_completion(messages)

        # Parse security issues
        security_issues = self._extract_security_issues(response.content)
        owasp_mapping = self._map_to_owasp_top10(security_issues)

        return {
            "language": language,
            "security_focus": security_focus,
            "review_results": response.content,
            "security_issues": security_issues,
            "owasp_top10_mapping": owasp_mapping,
            "critical_vulnerabilities": [
                i for i in security_issues if i.get("severity") == "critical"
            ],
            "remediation_priority": self._prioritize_remediations(security_issues),
            "security_score": self._calculate_security_score(security_issues),
            "review_date": datetime.now(timezone.utc).isoformat(),
            "follow_up_required": len(
                [i for i in security_issues if i.get("severity") in ["high", "critical"]]
            )
            > 0,
        }

    async def _process_security_testing(
        self, task: TaskData
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Design security testing strategies"""

        test_type = task.metadata.get("test_type", "penetration_testing")
        target_system = task.metadata.get("target", "web_application")

        testing_prompt = f"""
        Design comprehensive security testing strategy for:

        Test Type: {test_type}
        Target System: {target_system}
        Testing Objective: {task.title}
        Requirements: {task.description}

        Develop detailed security testing plan including:
        1. Test scope and objectives
        2. Testing methodology and approach
        3. Test scenarios and use cases
        4. Required tools and techniques
        5. Risk assessment of testing activities
        6. Success criteria and metrics
        7. Reporting and documentation requirements
        8. Post-test remediation workflow

        Ensure ethical hacking principles and legal compliance.
        """

        messages = [LLMMessage(role="user", content=testing_prompt)]
        response = await self._get_llm_client().chat_completion(messages)

        return {
            "test_type": test_type,
            "target_system": target_system,
            "testing_plan": response.content,
            "testing_phases": self._extract_testing_phases(response.content),
            "required_tools": self._extract_testing_tools(response.content),
            "risk_level": "medium",  # Default for testing activities
            "estimated_duration": self._estimate_testing_duration(test_type),
            "compliance_requirements": [
                "written_authorization",
                "scope_agreement",
                "data_protection",
            ],
            "deliverables": [
                "executive_summary",
                "technical_findings",
                "remediation_plan",
            ],
        }

    async def _process_incident_response(
        self, task: TaskData
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Provide incident response guidance"""

        incident_type = task.metadata.get("incident_type", "security_breach")
        severity = task.metadata.get("severity", "medium")
        affected_systems = task.metadata.get("affected_systems", [])

        incident_prompt = f"""
        Provide incident response guidance for:

        Incident Type: {incident_type}
        Severity Level: {severity}
        Incident Description: {task.title}
        Details: {task.description}
        Affected Systems: {", ".join(affected_systems) if affected_systems else "To be determined"}

        Provide comprehensive incident response including:
        1. Immediate containment actions
        2. Evidence preservation procedures
        3. Impact assessment methodology
        4. Investigation and forensics approach
        5. Communication and notification plan
        6. Recovery and restoration steps
        7. Lessons learned and improvement recommendations
        8. Legal and regulatory considerations

        Follow industry-standard incident response frameworks.
        """

        messages = [LLMMessage(role="user", content=incident_prompt)]
        response = await self._get_llm_client().chat_completion(messages)

        return {
            "incident_type": incident_type,
            "severity": severity,
            "affected_systems": affected_systems,
            "response_plan": response.content,
            "immediate_actions": self._extract_immediate_actions(response.content),
            "investigation_steps": self._extract_investigation_steps(response.content),
            "recovery_timeline": self._estimate_recovery_timeline(severity),
            "notification_requirements": self._determine_notifications(incident_type, severity),
            "escalation_triggers": self._define_escalation_triggers(severity),
            "response_date": datetime.now(timezone.utc).isoformat(),
            "follow_up_required": True,
        }

    async def _process_general_security_assessment(
        self, task: TaskData
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Process general security assessment requests"""

        assessment_prompt = f"""
        Conduct comprehensive security assessment for:

        Subject: {task.title}
        Requirements: {task.description}

        Provide thorough security analysis including:
        1. Security posture assessment
        2. Risk identification and prioritization
        3. Vulnerability analysis
        4. Compliance considerations
        5. Security control recommendations
        6. Implementation roadmap
        7. Cost-benefit analysis
        8. Ongoing monitoring strategy

        Focus on practical, actionable security improvements.
        """

        messages = [LLMMessage(role="user", content=assessment_prompt)]
        response = await self._get_llm_client().chat_completion(messages)

        return {
            "assessment_type": "general_security",
            "assessment_results": response.content,
            "security_posture": "to_be_determined",
            "key_recommendations": self._extract_recommendations(response.content),
            "priority_actions": self._extract_priority_actions(response.content),
            "estimated_effort": "medium",
            "assessment_date": datetime.now(timezone.utc).isoformat(),
            "review_frequency": "annual",
        }

    # Helper methods for parsing and analysis
    def _extract_vulnerabilities(
        self, text: str
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Extract vulnerabilities from assessment text"""
        # Simplified extraction - in production would use more sophisticated parsing
        vulnerabilities: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        lines = text.split("\n")

        for line in lines:
            if any(word in line.lower() for word in ["vulnerability", "cve-", "exploit"]):
                severity = "medium"
                if any(word in line.lower() for word in ["critical", "high"]):
                    severity = "high" if "high" in line.lower() else "critical"
                elif "low" in line.lower():
                    severity = "low"

                vulnerabilities.append(
                    {
                        "description": line.strip(),
                        "severity": severity,
                        "type": "security_vulnerability",
                    }
                )

        return vulnerabilities[:10]  # Limit to top 10

    def _calculate_risk_score(self, assessment_text: str) -> float:
        """Calculate overall risk score from assessment"""
        critical_count = assessment_text.lower().count("critical")
        high_count = assessment_text.lower().count("high")
        medium_count = assessment_text.lower().count("medium")

        # Weighted scoring
        score = (critical_count * 9) + (high_count * 7) + (medium_count * 5)

        # Normalize to 0-10 scale
        return min(score / 10, 10.0)

    def _calculate_overall_risk(
        self, result: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Calculate overall risk assessment"""
        risk_score = result.get("risk_score", 5.0)

        if risk_score >= 8:
            level = "CRITICAL"
        elif risk_score >= 6:
            level = "HIGH"
        elif risk_score >= 4:
            level = "MEDIUM"
        else:
            level = "LOW"

        return {
            "level": level,
            "score": risk_score,
            "color": self.risk_levels[level]["color"],
            "recommendation": "immediate_action" if level == "CRITICAL" else "planned_remediation",
        }

    def _categorize_by_severity(
        self, vulnerabilities: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, int]:  # TODO(TYPE): replace Any with concrete type
        """Categorize vulnerabilities by severity"""
        severity_counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}

        for vuln in vulnerabilities:
            severity = vuln.get("severity", "medium").lower()
            if severity in severity_counts:
                severity_counts[severity] += 1

        return severity_counts

    def _calculate_next_assessment_date(self) -> str:
        """Calculate next assessment due date"""
        from datetime import timedelta

        next_date = datetime.now(timezone.utc) + timedelta(days=90)  # Quarterly assessment
        return next_date.isoformat()

    def _assess_compliance_impact(
        self, vulnerabilities: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    ) -> str:  # TODO(TYPE): replace Any with concrete type
        """Assess impact on compliance"""
        critical_vulns = len([v for v in vulnerabilities if v.get("severity") == "critical"])

        if critical_vulns > 0:
            return "non_compliant"
        elif len(vulnerabilities) > 5:
            return "at_risk"
        else:
            return "compliant"

    # Genuine parsing, matrix calculation, and OWASP mapping methods
    def _extract_risks(
        self, text: str
    ) -> list[RiskItem]:
        risks: list[RiskItem] = []
        if not text:
            return risks

        import re
        # Match lines like "- [CRITICAL] Title. Description. Likelihood: X, Impact: Y" or similar bullets
        pattern = re.compile(
            r"[-*]\s*\[?(CRITICAL|HIGH|MEDIUM|LOW)\]?\s*:?\s*(.*?)(?=\n[-*]|\n\n|\Z)",
            re.IGNORECASE | re.DOTALL,
        )
        for match in pattern.finditer(text):
            severity = match.group(1).lower()
            content = match.group(2).strip().replace("\n", " ")
            
            # Extract Likelihood and Impact if present, else estimate from severity
            lh_match = re.search(r"likelihood\s*:?\s*(\d+)", content, re.IGNORECASE)
            imp_match = re.search(r"impact\s*:?\s*(\d+)", content, re.IGNORECASE)
            
            sev_defaults = {"critical": (4, 5), "high": (3, 4), "medium": (3, 2), "low": (1, 2)}
            def_lh, def_imp = sev_defaults.get(severity, (2, 2))
            
            likelihood = int(lh_match.group(1)) if lh_match else def_lh
            impact = int(imp_match.group(1)) if imp_match else def_imp
            
            title = content.split(".")[0].strip()
            risks.append({
                "title": title,
                "description": content,
                "severity": severity,
                "likelihood": likelihood,
                "impact": impact,
                "risk_score": likelihood * impact,
            })
        return risks

    def _build_risk_matrix(
        self, risks: list[RiskItem]
    ) -> RiskMatrix:
        matrix: RiskMatrix = {
            "critical": [],
            "high": [],
            "medium": [],
            "low": [],
            "matrix_distribution": {f"L{lh}_I{imp}": 0 for lh in range(1, 6) for imp in range(1, 6)},
        }
        for r in risks:
            sev = r.get("severity", "medium").lower()
            if sev == "critical":
                matrix["critical"].append(r)
            elif sev == "high":
                matrix["high"].append(r)
            elif sev == "medium":
                matrix["medium"].append(r)
            elif sev == "low":
                matrix["low"].append(r)
            lh = min(max(r.get("likelihood", 3), 1), 5)
            imp = min(max(r.get("impact", 3), 1), 5)
            matrix["matrix_distribution"][f"L{lh}_I{imp}"] += 1
        return matrix

    def _calculate_overall_risk_level(
        self, risks: list[RiskItem]
    ) -> str:
        if not risks:
            return "low"
        if any(r.get("severity") == "critical" for r in risks):
            return "critical"
        if any(r.get("severity") == "high" for r in risks):
            return "high"
        if any(r.get("severity") == "medium" for r in risks):
            return "medium"
        return "low"

    def _generate_treatment_recommendations(
        self, risks: list[RiskItem]
    ) -> list[str]:
        recommendations = [
            "Implement automated dependency and container scanning in CI/CD pipeline",
            "Enforce least-privilege RBAC policies and periodic credential rotation",
            "Establish continuous security telemetry and audit logging",
        ]
        for r in risks:
            if r.get("severity") == "critical":
                recommendations.insert(0, f"Immediate hotfix required: {r.get('title', 'Critical Vulnerability')}")
        return recommendations

    def _extract_compliance_findings(
        self, text: str
    ) -> list[ComplianceFinding]:
        findings: list[ComplianceFinding] = []
        if not text:
            return findings

        import re
        lines = text.splitlines()
        current_section = ""
        for line in lines:
            if line.startswith("#"):
                current_section = line.lower()
            elif ("[" in line or "-" in line) and any(kw in line.lower() for kw in ["gdpr", "iso", "soc2", "pci", "hipaa", "compliant", "gap", "retention", "backup"]):
                sev = "medium"
                for s in ["critical", "high", "medium", "low"]:
                    if s in line.lower():
                        sev = s
                        break
                findings.append({
                    "description": line.strip("- *#"),
                    "severity": sev,
                    "section": current_section,
                })
        return findings

    def _identify_compliance_gaps(
        self, text: str
    ) -> list[ComplianceFinding]:
        findings = self._extract_compliance_findings(text)
        return [f for f in findings if any(w in f["description"].lower() for w in ["gap", "non-compliant", "not enforced", "missing", "unencrypted", "violation"])]

    def _calculate_compliance_score(
        self, gaps: list[ComplianceFinding]
    ) -> float:
        if not gaps:
            return 100.0
        critical = len([g for g in gaps if g.get("severity") == "critical"])
        return max(0.0, 100.0 - (critical * 20) - (len(gaps) * 5))

    def _generate_remediation_timeline(
        self, gaps: list[ComplianceFinding]
    ) -> list[RemediationItem]:
        timeline: list[RemediationItem] = []
        sla_map = {"critical": 7, "high": 30, "medium": 60, "low": 90}
        for gap in gaps:
            sev = gap.get("severity", "medium").lower()
            sla = sla_map.get(sev, 60)
            timeline.append({
                "gap": gap.get("description", "Unknown gap"),
                "severity": sev,
                "sla_days": sla,
                "timeline": f"Within {sla} days",
                "status": "pending_remediation",
            })
        return timeline

    def _calculate_next_audit_date(self, framework: str) -> str:
        from datetime import timedelta
        intervals = {"ISO27001": 365, "SOC2": 365, "PCI-DSS": 90, "GDPR": 180}
        days = intervals.get(framework, 365)
        return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()

    def _assess_certification_readiness(
        self, gaps: list[ComplianceFinding]
    ) -> str:
        critical = len([g for g in gaps if g.get("severity") == "critical"])
        if critical > 0:
            return "not_ready"
        elif len(gaps) > 5:
            return "needs_improvement"
        return "ready"

    def _extract_threats(
        self, text: str
    ) -> list[ThreatItem]:
        risks = self._extract_risks(text)
        threats: list[ThreatItem] = []
        for r in risks:
            threats.append({
                "threat": r["title"],
                "category": r["severity"],
                "impact": r["impact"],
                "likelihood": r["likelihood"],
            })
        return threats

    def _extract_attack_vectors(
        self, text: str
    ) -> list[AttackVector]:
        vectors: list[AttackVector] = []
        text_lower = text.lower()
        if "sql" in text_lower or "injection" in text_lower:
            vectors.append({"type": "SQL Injection", "surface": "API Endpoints / Database Query Layer"})
        if "idor" in text_lower or "direct object" in text_lower:
            vectors.append({"type": "IDOR / Broken Object Level Auth", "surface": "Resource Identifier Parameters"})
        if "rate limit" in text_lower or "brute force" in text_lower:
            vectors.append({"type": "Credential Stuffing / Brute Force", "surface": "Authentication Endpoints"})
        if "banner" in text_lower or "header" in text_lower:
            vectors.append({"type": "Information Disclosure", "surface": "HTTP Response Headers"})
        return vectors

    def _categorize_by_stride(
        self,
        threats: list[ThreatItem],
    ) -> dict[str, list[ThreatItem]]:
        categories: dict[str, list[ThreatItem]] = {
            "spoofing": [],
            "tampering": [],
            "repudiation": [],
            "information_disclosure": [],
            "denial_of_service": [],
            "elevation_of_privilege": [],
        }
        for t in threats:
            desc = str(t.get("threat", "")).lower()
            if "spoof" in desc or "auth" in desc:
                categories["spoofing"].append(t)
            elif "tamper" in desc or "sql" in desc or "inject" in desc:
                categories["tampering"].append(t)
            elif "repudiat" in desc or "audit" in desc or "log" in desc:
                categories["repudiation"].append(t)
            elif "disclos" in desc or "idor" in desc or "leak" in desc or "banner" in desc:
                categories["information_disclosure"].append(t)
            elif "denial" in desc or "rate" in desc or "dos" in desc:
                categories["denial_of_service"].append(t)
            else:
                categories["elevation_of_privilege"].append(t)
        return categories

    def _generate_countermeasures(
        self, threats: list[ThreatItem]
    ) -> list[Countermeasure]:
        countermeasures: list[Countermeasure] = []
        for t in threats:
            title = t.get("threat", "")
            lower_title = title.lower()
            if "sql" in lower_title:
                cm = "Enforce parameterized queries with SQLAlchemy / Pydantic validation"
            elif "idor" in lower_title or "access" in lower_title:
                cm = "Enforce strict tenant_id and user_id scoping on all query filters"
            elif "rate" in lower_title or "brute" in lower_title:
                cm = "Implement slowapi rate limiting with Redis-backed counters"
            elif "backup" in lower_title or "encrypt" in lower_title:
                cm = "Enable AES-256 server-side encryption with AWS KMS / GCP CMEK"
            else:
                cm = "Apply input sanitation, principle of least privilege, and security audit logging"
            countermeasures.append({
                "target_threat": title,
                "countermeasure": cm,
                "mitigation": cm,
            })
        return countermeasures

    def _extract_security_issues(
        self, text: str
    ) -> list[RiskItem]:
        return self._extract_risks(text)

    def _map_to_owasp_top10(
        self, issues: list[RiskItem]
    ) -> dict[str, list[RiskItem]]:
        owasp_mapping: dict[str, list[RiskItem]] = {
            "A01:2021-Broken Access Control": [],
            "A02:2021-Cryptographic Failures": [],
            "A03:2021-Injection": [],
            "A04:2021-Insecure Design": [],
            "A05:2021-Security Misconfiguration": [],
            "A06:2021-Vulnerable and Outdated Components": [],
            "A07:2021-Identification and Authentication Failures": [],
            "A08:2021-Software and Data Integrity Failures": [],
            "A09:2021-Security Logging and Monitoring Failures": [],
            "A10:2021-Server-Side Request Forgery": [],
        }
        for item in issues:
            desc = (item.get("title", "") + " " + item.get("description", "")).lower()
            if "sql" in desc or "inject" in desc or "command" in desc:
                owasp_mapping["A03:2021-Injection"].append(item)
            elif "idor" in desc or "access control" in desc or "privilege" in desc or "permission" in desc:
                owasp_mapping["A01:2021-Broken Access Control"].append(item)
            elif "crypto" in desc or "unencrypted" in desc or "tls" in desc or "certificate" in desc:
                owasp_mapping["A02:2021-Cryptographic Failures"].append(item)
            elif "header" in desc or "banner" in desc or "misconfig" in desc or "default" in desc:
                owasp_mapping["A05:2021-Security Misconfiguration"].append(item)
            elif "password" in desc or "rate limit" in desc or "jwt" in desc or "session" in desc:
                owasp_mapping["A07:2021-Identification and Authentication Failures"].append(item)
            elif "ssrf" in desc or "webhook" in desc:
                owasp_mapping["A10:2021-Server-Side Request Forgery"].append(item)
            elif "log" in desc or "monitor" in desc or "audit" in desc:
                owasp_mapping["A09:2021-Security Logging and Monitoring Failures"].append(item)
            else:
                owasp_mapping["A04:2021-Insecure Design"].append(item)

        # Return only categories that have mapped items
        return {k: v for k, v in owasp_mapping.items() if v}

    def _prioritize_remediations(
        self, issues: list[RiskItem]
    ) -> list[RiskItem]:
        return sorted(
            issues,
            key=lambda x: {"critical": 0, "high": 1, "medium": 2, "low": 3}.get(
                x.get("severity", "medium"), 2
            ),
        )

    def _calculate_security_score(
        self, issues: list[RiskItem]
    ) -> float:
        if not issues:
            return 100.0
        critical = len([i for i in issues if i.get("severity") == "critical"])
        high = len([i for i in issues if i.get("severity") == "high"])
        return max(0.0, 100.0 - (critical * 25) - (high * 10) - (len(issues) * 2))

    def _extract_testing_phases(
        self, text: str
    ) -> list[TestingPhaseItem]:
        phases: list[TestingPhaseItem] = []
        import re
        matches = re.findall(r"Phase\s*(\d+)\s*:?\s*(.*?)(?=\nPhase|\n\n|\Z)", text, re.IGNORECASE | re.DOTALL)
        for num, content in matches:
            phases.append({
                "phase": int(num),
                "name": content.strip().split("\n")[0],
                "details": content.strip(),
            })
        return phases

    def _extract_testing_tools(self, text: str) -> list[str]:
        import re

        known_tools = [
            "semgrep",
            "bandit",
            "owasp zap",
            "zap",
            "postman",
            "sonarqube",
            "trivy",
            "snyk",
            "burp suite",
            "nmap",
            "sqlmap",
            "wireshark",
        ]
        found = []
        text_lower = text.lower()
        for tool in known_tools:
            if re.search(rf"\b{re.escape(tool)}\b", text_lower):
                if tool == "zap" and "owasp zap" in found:
                    continue
                found.append(tool)
        return found

    def _estimate_testing_duration(self, test_type: str) -> str:
        durations = {
            "penetration_testing": "2-4 weeks",
            "vulnerability_scanning": "1-2 days",
            "code_review": "1-2 weeks",
            "compliance_audit": "2-3 weeks",
        }
        return durations.get(test_type, "1-2 weeks")

    def _extract_immediate_actions(self, text: str) -> list[str]:
        actions: list[str] = []
        import re
        # Look for numbered lists under containment/response or action keywords
        matches = re.findall(r"^\s*\d+\.\s*(.+)$", text, re.MULTILINE)
        for m in matches:
            if any(w in m.lower() for w in ["revoke", "isolate", "terminate", "disable", "patch", "contain", "block", "dump", "kill"]):
                actions.append(m.strip())
        return actions

    def _extract_investigation_steps(self, text: str) -> list[str]:
        steps: list[str] = []
        import re
        matches = re.findall(r"^\s*\d+\.\s*(.+)$", text, re.MULTILINE)
        for m in matches:
            if any(w in m.lower() for w in ["forensic", "dump", "log", "investigat", "snapshot", "anomalous", "root cause", "trace"]):
                steps.append(m.strip())
        return steps

    def _estimate_recovery_timeline(self, severity: str) -> str:
        timelines = {
            "critical": "24-48 hours",
            "high": "1-3 days",
            "medium": "1-2 weeks",
            "low": "2-4 weeks",
        }
        return timelines.get(severity, "1-2 weeks")

    def _determine_notifications(self, incident_type: str, severity: str) -> list[str]:
        notifications = ["security_team", "management"]
        if severity in ("critical", "high"):
            notifications.extend(["executive_team", "legal"])
        if incident_type == "data_breach":
            notifications.extend(["data_protection_officer", "regulatory_authority"])
        return notifications

    def _define_escalation_triggers(self, severity: str) -> list[str]:
        triggers = ["no_containment_in_1h", "additional_systems_affected"]
        if severity in ("critical", "high"):
            triggers.append("data_exfiltration_detected")
        return triggers

    def _extract_recommendations(self, text: str) -> list[str]:
        return self._generate_treatment_recommendations(self._extract_risks(text))

    def _extract_priority_actions(self, text: str) -> list[str]:
        immediate = self._extract_immediate_actions(text)
        if immediate:
            return immediate
        return ["Isolate affected services", "Review access logs", "Apply security patches"]


# Factory function
async def create_security_agent(
    agent_id: str | None = None,
    tenant_id: int = 1,
) -> SecurityAgent:
    """Create and initialize a security agent"""
    if agent_id is None:
        agent_id = f"security_agent_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    agent = SecurityAgent(agent_id, tenant_id=tenant_id)

    # Initialize the agent
    await agent.initialize()

    return agent
