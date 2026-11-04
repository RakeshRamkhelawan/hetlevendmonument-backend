"""
Organism Registry - 41-Agent Registration System

Registry for the complete organogram:
- 1 Chief Orchestrator
- 40 Department-level Agents across 10 organizational layers

Organizational Structure:
|-- ChiefOrchestrator (1)
|-- Product & Innovation (R&D) (4)
|-- Operations & Supply Chain (4)
|-- Sales & Marketing (4)
|-- Finance & Treasury (4)
|-- HR & Culture (4)
|-- IT & Security (4)
|-- Legal & Compliance (4)
|-- Customer Experience (4)
|-- Strategy & Business (4) - includes 1 Human role
`-- Data & AI Governance (4)

Total: 41 agents
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from src.core.als.agents.chief_orchestrator import ChiefOrchestrator
from src.core.als.agents.departments.base_department_agent import (
    AgentTechnology,
    DepartmentAgent,
    DepartmentType,
)
from src.core.als.agents.departments.customer_experience.sentiment_support import (
    SentimentSupportAgent,
)
from src.core.als.agents.departments.data_ai_governance.data_quality_sentinel import (
    DataQualitySentinelAgent,
)
from src.core.als.agents.departments.it_security.threat_hunter import ThreatHunterAgent
from src.core.als.agents.departments.legal_compliance.gdpr_privacy_guard import (
    GDPRPrivacyGuardAgent,
)
from src.core.als.agents.departments.operations_supply_chain.inventory_forecaster import (
    InventoryForecasterAgent,
)

# Import Critical Agents (Phase 1 - 6 agents)
from src.core.als.agents.departments.product_innovation.technical_architect import (
    TechnicalArchitectAgent,
)
from src.core.als.infrastructure.signal_bus import SignalBus

logger = logging.getLogger(__name__)


class AgentPriority(str, Enum):
    """Agent priority levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"


@dataclass
class AgentRegistration:
    """Agent registration metadata."""

    agent_id: str
    agent_class: type[DepartmentAgent]
    department: DepartmentType
    technology: AgentTechnology
    priority: AgentPriority
    description: str
    human_role: bool = False


