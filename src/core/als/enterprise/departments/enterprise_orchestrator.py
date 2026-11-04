"""
EnterpriseOrchestrator - Enterprise Implementation.

Manages 10 departments (Strategy, Product Innovation, Operations, Sales & Marketing,
Finance, HR, IT Security, Legal, Customer Experience, Data & AI Governance) with:
- Deterministic routing (no LLM)
- Prana economy (10,000 tokens per department)
- Cross-department A2A contract negotiation

Architecture:
    +-------------------------------------------------------------+
    |              EnterpriseOrchestrator                         |
    |         (routing, contracts, coordination)                  |
    +--------------+----------------------------------------------+
                   |
    +--------------+--------------+--------------+--------------+
    v              v              v              v              v
+--------+   +----------+  +----------+  +----------+  +----------+
|STRATEGY|   | PRODUCT  |  |OPERATIONS|  | SALES &  |  | FINANCE  |
| 10,000 |   |INNOVATION|  |  10,000  |  | MARKETING|  |  10,000  |
+--------+   |  10,000  |  +----------+  |  10,000  |  +----------+
             +----------+                +----------+
+--------+   +----------+  +----------+  +----------+  +----------+
|   HR   |   |IT_SECURITY| |  LEGAL   |  |   CX     |  |DATA & AI |
| 10,000 |   |  10,000  |  | 10,000   |  |  10,000  |  | 10,000   |
+--------+   +----------+  +----------+  +----------+  +----------+

Total: 1 Chief Orchestrator + 40 Department Agents across 10 Departments
"""

import logging
from dataclasses import dataclass
from typing import Any, Optional

from src.core.als.enterprise.contracts.models import A2AContract, ContractProposal, ContractState
from src.core.als.enterprise.contracts.schema_registry import SchemaRef, SchemaRegistry
from src.core.als.enterprise.contracts.settlement import PranaLedger
from src.core.als.enterprise.contracts.state_machine import ActorRole, ContractStateMachine
from src.core.als.enterprise.contracts.validator import ContractValidator
from src.core.als.enterprise.departments.department_orchestrator import (
    Department,
    DepartmentOrchestrator,
)
from src.core.als.enterprise.departments.deterministic_router import DeterministicRouter

logger = logging.getLogger("EnterpriseOrchestrator")


@dataclass
class DepartmentStatus:
    """Status snapshot of a department."""

    department: Department
    is_online: bool
    prana_available: int
    prana_total: int = 10000
    agent_count: int = 0
    pending_contracts: int = 0

    @property
    def health_score(self) -> float:
        """Calculate health score (0-1) based on available resources."""
        # Health based on prana availability regardless of online status
        prana_ratio = self.prana_available / self.prana_total
        return min(1.0, prana_ratio)


@dataclass
class EnterpriseMetrics:
    """Enterprise-wide metrics and KPIs."""

    total_departments: int = 10
    online_departments: int = 0
    total_prana_available: int = 0
    total_prana_capacity: int = 100000  # 10 depts * 10,000 each
    total_agents: int = 0
    active_contracts: int = 0
    pending_proposals: int = 0
    cross_department_collaborations: int = 0


