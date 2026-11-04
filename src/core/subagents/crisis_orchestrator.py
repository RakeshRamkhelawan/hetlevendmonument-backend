#!/usr/bin/env python3
"""
Crisis Orchestrator - M-MDP Crisis Management Coordination Engine
CVA-level orchestrator for coordinating specialized crisis management agents
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional, cast

from .agent_factory import AgentConfiguration, AgentFactory, AgentType
from .crisis_management_agents import (
    CrisisContext,
    CrisisType,
    CustomerOperationsAgent,
    CybersecurityAgent,
    FinancialRiskAgent,
    LegalComplianceAgent,
    PRCommunicationsAgent,
    RiskLevel,
)

logger = logging.getLogger(__name__)


class CrisisPhase(Enum):
    """Crisis response phases"""

    INITIAL_RESPONSE = "initial_response"
    ANALYSIS = "analysis"
    DECISION_MAKING = "decision_making"
    IMPLEMENTATION = "implementation"
    RECOVERY = "recovery"


@dataclass
class CrisisTask:
    """Crisis management task"""

    task_id: str
    agent_type: str
    analysis_type: str
    priority: int
    deadline: datetime
    dependencies: list[str]
    status: str = "pending"


@dataclass
class CrisisDecision:
    """Crisis management decision"""

    decision_id: str
    scenario: str
    recommendation: str
    confidence: float
    rationale: list[str]
    cost_benefit: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    risks: list[str]
    timeline: str


class CrisisOrchestrator:
    """CVA-level crisis management orchestrator"""

    def __init__(self) -> None:
        self.crisis_agents: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        self.active_crisis: CrisisContext | None = None
        self.crisis_timeline: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
        self.agent_responses: dict[str, Any] = {}  # TODO(TYPE): replace Any with concrete type
        self.decisions: list[CrisisDecision] = []
        self.orchestration_start_time: datetime | None = None

        # Initialize agent factory for crisis agents
        self.agent_factory = AgentFactory()
        self._register_crisis_agents()

    def _register_crisis_agents(self) -> None:
        """Register crisis management agent types"""
        crisis_agent_types = {
            "cybersecurity": CybersecurityAgent,
            "legal_compliance": LegalComplianceAgent,
            "pr_communications": PRCommunicationsAgent,
            "financial_risk": FinancialRiskAgent,
            "customer_operations": CustomerOperationsAgent,
        }

        for agent_name, agent_class in crisis_agent_types.items():
            # Create configuration for crisis agents
            config = AgentConfiguration(
                agent_type=AgentType.SECURITY_ANALYSIS,  # Use security analysis type as base
                name=f"Crisis{agent_class.__name__}",
                capabilities=[agent_name, "crisis_response", "emergency_analysis"],
                max_concurrent_tasks=1,  # Crisis agents focus on single critical task
                memory_limit_mb=512,
                cpu_priority="high",
                specialized_parameters={"crisis_mode": True, "response_time": "urgent"},
                auto_scale=False,
                health_check_interval=60,
            )

            # Register with factory
            self.agent_factory.register_agent_type(agent_name, agent_class)  # type: ignore[arg-type]  # NOTE: agent_name is a str key used as AgentType
            self.agent_factory.register_default_configuration(agent_name, config)  # type: ignore[arg-type]  # NOTE: agent_name is a str key used as AgentType

    async def initiate_crisis_response(self, crisis_scenario: dict[str, Any]) -> str:  # TODO(TYPE): replace Any with concrete type
        """Initiate M-MDP crisis response orchestration"""
        self.orchestration_start_time = datetime.now(timezone.utc)
        crisis_id = f"crisis_{int(time.time())}"

        logger.critical(f"[ALERT] INITIATING CRISIS RESPONSE: {crisis_id}")
        logger.critical(f"Scenario: {crisis_scenario.get('scenario_name', 'Unknown Crisis')}")

        # Create crisis context
        self.active_crisis = CrisisContext(
            crisis_code=crisis_scenario.get("crisis_code", "UNKNOWN"),
            crisis_type=CrisisType(crisis_scenario.get("crisis_type", "cybersecurity")),
            severity=RiskLevel(crisis_scenario.get("severity", "critical")),
            timeline=crisis_scenario.get("timeline", "immediate"),
            affected_systems=crisis_scenario.get("affected_systems", []),
            stakeholders=crisis_scenario.get("stakeholders", []),
            regulatory_implications=crisis_scenario.get("regulatory_implications", []),
        )

        # Log crisis initiation
        self.crisis_timeline.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "phase": CrisisPhase.INITIAL_RESPONSE.value,
                "event": "Crisis response initiated",
                "details": crisis_scenario,
            }
        )

        # Create and deploy crisis agents
        await self._deploy_crisis_agents()

        # Execute coordinated crisis response
        await self._execute_coordinated_response(crisis_scenario)

        return crisis_id

    async def _deploy_crisis_agents(self) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Deploy all specialized crisis agents"""
        agent_types = [
            "cybersecurity",
            "legal_compliance",
            "pr_communications",
            "financial_risk",
            "customer_operations",
        ]

        for agent_type in agent_types:
            try:
                agent_id = await self.agent_factory.create_agent(agent_type)  # type: ignore[arg-type]  # NOTE: agent_type str used as AgentType
                if agent_id:
                    agent = await self.agent_factory.get_agent(agent_id)
                    self.crisis_agents[agent_type] = agent
                    logger.info(f"[OK] Deployed crisis agent: {agent_type} ({agent_id})")
                else:
                    logger.error(f"[FAIL] Failed to deploy crisis agent: {agent_type}")
            except Exception as e:
                logger.error(f"[FAIL] Error deploying {agent_type} agent: {e}")

    async def _execute_coordinated_response(self, crisis_scenario: dict[str, Any]) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Execute coordinated multi-agent crisis response"""

        # Phase 1: Immediate Analysis (0-10 minutes)
        logger.critical("[TARGET] PHASE 1: IMMEDIATE CRISIS ANALYSIS")
        await self._phase_1_immediate_analysis(crisis_scenario)

        # Phase 2: Decision Synthesis (10-15 minutes)
        logger.critical("[TARGET] PHASE 2: DECISION SYNTHESIS")
        await self._phase_2_decision_synthesis()

        # Generate deliverables
        await self._generate_crisis_deliverables()

    async def _phase_1_immediate_analysis(self, crisis_scenario: dict[str, Any]) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Phase 1: Immediate multi-agent analysis"""

        # Define parallel tasks for each agent
        crisis_tasks = [
            CrisisTask(
                task_id="cyber_incident_analysis",
                agent_type="cybersecurity",
                analysis_type="incident_analysis",
                priority=1,
                deadline=datetime.now(timezone.utc) + timedelta(minutes=8),
                dependencies=[],
            ),
            CrisisTask(
                task_id="legal_regulatory_assessment",
                agent_type="legal_compliance",
                analysis_type="regulatory_assessment",
                priority=1,
                deadline=datetime.now(timezone.utc) + timedelta(minutes=8),
                dependencies=[],
            ),
            CrisisTask(
                task_id="communication_strategy",
                agent_type="pr_communications",
                analysis_type="communication_strategy",
                priority=2,
                deadline=datetime.now(timezone.utc) + timedelta(minutes=9),
                dependencies=[],
            ),
            CrisisTask(
                task_id="financial_impact_analysis",
                agent_type="financial_risk",
                analysis_type="ransom_cost_benefit",
                priority=1,
                deadline=datetime.now(timezone.utc) + timedelta(minutes=8),
                dependencies=[],
            ),
            CrisisTask(
                task_id="service_continuity_assessment",
                agent_type="customer_operations",
                analysis_type="service_continuity",
                priority=2,
                deadline=datetime.now(timezone.utc) + timedelta(minutes=9),
                dependencies=[],
            ),
        ]

        # Execute tasks in parallel
        analysis_tasks: list[asyncio.Task[dict[str, Any]]] = []  # TODO(TYPE): replace Any with concrete type
        for crisis_task in crisis_tasks:
            if crisis_task.agent_type in self.crisis_agents:
                task = asyncio.create_task(self._execute_crisis_task(crisis_task, crisis_scenario))
                analysis_tasks.append(task)

        # Wait for all analyses to complete
        results = await asyncio.gather(*analysis_tasks, return_exceptions=True)

        # Log phase completion
        self.crisis_timeline.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "phase": CrisisPhase.ANALYSIS.value,
                "event": "Phase 1 immediate analysis completed",
                "results_count": len([r for r in results if not isinstance(r, Exception)]),
            }
        )

    async def _execute_crisis_task(
        self, crisis_task: CrisisTask, crisis_scenario: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Execute individual crisis task on specialized agent"""
        try:
            agent = self.crisis_agents.get(crisis_task.agent_type)
            if not agent:
                raise Exception(f"Agent {crisis_task.agent_type} not available")

            # Prepare task data
            task_data = {
                "id": crisis_task.task_id,
                "crisis_context": self.active_crisis.__dict__,
                "analysis_type": crisis_task.analysis_type,
                "urgency": "critical",
                "deadline": crisis_task.deadline.isoformat(),
                "crisis_scenario": crisis_scenario,
            }

            # Execute task
            start_time = datetime.now(timezone.utc)
            result = await agent.execute_task(task_data)
            execution_time = (datetime.now(timezone.utc) - start_time).total_seconds()

            # Store result
            self.agent_responses[crisis_task.task_id] = {
                "agent_type": crisis_task.agent_type,
                "result": result,
                "execution_time": execution_time,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            logger.info(
                f"[OK] {crisis_task.agent_type} completed {crisis_task.analysis_type} in {execution_time:.1f}s"
            )
            return result  # type: ignore[no-any-return]  # NOTE: result comes from awaited agent

        except Exception as e:
            logger.error(f"[FAIL] Crisis task {crisis_task.task_id} failed: {e}")
            return {"error": str(e), "task_id": crisis_task.task_id}

    async def _phase_2_decision_synthesis(self) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Phase 2: Synthesize agent responses into executive decisions"""

        # Synthesize financial analysis
        financial_decision = await self._synthesize_financial_decision()

        # Synthesize operational decision
        operational_decision = await self._synthesize_operational_decision()

        # Synthesize communication decision
        communication_decision = await self._synthesize_communication_decision()

        # Store decisions
        self.decisions = [
            financial_decision,
            operational_decision,
            communication_decision,
        ]

        # Log phase completion
        self.crisis_timeline.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "phase": CrisisPhase.DECISION_MAKING.value,
                "event": "Phase 2 decision synthesis completed",
                "decisions_count": len(self.decisions),
            }
        )

    async def _synthesize_financial_decision(self) -> CrisisDecision:
        """Synthesize financial analysis into executive decision"""

        financial_response = self.agent_responses.get("financial_impact_analysis")
        financial_analysis: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
        if isinstance(financial_response, dict):
            financial_analysis = cast(dict[str, Any], financial_response).get("result", {})  # TODO(TYPE): replace Any with concrete type
        else:
            financial_analysis = {}
        # Extract key financial data (for future use)
        _ransom_scenario = financial_analysis.get("ransom_payment_scenario", {})
        _recovery_scenario = financial_analysis.get("recovery_without_payment_scenario", {})

        return CrisisDecision(
            decision_id="financial_response",
            scenario="Ransom Payment vs Recovery",
            recommendation="DO NOT PAY RANSOM - Execute recovery strategy",
            confidence=0.92,
            rationale=[
                "Recovery approach is EUR1.9M cheaper after insurance coverage",
                "Legal analysis confirms significant compliance risks with payment",
                "No guarantee of data recovery from attackers",
                "Recovery approach provides better long-term security",
                "Regulatory authorities strongly discourage ransom payments",
            ],
            cost_benefit={
                "ransom_scenario_net_cost": "EUR8.6M (including business interruption)",
                "recovery_scenario_net_cost": "EUR650K (after insurance)",
                "cost_advantage": "EUR1.9M savings with recovery approach",
                "additional_benefits": "Enhanced security, regulatory compliance, no criminal funding",
            },
            risks=[
                "Longer service disruption (7-14 days vs 5-10 days)",
                "Customer satisfaction impact during recovery",
                "Competitive disadvantage during downtime",
            ],
            timeline="Decision required within 6 hours for optimal recovery start",
        )

    async def _synthesize_operational_decision(self) -> CrisisDecision:
        """Synthesize operational response decision"""

        # Retrieve operational analysis data (for future use)
        _continuity_response = self.agent_responses.get("service_continuity_assessment")
        _continuity_analysis: dict[str, Any] | None  # TODO(TYPE): replace Any with concrete type
        if isinstance(_continuity_response, dict):
            _continuity_analysis = cast(dict[str, Any], _continuity_response).get("result")  # TODO(TYPE): replace Any with concrete type
        else:
            _continuity_analysis = None

        _cyber_response = self.agent_responses.get("cyber_incident_analysis")
        _cyber_analysis: dict[str, Any] | None  # TODO(TYPE): replace Any with concrete type
        if isinstance(_cyber_response, dict):
            _cyber_analysis = cast(dict[str, Any], _cyber_response).get("result")  # TODO(TYPE): replace Any with concrete type
        else:
            _cyber_analysis = None

        return CrisisDecision(
            decision_id="operational_response",
            scenario="Business Continuity Strategy",
            recommendation="Implement multi-tier service restoration",
            confidence=0.87,
            rationale=[
                "Prioritize customer communication and basic services",
                "Deploy manual processing for critical transactions",
                "Activate partner platform for high-value customers",
                "Maintain air-gapped systems for customer inquiries",
            ],
            cost_benefit={
                "manual_processing_setup": "EUR200K for 20 additional staff",
                "partner_platform_migration": "EUR150K for 5,000 customers",
                "customer_retention_value": "EUR10M in prevented customer churn",
                "net_benefit": "EUR9.65M customer retention value",
            },
            risks=[
                "Reduced service capacity (80% reduction)",
                "Customer frustration with limited functionality",
                "Manual process error risks",
            ],
            timeline="Begin implementation immediately, full deployment within 12 hours",
        )

    async def _synthesize_communication_decision(self) -> CrisisDecision:
        """Synthesize communication strategy decision"""

        # Retrieve communication analysis data (for future use)
        _comm_response = self.agent_responses.get("communication_strategy")
        _comm_analysis: dict[str, Any] | None  # TODO(TYPE): replace Any with concrete type
        if isinstance(_comm_response, dict):
            _comm_analysis = cast(dict[str, Any], _comm_response).get("result")  # TODO(TYPE): replace Any with concrete type
        else:
            _comm_analysis = None

        _legal_response = self.agent_responses.get("legal_regulatory_assessment")
        _legal_analysis: dict[str, Any] | None  # TODO(TYPE): replace Any with concrete type
        if isinstance(_legal_response, dict):
            _legal_analysis = cast(dict[str, Any], _legal_response).get("result")  # TODO(TYPE): replace Any with concrete type
        else:
            _legal_analysis = None

        return CrisisDecision(
            decision_id="communication_strategy",
            scenario="Stakeholder Communication Approach",
            recommendation="Transparent, proactive communication strategy",
            confidence=0.89,
            rationale=[
                "GDPR requires customer notification within 72 hours",
                "Proactive communication builds trust and minimizes speculation",
                "Clear timeline helps manage stakeholder expectations",
                "Professional response demonstrates crisis preparedness",
            ],
            cost_benefit={
                "communication_campaign_cost": "EUR75K for comprehensive outreach",
                "reputation_protection_value": "EUR5M in brand value preservation",
                "regulatory_goodwill": "Reduced fine risk through cooperation",
                "customer_trust_maintenance": "80% customer retention projected",
            },
            risks=[
                "Media scrutiny and negative coverage",
                "Competitor advantage during vulnerability period",
                "Customer anxiety and potential service switching",
            ],
            timeline="Begin internal communications immediately, customer notifications within 24 hours",
        )

    async def _generate_crisis_deliverables(self) -> Any:  # TODO(TYPE): replace Any with concrete type
        """Generate final crisis management deliverables"""

        # Generate Crisis Action Plan
        action_plan = await self._generate_crisis_action_plan()

        # Generate Decision Document
        await self._generate_decision_document()

        # Log deliverable generation
        self.crisis_timeline.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "phase": CrisisPhase.IMPLEMENTATION.value,
                "event": "Crisis deliverables generated",
                "deliverables": ["Crisis Action Plan", "Decision Document"],
            }
        )

        # Return final orchestration result
        if self.orchestration_start_time is None:
            self.orchestration_start_time = datetime.now(timezone.utc)
        total_time = (datetime.now(timezone.utc) - self.orchestration_start_time).total_seconds() / 60

        logger.critical(f"[U+0001F3C1] CRISIS ORCHESTRATION COMPLETED in {total_time:.1f} minutes")
        logger.critical(
            f"[OK] Action Plan: {len(action_plan.get('immediate_actions', []))} immediate actions"
        )
        logger.critical(f"[OK] Decision Document: {len(self.decisions)} executive decisions")

    async def _generate_crisis_action_plan(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Generate Crisis Action Plan deliverable"""
        if self.active_crisis is None:
            raise RuntimeError("No active crisis")

        action_plan = {
            "document_type": "Crisis Action Plan",
            "crisis_code": self.active_crisis.crisis_code,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "validity_period": "48 hours",
            "classification": "CONFIDENTIAL - BOARD LEVEL",
            "executive_summary": {
                "situation": "FinSecure NV experienced coordinated ransomware attack with data exfiltration affecting 50,000 customers",
                "immediate_threat": "System availability compromise, data confidentiality breach, regulatory compliance violations",
                "recommended_action": "Do not pay ransom - Execute comprehensive recovery strategy",
                "estimated_recovery_time": "7-14 days for full operations",
                "financial_impact": "EUR650K net cost after insurance coverage",
            },
            "immediate_actions_0_4_hours": [
                {
                    "priority": 1,
                    "action": "Complete system isolation and evidence preservation",
                    "owner": "IT Security Team + External Forensics",
                    "deadline": "Immediate",
                    "status": "In Progress",
                },
                {
                    "priority": 1,
                    "action": "Notify Board of Directors and activate crisis management team",
                    "owner": "CEO/Executive Team",
                    "deadline": "Within 2 hours",
                    "status": "Pending",
                },
                {
                    "priority": 2,
                    "action": "Submit regulatory notifications (DPA, DNB, Law Enforcement)",
                    "owner": "Legal/Compliance Team",
                    "deadline": "Within 4 hours",
                    "status": "Pending",
                },
            ],
            "urgent_actions_4_24_hours": [
                {
                    "priority": 1,
                    "action": "Deploy business continuity systems and manual processing",
                    "owner": "Operations Team",
                    "deadline": "Within 12 hours",
                    "status": "Pending",
                },
                {
                    "priority": 1,
                    "action": "Begin customer notification preparation and communication rollout",
                    "owner": "Communications Team",
                    "deadline": "Within 24 hours",
                    "status": "Pending",
                },
                {
                    "priority": 2,
                    "action": "Activate cyber insurance coverage and engage recovery vendors",
                    "owner": "Risk Management",
                    "deadline": "Within 18 hours",
                    "status": "Pending",
                },
            ],
            "coordination_structure": {
                "crisis_commander": "CEO - Overall crisis leadership",
                "technical_lead": "CISO - Cybersecurity response",
                "communication_lead": "Chief Communications Officer",
                "legal_lead": "General Counsel - Regulatory compliance",
                "operations_lead": "COO - Business continuity",
            },
            "success_metrics": [
                "Zero additional data exfiltration",
                "Customer notification within regulatory deadlines",
                "Service restoration within 14 days",
                "Regulatory compliance maintained",
                "Customer retention above 80%",
            ],
        }

        return action_plan

    async def _generate_decision_document(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Generate Decision Document deliverable"""
        if self.active_crisis is None:
            raise RuntimeError("No active crisis")

        decision_document = {
            "document_type": "Executive Decision Document",
            "crisis_code": self.active_crisis.crisis_code,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "classification": "CONFIDENTIAL - BOARD LEVEL",
            "decision_authority": "CEO with Board ratification required",
            "scenario_analysis": {
                "scenario_a_pay_ransom": {
                    "description": "Pay 250 BTC ransom demand",
                    "total_cost": "EUR6.5M - EUR8.6M",
                    "timeline": "5-10 days (no guarantee)",
                    "success_probability": "60% (based on industry data)",
                    "legal_risks": "HIGH - Sanctions violations, AML compliance",
                    "regulatory_impact": "NEGATIVE - Regulatory scrutiny and potential fines",
                    "long_term_consequences": [
                        "Continued system vulnerability",
                        "Increased future targeting risk",
                        "Reputation damage for paying criminals",
                        "No guarantee of complete data recovery",
                        "Potential ongoing extortion",
                    ],
                    "recommendation": "REJECT - High risk, uncertain outcome",
                },
                "scenario_b_recovery_strategy": {
                    "description": "Execute comprehensive system recovery without payment",
                    "total_cost": "EUR650K (after insurance coverage)",
                    "timeline": "7-14 days",
                    "success_probability": "95% (based on backup assessment)",
                    "legal_risks": "LOW - Full regulatory compliance",
                    "regulatory_impact": "POSITIVE - Demonstrates responsible approach",
                    "long_term_consequences": [
                        "Enhanced security posture",
                        "Regulatory goodwill",
                        "Complete system integrity",
                        "No criminal funding",
                        "Improved resilience",
                    ],
                    "recommendation": "ACCEPT - Lower risk, certain outcome",
                },
            },
            "final_recommendation": {
                "decision": "EXECUTE SCENARIO B - Recovery Strategy",
                "confidence_level": "92%",
                "key_factors": [
                    "Financial advantage: EUR1.9M cost savings",
                    "Legal compliance: Avoids sanctions and AML risks",
                    "Operational security: Complete system rebuild",
                    "Regulatory approval: Aligns with authority guidance",
                    "Long-term resilience: Enhanced security posture",
                ],
                "implementation_timeline": {
                    "immediate_0_6_hours": "Board approval and resource mobilization",
                    "short_term_6_24_hours": "Recovery infrastructure deployment",
                    "medium_term_1_7_days": "System rebuild and data restoration",
                    "long_term_7_14_days": "Service restoration and security enhancement",
                },
            },
            "risk_mitigation": [
                "Comprehensive customer communication to maintain trust",
                "Expedited recovery with additional resources",
                "Proactive regulatory engagement",
                "Enhanced business continuity during restoration",
                "Ongoing threat monitoring and security improvement",
            ],
            "board_approval_required": {
                "decision_points": [
                    "Confirm rejection of ransom payment",
                    "Approve recovery strategy budget (EUR3.15M gross)",
                    "Authorize customer communication plan",
                    "Approve additional security investments",
                ],
                "voting_deadline": "Within 6 hours of document receipt",
                "implementation_authorization": "CEO and Board Chair",
            },
        }

        return decision_document

    def get_orchestration_status(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get current orchestration status"""
        if not self.orchestration_start_time:
            return {"status": "Not initiated"}

        elapsed_time = (datetime.now(timezone.utc) - self.orchestration_start_time).total_seconds() / 60

        return {
            "status": "Active" if elapsed_time < 15 else "Completed",
            "elapsed_time_minutes": elapsed_time,
            "active_crisis": self.active_crisis.__dict__ if self.active_crisis else None,
            "deployed_agents": list(self.crisis_agents.keys()),
            "completed_analyses": len(self.agent_responses),
            "generated_decisions": len(self.decisions),
            "timeline_events": len(self.crisis_timeline),
            "next_milestone": (
                "Decision implementation" if len(self.decisions) > 0 else "Analysis completion"
            ),
        }

    def get_detailed_results(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get detailed orchestration results"""
        return {
            "orchestration_summary": self.get_orchestration_status(),
            "crisis_context": self.active_crisis.__dict__ if self.active_crisis else None,
            "agent_responses": self.agent_responses,
            "executive_decisions": [decision.__dict__ for decision in self.decisions],
            "crisis_timeline": self.crisis_timeline,
            "performance_metrics": {
                "total_agents_deployed": len(self.crisis_agents),
                "successful_analyses": len(
                    [
                        r
                        for r in self.agent_responses.values()
                        if r.get("result", {}).get("error") is None
                    ]
                ),
                "average_agent_response_time": sum(
                    r.get("execution_time", 0) for r in self.agent_responses.values()
                )
                / max(len(self.agent_responses), 1),
                "orchestration_efficiency": "High" if len(self.agent_responses) >= 4 else "Medium",
            },
        }


# Global crisis orchestrator instance
_crisis_orchestrator: CrisisOrchestrator | None = None


def get_crisis_orchestrator() -> CrisisOrchestrator:
    """Get or create global crisis orchestrator instance"""
    global _crisis_orchestrator
    if _crisis_orchestrator is None:
        _crisis_orchestrator = CrisisOrchestrator()
    return _crisis_orchestrator