class OrganismRegistry:
    """
    Central registry for all 41 agents in the organogram.

    Manages agent registration, discovery, and instantiation.
    """

    def __init__(self) -> None:
        self._registrations: dict[str, AgentRegistration] = {}
        self._instances: dict[str, DepartmentAgent] = {}
        self._chief_orchestrator: ChiefOrchestrator | None = None

        self._register_all_agents()

    def _register_all_agents(self) -> None:
        """Register all 41 agents."""

        # =================================================================
        # PRODUCT & INNOVATION (R&D) - 4 agents
        # =================================================================
        self._register(
            AgentRegistration(
                agent_id="technical_architect",
                agent_class=TechnicalArchitectAgent,
                department=DepartmentType.PRODUCT_INNOVATION,
                technology=AgentTechnology.LLM,
                priority=AgentPriority.CRITICAL,
                description="System design, architecture decisions, technical strategy",
            )
        )

        self._register(
            AgentRegistration(
                agent_id="rnd_prototyping",
                agent_class=TechnicalArchitectAgent,  # Placeholder
                department=DepartmentType.PRODUCT_INNOVATION,
                technology=AgentTechnology.ML,
                priority=AgentPriority.HIGH,
                description="Rapid prototyping, MVP validation, feature experimentation",
            )
        )

        self._register(
            AgentRegistration(
                agent_id="market_gap_analysis",
                agent_class=TechnicalArchitectAgent,  # Placeholder
                department=DepartmentType.PRODUCT_INNOVATION,
                technology=AgentTechnology.ML,
                priority=AgentPriority.HIGH,
                description="Market opportunity identification, competitive gap analysis",
            )
        )

        self._register(
            AgentRegistration(
                agent_id="ux_ui_designer",
                agent_class=TechnicalArchitectAgent,  # Placeholder
                department=DepartmentType.PRODUCT_INNOVATION,
                technology=AgentTechnology.VISION,
                priority=AgentPriority.MEDIUM,
                description="UI/UX design synthesis, visual design generation",
            )
        )

        # =================================================================
        # OPERATIONS & SUPPLY CHAIN - 4 agents
        # =================================================================
        self._register(
            AgentRegistration(
                agent_id="inventory_forecaster",
                agent_class=InventoryForecasterAgent,
                department=DepartmentType.OPERATIONS_SUPPLY_CHAIN,
                technology=AgentTechnology.ML,
                priority=AgentPriority.CRITICAL,
                description="Demand forecasting, inventory optimization, stock prediction",
            )
        )

        self._register(
            AgentRegistration(
                agent_id="logistics_optimizer",
                agent_class=InventoryForecasterAgent,  # Placeholder
                department=DepartmentType.OPERATIONS_SUPPLY_CHAIN,
                technology=AgentTechnology.ML,
                priority=AgentPriority.HIGH,
                description="Route optimization, shipping cost reduction, logistics planning",
            )
        )

        self._register(
            AgentRegistration(
                agent_id="production_scheduler",
                agent_class=InventoryForecasterAgent,  # Placeholder
                department=DepartmentType.OPERATIONS_SUPPLY_CHAIN,
                technology=AgentTechnology.ML,
                priority=AgentPriority.HIGH,
                description="Production planning, capacity optimization, scheduling",
            )
        )

        self._register(
            AgentRegistration(
                agent_id="supplier_risk_assessor",
                agent_class=InventoryForecasterAgent,  # Placeholder
                department=DepartmentType.OPERATIONS_SUPPLY_CHAIN,
                technology=AgentTechnology.ML,
                priority=AgentPriority.MEDIUM,
                description="Supplier evaluation, risk assessment, vendor monitoring",
            )
        )

        # =================================================================
        # SALES & MARKETING - 4 agents
        # =================================================================
        self._register(
            AgentRegistration(
                agent_id="campaign_performance",
                agent_class=TechnicalArchitectAgent,  # Placeholder
                department=DepartmentType.SALES_MARKETING,
                technology=AgentTechnology.ML,
                priority=AgentPriority.HIGH,
                description="Campaign ROI analysis, performance optimization, attribution",
            )
        )

        self._register(
            AgentRegistration(
                agent_id="lead_qualification",
                agent_class=TechnicalArchitectAgent,  # Placeholder
                department=DepartmentType.SALES_MARKETING,
                technology=AgentTechnology.ML,
                priority=AgentPriority.HIGH,
                description="Lead scoring, qualification, prioritization",
            )
        )

        self._register(
            AgentRegistration(
                agent_id="market_intelligence",
                agent_class=TechnicalArchitectAgent,  # Placeholder
                department=DepartmentType.SALES_MARKETING,
                technology=AgentTechnology.LLM,
                priority=AgentPriority.HIGH,
                description="Market research, competitive analysis, trend identification",
            )
        )

        self._register(
            AgentRegistration(
                agent_id="pricing_optimizer",
                agent_class=TechnicalArchitectAgent,  # Placeholder
                department=DepartmentType.SALES_MARKETING,
                technology=AgentTechnology.ML,
                priority=AgentPriority.MEDIUM,
                description="Dynamic pricing, revenue optimization, elasticity modeling",
            )
        )

        # =================================================================
        # FINANCE & TREASURY - 4 agents
        # =================================================================
        self._register(
            AgentRegistration(
                agent_id="financial_forecaster",
                agent_class=TechnicalArchitectAgent,  # Placeholder
                department=DepartmentType.FINANCE_TREASURY,
                technology=AgentTechnology.ML,
                priority=AgentPriority.HIGH,
                description="Financial forecasting, budget planning, variance analysis",
            )
        )

        self._register(
            AgentRegistration(
                agent_id="fraud_detector",
                agent_class=TechnicalArchitectAgent,  # Placeholder
                department=DepartmentType.FINANCE_TREASURY,
                technology=AgentTechnology.ML,
                priority=AgentPriority.CRITICAL,
                description="Transaction monitoring, fraud detection, risk scoring",
            )
        )

        self._register(
            AgentRegistration(
                agent_id="cash_flow_optimizer",
                agent_class=TechnicalArchitectAgent,  # Placeholder
                department=DepartmentType.FINANCE_TREASURY,
                technology=AgentTechnology.ML,
                priority=AgentPriority.HIGH,
                description="Cash flow forecasting, working capital optimization",
            )
        )

        self._register(
            AgentRegistration(
                agent_id="vendor_negotiation",
                agent_class=TechnicalArchitectAgent,  # Placeholder
                department=DepartmentType.FINANCE_TREASURY,
                technology=AgentTechnology.LLM,
                priority=AgentPriority.MEDIUM,
                description="Contract negotiation, terms analysis, vendor communication",
            )
        )

        # =================================================================
        # HR & CULTURE - 4 agents
        # =================================================================
        self._register(
            AgentRegistration(
                agent_id="talent_matcher",
                agent_class=TechnicalArchitectAgent,  # Placeholder
                department=DepartmentType.HR_CULTURE,
                technology=AgentTechnology.ML,
                priority=AgentPriority.HIGH,
                description="Candidate matching, skill gap analysis, recruitment optimization",
            )
        )

        self._register(
            AgentRegistration(
                agent_id="employee_sentiment",
                agent_class=TechnicalArchitectAgent,  # Placeholder
                department=DepartmentType.HR_CULTURE,
                technology=AgentTechnology.ML,
                priority=AgentPriority.HIGH,
                description="Employee engagement analysis, satisfaction monitoring",
            )
        )

        self._register(
            AgentRegistration(
                agent_id="culture_pulse",
                agent_class=TechnicalArchitectAgent,  # Placeholder
                department=DepartmentType.HR_CULTURE,
                technology=AgentTechnology.LLM,
                priority=AgentPriority.MEDIUM,
                description="Culture assessment, values alignment, team dynamics",
            )
        )

        self._register(
            AgentRegistration(
                agent_id="learning_recommender",
                agent_class=TechnicalArchitectAgent,  # Placeholder
                department=DepartmentType.HR_CULTURE,
                technology=AgentTechnology.ML,
                priority=AgentPriority.MEDIUM,
                description="Training recommendations, skill development paths",
            )
        )

        # =================================================================
        # IT & SECURITY - 4 agents
        # =================================================================
        self._register(
            AgentRegistration(
                agent_id="threat_hunter",
                agent_class=ThreatHunterAgent,
                department=DepartmentType.IT_SECURITY,
                technology=AgentTechnology.ML,
                priority=AgentPriority.CRITICAL,
                description="Threat detection, anomaly detection, security monitoring",
            )
        )

        self._register(
            AgentRegistration(
                agent_id="infrastructure_optimizer",
                agent_class=ThreatHunterAgent,  # Placeholder
                department=DepartmentType.IT_SECURITY,
                technology=AgentTechnology.ML,
                priority=AgentPriority.HIGH,
                description="Resource optimization, cost reduction, performance tuning",
            )
        )

        self._register(
            AgentRegistration(
                agent_id="devops_automation",
                agent_class=ThreatHunterAgent,  # Placeholder
                department=DepartmentType.IT_SECURITY,
                technology=AgentTechnology.LLM,
                priority=AgentPriority.HIGH,
                description="CI/CD optimization, deployment automation, script generation",
            )
        )

        self._register(
            AgentRegistration(
                agent_id="cloud_cost_controller",
                agent_class=ThreatHunterAgent,  # Placeholder
                department=DepartmentType.IT_SECURITY,
                technology=AgentTechnology.ML,
                priority=AgentPriority.MEDIUM,
                description="Cloud spending analysis, cost optimization, budget alerts",
            )
        )

        # =================================================================
        # LEGAL & COMPLIANCE - 4 agents
        # =================================================================
        self._register(
            AgentRegistration(
                agent_id="gdpr_privacy_guard",
                agent_class=GDPRPrivacyGuardAgent,
                department=DepartmentType.LEGAL_COMPLIANCE,
                technology=AgentTechnology.LLM,
                priority=AgentPriority.CRITICAL,
                description="GDPR compliance, privacy protection, data governance",
            )
        )

        self._register(
            AgentRegistration(
                agent_id="contract_analyzer",
                agent_class=GDPRPrivacyGuardAgent,  # Placeholder
                department=DepartmentType.LEGAL_COMPLIANCE,
                technology=AgentTechnology.LLM,
                priority=AgentPriority.HIGH,
                description="Contract review, risk identification, clause extraction",
            )
        )

        self._register(
            AgentRegistration(
                agent_id="ip_rights_guardian",
                agent_class=GDPRPrivacyGuardAgent,  # Placeholder
                department=DepartmentType.LEGAL_COMPLIANCE,
                technology=AgentTechnology.ML,
                priority=AgentPriority.HIGH,
                description="IP monitoring, trademark protection, infringement detection",
            )
        )

        self._register(
            AgentRegistration(
                agent_id="regulatory_tracker",
                agent_class=GDPRPrivacyGuardAgent,  # Placeholder
                department=DepartmentType.LEGAL_COMPLIANCE,
                technology=AgentTechnology.LLM,
                priority=AgentPriority.MEDIUM,
                description="Regulatory monitoring, compliance updates, policy tracking",
            )
        )

        # =================================================================
        # CUSTOMER EXPERIENCE - 4 agents
        # =================================================================
        self._register(
            AgentRegistration(
                agent_id="sentiment_support",
                agent_class=SentimentSupportAgent,
                department=DepartmentType.CUSTOMER_EXPERIENCE,
                technology=AgentTechnology.HYBRID,
                priority=AgentPriority.CRITICAL,
                description="Sentiment analysis, support automation, response generation",
            )
        )

        self._register(
            AgentRegistration(
                agent_id="churn_predictor",
                agent_class=SentimentSupportAgent,  # Placeholder
                department=DepartmentType.CUSTOMER_EXPERIENCE,
                technology=AgentTechnology.ML,
                priority=AgentPriority.HIGH,
                description="Churn prediction, retention risk scoring, early warning",
            )
        )

        self._register(
            AgentRegistration(
                agent_id="loyalty_optimizer",
                agent_class=SentimentSupportAgent,  # Placeholder
                department=DepartmentType.CUSTOMER_EXPERIENCE,
                technology=AgentTechnology.ML,
                priority=AgentPriority.MEDIUM,
                description="Loyalty program optimization, reward personalization",
            )
        )

        self._register(
            AgentRegistration(
                agent_id="feedback_synthesizer",
                agent_class=SentimentSupportAgent,  # Placeholder
                department=DepartmentType.CUSTOMER_EXPERIENCE,
                technology=AgentTechnology.LLM,
                priority=AgentPriority.MEDIUM,
                description="Feedback aggregation, insight extraction, trend analysis",
            )
        )

        # =================================================================
        # STRATEGY & BUSINESS - 4 agents (1 Human role)
        # =================================================================
        self._register(
            AgentRegistration(
                agent_id="business_model",
                agent_class=TechnicalArchitectAgent,  # Placeholder
                department=DepartmentType.STRATEGY_BUSINESS,
                technology=AgentTechnology.LLM,
                priority=AgentPriority.HIGH,
                description="Business model analysis, monetization strategy, pivot planning",
            )
        )

        self._register(
            AgentRegistration(
                agent_id="competitive_intel",
                agent_class=TechnicalArchitectAgent,  # Placeholder
                department=DepartmentType.STRATEGY_BUSINESS,
                technology=AgentTechnology.ML,
                priority=AgentPriority.HIGH,
                description="Competitive analysis, market positioning, threat assessment",
            )
        )

        self._register(
            AgentRegistration(
                agent_id="growth_lead",
                agent_class=TechnicalArchitectAgent,  # Placeholder
                department=DepartmentType.STRATEGY_BUSINESS,
                technology=AgentTechnology.LLM,
                priority=AgentPriority.CRITICAL,
                description="Growth strategy, expansion planning, market entry",
                human_role=True,  # This is a human role
            )
        )

        self._register(
            AgentRegistration(
                agent_id="m_a_analyst",
                agent_class=TechnicalArchitectAgent,  # Placeholder
                department=DepartmentType.STRATEGY_BUSINESS,
                technology=AgentTechnology.LLM,
                priority=AgentPriority.MEDIUM,
                description="M&A opportunity analysis, due diligence support, valuation",
            )
        )

        # =================================================================
        # DATA & AI GOVERNANCE - 4 agents
        # =================================================================
        self._register(
            AgentRegistration(
                agent_id="data_quality_sentinel",
                agent_class=DataQualitySentinelAgent,
                department=DepartmentType.DATA_AI_GOVERNANCE,
                technology=AgentTechnology.ML,
                priority=AgentPriority.CRITICAL,
                description="Data quality monitoring, validation, anomaly detection",
            )
        )

        self._register(
            AgentRegistration(
                agent_id="model_performance",
                agent_class=DataQualitySentinelAgent,  # Placeholder
                department=DepartmentType.DATA_AI_GOVERNANCE,
                technology=AgentTechnology.ML,
                priority=AgentPriority.HIGH,
                description="ML model monitoring, performance tracking, drift detection",
            )
        )

        self._register(
            AgentRegistration(
                agent_id="bias_detector",
                agent_class=DataQualitySentinelAgent,  # Placeholder
                department=DepartmentType.DATA_AI_GOVERNANCE,
                technology=AgentTechnology.ML,
                priority=AgentPriority.HIGH,
                description="AI bias detection, fairness assessment, ethical AI review",
            )
        )

        self._register(
            AgentRegistration(
                agent_id="data_lineage_mapper",
                agent_class=DataQualitySentinelAgent,  # Placeholder
                department=DepartmentType.DATA_AI_GOVERNANCE,
                technology=AgentTechnology.ML,
                priority=AgentPriority.MEDIUM,
                description="Data lineage tracking, impact analysis, dependency mapping",
            )
        )

        logger.info(f"OrganismRegistry initialized with {len(self._registrations)} agents")

    def _register(self, registration: AgentRegistration) -> None:
        """Register an agent."""
        self._registrations[registration.agent_id] = registration

    def create_chief_orchestrator(
        self, tenant_id: int, signal_bus: SignalBus | None = None
    ) -> ChiefOrchestrator:
        """Create and return the Chief Orchestrator."""
        if signal_bus is None:
            raise ValueError("signal_bus is required for ChiefOrchestrator")
        # cast() needed because type checker doesn't narrow after raise
        signal_bus = signal_bus
        self._chief_orchestrator = ChiefOrchestrator(tenant_id=tenant_id, signal_bus=signal_bus)
        logger.info(f"ChiefOrchestrator created for tenant {tenant_id}")
        return self._chief_orchestrator

    def create_agent(self, agent_id: str, tenant_id: int, **kwargs: object) -> DepartmentAgent | None:
        """Create and return an agent instance."""
        registration = self._registrations.get(agent_id)
        if not registration:
            logger.error(f"Unknown agent_id: {agent_id}")
            return None

        try:
            agent = registration.agent_class(agent_id=agent_id, tenant_id=tenant_id, **kwargs)
            self._instances[agent_id] = agent
            return agent
        except Exception as e:
            logger.error(f"Failed to create agent {agent_id}: {e}")
            return None

    def get_registration(self, agent_id: str) -> AgentRegistration | None:
        """Get agent registration metadata."""
        return self._registrations.get(agent_id)

    def list_agents(
        self,
        department: DepartmentType | None = None,
        priority: AgentPriority | None = None,
        technology: AgentTechnology | None = None,
    ) -> list[AgentRegistration]:
        """List agents with optional filtering."""
        results = list(self._registrations.values())

        if department:
            results = [r for r in results if r.department == department]
        if priority:
            results = [r for r in results if r.priority == priority]
        if technology:
            results = [r for r in results if r.technology == technology]

        return results

    def get_department_agents(self, department: DepartmentType) -> list[AgentRegistration]:
        """Get all agents for a department."""
        return [r for r in self._registrations.values() if r.department == department]

    def get_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get registry statistics."""
        return {
            "total_agents": len(self._registrations),
            "departments": len(list(DepartmentType)),
            "critical_agents": len(
                [r for r in self._registrations.values() if r.priority == AgentPriority.CRITICAL]
            ),
            "high_priority": len(
                [r for r in self._registrations.values() if r.priority == AgentPriority.HIGH]
            ),
            "medium_priority": len(
                [r for r in self._registrations.values() if r.priority == AgentPriority.MEDIUM]
            ),
            "ml_agents": len(
                [r for r in self._registrations.values() if r.technology == AgentTechnology.ML]
            ),
            "llm_agents": len(
                [r for r in self._registrations.values() if r.technology == AgentTechnology.LLM]
            ),
            "vision_agents": len(
                [r for r in self._registrations.values() if r.technology == AgentTechnology.VISION]
            ),
            "hybrid_agents": len(
                [r for r in self._registrations.values() if r.technology == AgentTechnology.HYBRID]
            ),
            "human_roles": len([r for r in self._registrations.values() if r.human_role]),
            "chief_orchestrator": self._chief_orchestrator is not None,
        }

    def create_full_organism(
        self, tenant_id: int, signal_bus: SignalBus | None = None
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Create the full 41-agent organism."""
        # Create Chief Orchestrator
        chief = self.create_chief_orchestrator(tenant_id, signal_bus)

        # Create all department agents
        created: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        failed: list[Any] = []  # TODO(TYPE): replace Any with concrete type
        for agent_id in self._registrations.keys():
            agent = self.create_agent(agent_id, tenant_id)
            if agent:
                created.append(agent_id)
            else:
                failed.append(agent_id)

        return {
            "chief_orchestrator": chief,
            "agents_created": created,
            "agents_failed": failed,
            "total_created": len(created),
            "total_failed": len(failed),
        }


# Global registry instance
_registry_instance: OrganismRegistry | None = None


def get_organism_registry() -> OrganismRegistry:
    """Get or create the global organism registry."""
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = OrganismRegistry()
    return _registry_instance