class EnterpriseOrchestrator:
    """
    Enterprise Orchestrator with 10 Departments.

    Manages all enterprise departments with:
    - Deterministic task routing (no LLM)
    - Prana economy (10,000 per department)
    - A2A contract lifecycle management

    Departments:
        1. STRATEGY - Market intelligence, M&A, partnerships, strategic planning
        2. PRODUCT_INNOVATION - R&D, architecture, UX/UI, QA
        3. OPERATIONS_SUPPLY_CHAIN - Process mining, logistics, procurement
        4. SALES_MARKETING - Lead gen, pricing, content, growth
        5. FINANCE - Treasury, accounting, audit, tax, investment
        6. HR - Talent acquisition, culture, training, mobility
        7. IT_SECURITY - Threat hunting, cloud orchestration, DevSecOps
        8. LEGAL_COMPLIANCE - Contracts, GDPR, regulatory tracking
        9. CUSTOMER_EXPERIENCE - Support, success, sentiment, community
        10. DATA_AI_GOVERNANCE - Data quality, AI ethics, ML models
    """

    # All 10 Enterprise Departments
    DEPARTMENTS = [
        Department.STRATEGY,
        Department.PRODUCT_INNOVATION,
        Department.OPERATIONS_SUPPLY_CHAIN,
        Department.SALES_MARKETING,
        Department.FINANCE,
        Department.HR,
        Department.IT_SECURITY,
        Department.LEGAL_COMPLIANCE,
        Department.CUSTOMER_EXPERIENCE,
        Department.DATA_AI_GOVERNANCE,
    ]
    PRANA_PER_DEPARTMENT = 10000

    def __init__(
        self,
        tenant_id: int,
        signal_bus: Any = None,  # Optional for initialization
        schema_registry: SchemaRegistry | None = None,
    ) -> None:
        self.tenant_id = tenant_id
        self.signal_bus = signal_bus
        self.schema_registry = schema_registry or SchemaRegistry()
        self.router = DeterministicRouter()
        self.validator = ContractValidator(self.schema_registry)

        # Departments (initialized on demand)
        self._departments: dict[Department, DepartmentOrchestrator | None] = {
            dept: None for dept in self.DEPARTMENTS
        }

        # Prana ledger for cross-department accounting
        self.prana_ledger = PranaLedger()
        self._initialize_prana_budgets()

        # Active contracts
        self._contracts: dict[str, A2AContract] = {}
        self._pending_proposals: dict[str, tuple[ContractProposal, Department]] = {}

        # Metrics tracking
        self._metrics = EnterpriseMetrics()
        self._initialized = False

        logger.info(
            "EnterpriseOrchestrator initialized",
            extra={
                "tenant_id": tenant_id,
                "departments": [d.value for d in self.DEPARTMENTS],
                "total_departments": len(self.DEPARTMENTS),
                "total_prana": len(self.DEPARTMENTS) * self.PRANA_PER_DEPARTMENT,
            },
        )

    def _initialize_prana_budgets(self) -> None:
        """Initialize prana budgets for all 10 departments."""
        for dept in self.DEPARTMENTS:
            dept_id = f"dept_{dept.value}_{self.tenant_id}"
            self.prana_ledger.deposit(dept_id, self.PRANA_PER_DEPARTMENT)
            logger.debug(f"Initialized {self.PRANA_PER_DEPARTMENT} prana for {dept.value}")

    async def initialize(self) -> bool:
        """Initialize all departments."""
        try:
            for dept in self.DEPARTMENTS:
                if self.signal_bus:
                    orchestrator = DepartmentOrchestrator(
                        department=dept,
                        tenant_id=self.tenant_id,
                        signal_bus=self.signal_bus,
                    )
                    await orchestrator.initialize()
                    self._departments[dept] = orchestrator
                else:
                    # Without signal bus, just mark as ready
                    self._departments[dept] = None

            self._initialized = True
            self._update_metrics()
            logger.info(f"EnterpriseOrchestrator ready with {len(self.DEPARTMENTS)} departments")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize: {e}")
            return False

    def _update_metrics(self) -> None:
        """Update enterprise metrics."""
        self._metrics.total_departments = len(self.DEPARTMENTS)
        self._metrics.online_departments = sum(
            1 for dept, orch in self._departments.items() if orch is not None
        )
        self._metrics.total_prana_available = sum(
            self.get_department_prana(dept) for dept in self.DEPARTMENTS
        )
        self._metrics.active_contracts = sum(
            1 for c in self._contracts.values() if c.state == ContractState.AGREED
        )
        self._metrics.pending_proposals = len(self._pending_proposals)

    def get_department_prana(self, department: Department) -> int:
        """Get available prana for a department."""
        dept_id = f"dept_{department.value}_{self.tenant_id}"
        return self.prana_ledger.get_balance(dept_id)

    def get_all_prana_status(self) -> dict[Department, int]:
        """Get prana status for all departments."""
        return {dept: self.get_department_prana(dept) for dept in self.DEPARTMENTS}

    def route_task(self, task_type: str, task_description: str = "") -> Department | None:
        """
        Route task to appropriate department using deterministic rules.

        NON-NEGOTIABLE: No LLM involved - pure rule-based routing.

        Returns:
            Department enum or None if no route found
        """
        available_prana = self.get_all_prana_status()
        return self.router.route(task_type, task_description, available_prana)

    def create_contract_proposal(
        self,
        producer: Department,
        consumer: Department,
        schema_ref: SchemaRef,
        deadline_ms: int = 5000,
        prana_cost: int = 50,
        required_fields: list[str] | None = None,
    ) -> ContractProposal:
        """
        Create a cross-department A2A contract proposal.

        Args:
            producer: Department providing the service
            consumer: Department consuming the service
            schema_ref: Schema reference for data format
            deadline_ms: SLA deadline in milliseconds
            prana_cost: Prana tokens to transfer on settlement
            required_fields: Required fields in the contract schema

        Returns:
            ContractProposal ready for negotiation

        Raises:
            ValueError: If departments not valid or insufficient prana
        """
        # Validate departments
        if producer not in self.DEPARTMENTS:
            raise ValueError(f"Producer {producer} not in enterprise departments")
        if consumer not in self.DEPARTMENTS:
            raise ValueError(f"Consumer {consumer} not in enterprise departments")

        # Check consumer has prana
        consumer_prana = self.get_department_prana(consumer)
        if consumer_prana < prana_cost:
            raise ValueError(
                f"Consumer {consumer.value} has insufficient prana: {consumer_prana} < {prana_cost}"
            )

        import uuid

        proposal_id = str(uuid.uuid4())

        proposal = ContractProposal(
            consumer_agent=f"dept_{consumer.value}",
            consumer_department=consumer,
            schema_ref=schema_ref,
            required_fields=required_fields or [],
            deadline_ms=deadline_ms,
            prana_offer=prana_cost,
        )

        # Store with generated ID
        self._pending_proposals[proposal_id] = (proposal, producer)

        logger.info(
            "Contract proposal created",
            extra={
                "proposal_id": proposal_id,
                "producer": producer.value,
                "consumer": consumer.value,
                "prana_cost": prana_cost,
            },
        )

        # Attach ID for tests
        proposal.proposal_id = proposal_id
        return proposal

    def accept_proposal(self, proposal_id: str) -> A2AContract:
        """
        Accept a pending contract proposal.

        Transitions proposal -> AGREED contract.
        """
        if proposal_id not in self._pending_proposals:
            raise ValueError(f"Proposal {proposal_id} not found")

        proposal, producer = self._pending_proposals.pop(proposal_id)

        # Generate contract ID and get schema hash
        import uuid

        contract_id = str(uuid.uuid4())

        # Get schema from registry
        schema = self.schema_registry.get(proposal.schema_ref.ref)
        schema_hash = schema.compute_hash() if schema else "unknown"

        # Create contract from proposal
        contract = proposal.to_contract(
            contract_id=contract_id,
            tenant_id=self.tenant_id,
            producer_agent=f"dept_{producer.value}",
            producer_department=producer,
            schema_hash=schema_hash,
        )

        # Validate state transition (PROPOSED -> AGREED)
        ContractStateMachine.transition(
            ContractState.PROPOSED, ContractState.AGREED, ActorRole.PRODUCER
        )
        contract.state = ContractState.AGREED

        # Store contract
        self._contracts[contract.contract_id] = contract

        # Update metrics
        self._update_metrics()

        logger.info(
            "Contract accepted",
            extra={"contract_id": contract.contract_id, "proposal_id": proposal_id},
        )

        return contract

    def reject_proposal(self, proposal_id: str, reason: str = "") -> None:
        """Reject a pending contract proposal."""
        if proposal_id not in self._pending_proposals:
            raise ValueError(f"Proposal {proposal_id} not found")

        self._pending_proposals.pop(proposal_id)

        logger.info("Proposal rejected", extra={"proposal_id": proposal_id, "reason": reason})

    def get_department_status(self, department: Department) -> DepartmentStatus:
        """Get current status of a department."""
        prana = self.get_department_prana(department)
        orchestrator = self._departments.get(department)

        agent_count = 0
        if orchestrator:
            health = orchestrator.get_department_health()
            agent_count = health.get("total_agents", 0)

        pending = sum(
            1
            for c in self._contracts.values()
            if c.consumer_department == department and c.state == ContractState.PROPOSED
        )

        return DepartmentStatus(
            department=department,
            is_online=self._initialized,
            prana_available=prana,
            prana_total=self.PRANA_PER_DEPARTMENT,
            agent_count=agent_count,
            pending_contracts=pending,
        )

    def get_all_status(self) -> dict[Department, DepartmentStatus]:
        """Get status for all departments."""
        return {dept: self.get_department_status(dept) for dept in self.DEPARTMENTS}

    def get_enterprise_health(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get overall enterprise health metrics."""
        statuses = self.get_all_status()

        total_prana = sum(s.prana_available for s in statuses.values())
        max_prana = len(self.DEPARTMENTS) * self.PRANA_PER_DEPARTMENT

        # Calculate health by category
        health_by_category = {
            "strategic": {
                "departments": [Department.STRATEGY.value],
                "avg_health": statuses[Department.STRATEGY].health_score,
            },
            "innovation": {
                "departments": [Department.PRODUCT_INNOVATION.value],
                "avg_health": statuses[Department.PRODUCT_INNOVATION].health_score,
            },
            "operations": {
                "departments": [
                    Department.OPERATIONS_SUPPLY_CHAIN.value,
                    Department.FINANCE.value,
                    Department.HR.value,
                    Department.IT_SECURITY.value,
                ],
                "avg_health": sum(
                    statuses[d].health_score
                    for d in [
                        Department.OPERATIONS_SUPPLY_CHAIN,
                        Department.FINANCE,
                        Department.HR,
                        Department.IT_SECURITY,
                    ]
                )
                / 4,
            },
            "growth": {
                "departments": [
                    Department.SALES_MARKETING.value,
                    Department.CUSTOMER_EXPERIENCE.value,
                ],
                "avg_health": sum(
                    statuses[d].health_score
                    for d in [
                        Department.SALES_MARKETING,
                        Department.CUSTOMER_EXPERIENCE,
                    ]
                )
                / 2,
            },
            "governance": {
                "departments": [
                    Department.LEGAL_COMPLIANCE.value,
                    Department.DATA_AI_GOVERNANCE.value,
                ],
                "avg_health": sum(
                    statuses[d].health_score
                    for d in [
                        Department.LEGAL_COMPLIANCE,
                        Department.DATA_AI_GOVERNANCE,
                    ]
                )
                / 2,
            },
        }

        return {
            "tenant_id": self.tenant_id,
            "departments_online": sum(1 for s in statuses.values() if s.is_online),
            "total_departments": len(self.DEPARTMENTS),
            "total_prana_available": total_prana,
            "total_prana_capacity": max_prana,
            "prana_utilization": 1 - (total_prana / max_prana),
            "pending_contracts": sum(s.pending_contracts for s in statuses.values()),
            "active_contracts": self._metrics.active_contracts,
            "health_by_department": {
                dept.value: {
                    "online": s.is_online,
                    "prana_available": s.prana_available,
                    "health_score": s.health_score,
                    "agent_count": s.agent_count,
                }
                for dept, s in statuses.items()
            },
            "health_by_category": health_by_category,
        }

    def get_department_agents(self, department: Department) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """
        Get the list of agents for a specific department.

        Returns list of agent definitions with their technology type.
        """
        agents_by_dept = {
            Department.STRATEGY: [
                {
                    "name": "market_intelligence",
                    "technology": "ML",
                    "type": "MarketIntelligenceAgent",
                },
                {"name": "ma_analyst", "technology": "LLM", "type": "MaAgent"},
                {
                    "name": "partnerships",
                    "technology": "LLM",
                    "type": "PartnershipsAgent",
                },
            ],
            Department.PRODUCT_INNOVATION: [
                {
                    "name": "market_gap_analysis",
                    "technology": "ML",
                    "type": "MarketGapAnalysisAgent",
                },
                {
                    "name": "technical_architect",
                    "technology": "LLM",
                    "type": "TechnicalArchitectAgent",
                },
                {
                    "name": "ux_ui_designer",
                    "technology": "Vision",
                    "type": "UxUiDesignSynthesizer",
                },
                {
                    "name": "qa_bug_detection",
                    "technology": "ML",
                    "type": "QaBugDetectionAgent",
                },
            ],
            Department.OPERATIONS_SUPPLY_CHAIN: [
                {
                    "name": "process_mining",
                    "technology": "ML",
                    "type": "ProcessMiningAgent",
                },
                {
                    "name": "inventory_forecasting",
                    "technology": "ML",
                    "type": "InventoryForecaster",
                },
                {
                    "name": "vendor_negotiation",
                    "technology": "LLM",
                    "type": "VendorNegotiationAgent",
                },
                {
                    "name": "logistics_optimization",
                    "technology": "ML",
                    "type": "LogisticsOptimizationAgent",
                },
            ],
            Department.SALES_MARKETING: [
                {"name": "sdr", "technology": "ML", "type": "SdrAgent"},
                {
                    "name": "dynamic_pricing",
                    "technology": "ML",
                    "type": "DynamicPricingAgent",
                },
                {
                    "name": "multichannel_content",
                    "technology": "LLM",
                    "type": "MultichannelContentAgent",
                },
                {"name": "lead_gen", "technology": "ML", "type": "LeadGenAgent"},
                {
                    "name": "content_personalization",
                    "technology": "ML",
                    "type": "ContentPersonalizationAgent",
                },
                {"name": "growth_lead", "technology": "Human", "type": "GrowthLead"},
            ],
            Department.FINANCE: [
                {
                    "name": "accounts_receivable_payable",
                    "technology": "ML",
                    "type": "AccountsReceivablePayableAgent",
                },
                {
                    "name": "tax_compliance",
                    "technology": "LLM",
                    "type": "TaxComplianceAgent",
                },
                {
                    "name": "investment_allocation",
                    "technology": "ML",
                    "type": "InvestmentAllocationAgent",
                },
                {"name": "forecasting", "technology": "ML", "type": "ForecastingAgent"},
                {
                    "name": "audit_compliance",
                    "technology": "ML",
                    "type": "AuditComplianceAgent",
                },
            ],
            Department.HR: [
                {
                    "name": "talent_acquisition",
                    "technology": "ML",
                    "type": "TalentAcquisitionAgent",
                },
                {
                    "name": "employee_sentiment",
                    "technology": "ML",
                    "type": "EmployeeSentimentAgent",
                },
                {
                    "name": "skills_gap_training",
                    "technology": "LLM",
                    "type": "SkillsGapTrainingAgent",
                },
                {
                    "name": "internal_mobility",
                    "technology": "ML",
                    "type": "InternalMobilityAgent",
                },
            ],
            Department.IT_SECURITY: [
                {
                    "name": "cloud_orchestration",
                    "technology": "ML",
                    "type": "CloudOrchestrationAgent",
                },
                {
                    "name": "threat_hunter",
                    "technology": "ML",
                    "type": "ThreatHunterAgent",
                },
                {"name": "auto_devops", "technology": "LLM", "type": "AutoDevOpsAgent"},
                {
                    "name": "data_integrity",
                    "technology": "ML",
                    "type": "DataIntegrityAgent",
                },
            ],
            Department.LEGAL_COMPLIANCE: [
                {
                    "name": "gdpr_privacy_guard",
                    "technology": "LLM",
                    "type": "GDPRPrivacyGuardAgent",
                },
                {
                    "name": "contract_lifecycle",
                    "technology": "LLM",
                    "type": "ContractLifecycleAgent",
                },
                {
                    "name": "regulatory_tracking",
                    "technology": "ML",
                    "type": "RegulatoryTrackingAgent",
                },
                {
                    "name": "contract_analysis",
                    "technology": "LLM",
                    "type": "ContractAnalysisAgent",
                },
            ],
            Department.CUSTOMER_EXPERIENCE: [
                {
                    "name": "sentiment_support",
                    "technology": "Hybrid",
                    "type": "SentimentSupportAgent",
                },
                {
                    "name": "customer_success",
                    "technology": "LLM",
                    "type": "CustomerSuccessAgent",
                },
                {
                    "name": "community_management",
                    "technology": "LLM",
                    "type": "CommunityManagementAgent",
                },
            ],
            Department.DATA_AI_GOVERNANCE: [
                {
                    "name": "data_integrity_ethics",
                    "technology": "ML",
                    "type": "DataIntegrityEthicsAgent",
                },
                {
                    "name": "data_science",
                    "technology": "ML",
                    "type": "DataScienceAgent",
                },
                {
                    "name": "ai_ethics_auditor",
                    "technology": "LLM",
                    "type": "AIEthicsAuditorAgent",
                },
            ],
        }
        return agents_by_dept.get(department, [])

    def get_all_agents(self) -> dict[Department, list[dict[str, Any]]]:  # TODO(TYPE): replace Any with concrete type
        """Get all agents across all departments."""
        return {dept: self.get_department_agents(dept) for dept in self.DEPARTMENTS}

    async def shutdown(self) -> None:
        """Graceful shutdown of enterprise orchestrator."""
        # Shutdown all department orchestrators
        for dept, orchestrator in self._departments.items():
            if orchestrator:
                await orchestrator.shutdown()

        self._initialized = False
        logger.info(f"EnterpriseOrchestrator tenant={self.tenant_id} shutdown")
