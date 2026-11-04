"""
DeterministicRouter - Rule-based routing without LLM.

Sprint B+ Requirement: Hard-coded routing decisions based on:
- Task type patterns (regex/keyword matching)
- Department capabilities (static mapping)
- Prana budget availability

All 10 Enterprise Departments supported:
- Strategy & Business
- Product & Innovation (R&D)
- Operations & Supply Chain
- Sales & Marketing
- Finance & Treasury
- HR & Culture
- IT, Infra & Cyber Security
- Legal, Risk & Compliance
- Customer Experience (CX) & Support
- Data & AI Governance
"""

import re
from dataclasses import dataclass
from enum import Enum

from src.core.als.enterprise.departments.department_orchestrator import Department


class TaskCategory(Enum):
    """High-level task categories for routing."""

    STRATEGY = "strategy"
    PRODUCT_INNOVATION = "product_innovation"
    OPERATIONS = "operations"
    SALES_MARKETING = "sales_marketing"
    FINANCIAL = "financial"
    HUMAN_RESOURCES = "human_resources"
    SECURITY = "security"
    LEGAL_COMPLIANCE = "legal_compliance"
    CUSTOMER_EXPERIENCE = "customer_experience"
    DATA_AI_GOVERNANCE = "data_ai_governance"
    GENERAL = "general"


@dataclass
class RoutingRule:
    """A deterministic routing rule."""

    pattern: str  # Regex pattern to match task type/description
    target_department: Department
    min_prana_required: int = 50
    priority: int = 1  # Higher = checked first


class DeterministicRouter:
    """
    Deterministic task router - NO LLM INVOLVED.

    Uses hard-coded rules and pattern matching to route tasks
    to the appropriate department.

    All 10 Enterprise Departments supported with specific routing patterns.

    NON-NEGOTIABLE:
    - No LLM calls for routing decisions
    - O(1) lookup time for known patterns
    - Deterministic: same input -> same output
    """

    # Pre-defined routing rules (hard-coded, no config files)
    # Order matters: higher priority = checked first
    _ROUTING_RULES: list[RoutingRule] = [
        # === STRATEGY & BUSINESS (priority 25 - highest for strategic decisions) ===
        RoutingRule(
            r"(?i)(strategy|strategic|business.development|market.intelligence|m\\&a|merger|acquisition|partnership|alliance|joint.venture|market.entry|expansion|competitive.analysis|swot|pestel|porter.five.forces|blue.ocean|bcg.matrix|ansoff.matrix)",
            Department.STRATEGY,
            100,
            25,
        ),
        RoutingRule(
            r"(?i)(corporate.strategy|business.model|value.proposition|market.sizing|tam.sam.som|go.to.market|gtm)",
            Department.STRATEGY,
            100,
            25,
        ),
        # === IT SECURITY patterns (priority 22 - security before other ops) ===
        RoutingRule(
            r"(?i)(soc2|gdpr|iso27001|nist|cybersecurity|vulnerability|threat|breach|malware|phishing|pentest|firewall|intrusion|siem|penetration.testing|zero.trust|ransomware|apt|advanced.persistent)",
            Department.IT_SECURITY,
            75,
            22,
        ),
        RoutingRule(
            r"(?i)(access.control|authenticat|authoriz|encrypt|cryptograph|certificat|ssl|tls|pki|identity.management|iam|mfa|2fa|sso)",
            Department.IT_SECURITY,
            100,
            22,
        ),
        RoutingRule(
            r"(?i)(security.(audit|assessment|incident|monitoring)|network.security|cloud.security|devsecops)",
            Department.IT_SECURITY,
            100,
            22,
        ),
        RoutingRule(
            r"(?i)\b(compliance.audit|security.compliance|data.protection|privacy.impact)\b",
            Department.IT_SECURITY,
            100,
            22,
        ),
        RoutingRule(
            r"(?i)(threat.hunter|threat.intelligence|indicator.of.compromise|ioc|attack.mitre|mitre.att\\&ck)",
            Department.IT_SECURITY,
            100,
            22,
        ),
        # === LEGAL & COMPLIANCE (priority 21) ===
        RoutingRule(
            r"(?i)(contract|legal|compliance|regulatory|gdpr|ccpa|privacy|terms.of.service|sla|nda|intellectual.property|ip|patent|trademark|copyright|litigation|dispute|arbitration|mediation|governance|risk|audit)",
            Department.LEGAL_COMPLIANCE,
            75,
            21,
        ),
        RoutingRule(
            r"(?i)(contract.lifecycl|clause.analysis|contract.review|regulatory.tracking|compliance.monitoring|policy.management|legal.research)",
            Department.LEGAL_COMPLIANCE,
            100,
            21,
        ),
        # === DATA & AI GOVERNANCE (priority 20) ===
        RoutingRule(
            r"(?i)(data.governance|data.quality|data.lineage|data.catalog|master.data|mdm|data.ethics|ai.ethics|ai.governance|algorithm.audit|bias.detection|fairness|explainability|interpretability|model.governance|mlops)",
            Department.DATA_AI_GOVERNANCE,
            75,
            20,
        ),
        RoutingRule(
            r"(?i)(data.science|machine.learning|ml.model|training.data|feature.engineering|model.training|model.evaluation|model.deployment|model.monitoring|drift.detection)",
            Department.DATA_AI_GOVERNANCE,
            100,
            20,
        ),
        # === PRODUCT & INNOVATION (R&D) (priority 18) ===
        RoutingRule(
            r"(?i)(product|innovation|r\\&d|research|development|market.gap|competitive.analysis|product.strategy|roadmap|feature|requirement|user.story|mvp|prototype|design.sprint|ux.research|usability|a.b.test|experiment)",
            Department.PRODUCT_INNOVATION,
            75,
            18,
        ),
        RoutingRule(
            r"(?i)(technical.architecture|system.design|api.design|database.schema|microservice|domain.driven|ddd|event.driven|serverless|cloud.native)",
            Department.PRODUCT_INNOVATION,
            100,
            18,
        ),
        RoutingRule(
            r"(?i)(qa|quality.assurance|testing|test.automation|bug|defect|regression|performance.test|load.test|security.test|penetration.test|code.review)",
            Department.PRODUCT_INNOVATION,
            75,
            18,
        ),
        RoutingRule(
            r"(?i)(ux|ui|user.experience|user.interface|design.system|component.library|wireframe|mockup|prototype|figma|sketch|adobe.xd)",
            Department.PRODUCT_INNOVATION,
            75,
            18,
        ),
        # === OPERATIONS & SUPPLY CHAIN (priority 17) ===
        RoutingRule(
            r"(?i)(operations|supply.chain|logistics|inventory|warehouse|fulfillment|shipping|delivery|procurement|sourcing|purchasing|vendor|supplier|manufacturing|production|assembly|quality.control|six.sigma|lean|kaizen|process.mining|bpm|workflow)",
            Department.OPERATIONS_SUPPLY_CHAIN,
            75,
            17,
        ),
        RoutingRule(
            r"(?i)(demand.forecast|demand.planning|supply.planning|material.requirement|mrp|erp|scm|wms|tms|yms|aps|srm)",
            Department.OPERATIONS_SUPPLY_CHAIN,
            100,
            17,
        ),
        RoutingRule(
            r"(?i)(negotiation|vendor.negotiation|contract.negotiation|price.negotiation|rfp|rfq|rft|tender|bid|quote|procurement)",
            Department.OPERATIONS_SUPPLY_CHAIN,
            100,
            17,
        ),
        RoutingRule(
            r"(?i)(route.optimization|load.optimization|fleet.management|delivery.scheduling|last.mile|cross.docking|consolidation)",
            Department.OPERATIONS_SUPPLY_CHAIN,
            75,
            17,
        ),
        # === SALES & MARKETING (priority 16) ===
        RoutingRule(
            r"(?i)(sales|marketing|lead|prospect|pipeline|crm|hubspot|salesforce|outreach|cold.call|email.campaign|nurture|funnel|conversion|cac|ltv|churn|retention|upsell|cross.sell|renewal)",
            Department.SALES_MARKETING,
            75,
            16,
        ),
        RoutingRule(
            r"(?i)(pricing|dynamic.pricing|price.optimization|promotion|discount|markdown|competitive.pricing|value.based.pricing|cost.plus|freemium)",
            Department.SALES_MARKETING,
            100,
            16,
        ),
        RoutingRule(
            r"(?i)(content|content.marketing|content.strategy|blog|whitepaper|ebook|webinar|podcast|video|youtube|linkedin|twitter|facebook|instagram|tiktok|social.media|seo|sem|ppc|advertising|ad.campaign|google.ads|facebook.ads|programmatic)",
            Department.SALES_MARKETING,
            75,
            16,
        ),
        RoutingRule(
            r"(?i)(personalization|recommendation|segmentation|persona|customer.journey|touchpoint|omnichannel|multichannel|cross.channel)",
            Department.SALES_MARKETING,
            75,
            16,
        ),
        RoutingRule(
            r"(?i)(sdr|sales.development|business.development|bdr|account.executive|ae|account.manager|am|customer.success|csm|growth|growth.hacking|growth.marketing)",
            Department.SALES_MARKETING,
            75,
            16,
        ),
        # === CUSTOMER EXPERIENCE (CX) (priority 15) ===
        RoutingRule(
            r"(?i)(customer.support|customer.service|helpdesk|ticketing|incident|troubleshooting|technical.support|customer.care|call.center|contact.center|live.chat|chatbot|virtual.assistant)",
            Department.CUSTOMER_EXPERIENCE,
            75,
            15,
        ),
        RoutingRule(
            r"(?i)(sentiment|nps|net.promoter|csat|customer.satisfaction|customer.effort.score|ces|voice.of.customer|voc|feedback|review|rating|testimonial|survey|poll)",
            Department.CUSTOMER_EXPERIENCE,
            75,
            15,
        ),
        RoutingRule(
            r"(?i)(customer.success|onboarding|training|adoption|health.score|renewal|expansion|advocacy|reference|case.study|community|forum|user.group)",
            Department.CUSTOMER_EXPERIENCE,
            75,
            15,
        ),
        RoutingRule(
            r"(?i)(escalation|complaint|dispute|refund|return|warranty|service.recovery|complaint.resolution)",
            Department.CUSTOMER_EXPERIENCE,
            100,
            15,
        ),
        # === FINANCE & TREASURY (priority 14) ===
        RoutingRule(
            r"(?i)(budget|invoice|payment|revenue|expens|audit|tax|financial|forecast|treasury|accounting|roi|cashflow|profit|loss|p\\&l|balance.sheet|income.statement|cash.flow.statement)",
            Department.FINANCE,
            50,
            14,
        ),
        RoutingRule(
            r"(?i)(account.receivable|ar|account.payable|ap|billing|collection|dso|dpo|working.capital|liquidity|cash.management|fx|foreign.exchange|hedging|investment|portfolio|asset.management)",
            Department.FINANCE,
            75,
            14,
        ),
        RoutingRule(
            r"(?i)(tax|vat|gst|sales.tax|income.tax|corporate.tax|tax.compliance|transfer.pricing|tax.optimization|r\\&d.tax.credit)",
            Department.FINANCE,
            100,
            14,
        ),
        RoutingRule(
            r"(?i)(financial.planning|fp\\&a|financial.analysis|variance.analysis|financial.modeling|valuation|dcf|npv|irr|wacc|capm|budget.varianc)",
            Department.FINANCE,
            75,
            14,
        ),
        RoutingRule(
            r"(?i)(audit|internal.audit|external.audit|financial.audit|compliance.audit|operational.audit|sox|gaap|ifrs|financial.reporting|sec.filing|10.k|10.q)",
            Department.FINANCE,
            100,
            14,
        ),
        RoutingRule(
            r"(?i)(capital.allocation|capex|opex|capital.budgeting|investment.decision|project.finance|venture.capital|private.equity|debt.financing|equity.financing|ipo)",
            Department.FINANCE,
            100,
            14,
        ),
        # === HR & CULTURE (priority 13) ===
        RoutingRule(
            r"(?i)(hiring|hire|onboard|offboard|payroll|benefit|compensat|salary|performance.review|training|skill|certification|employee|culture|engagement|retention|turnover|attrition)",
            Department.HR,
            50,
            13,
        ),
        RoutingRule(
            r"(?i)(talent.acquisition|recruiting|sourcing|interview|assessment|background.check|offer.letter|employment.contract|new.hire.orientation)",
            Department.HR,
            75,
            13,
        ),
        RoutingRule(
            r"(?i)(employee.sentiment|engagement.survey|pulse.survey|stay.interview|exit.interview|e-nps|employee.net.promoter|culture.assessment|values.alignment)",
            Department.HR,
            75,
            13,
        ),
        RoutingRule(
            r"(?i)(skill.gap|training.need|learning.path|lms|learning.management|competency|capability|succession.planning|career.path|internal.mobility|promotion)",
            Department.HR,
            75,
            13,
        ),
        RoutingRule(
            r"(?i)(payroll|payroll.processing|timesheet|overtime|leave.management|pto|vacation|sick.leave|benefits.admin|health.insurance|retirement|401k|pension)",
            Department.HR,
            75,
            13,
        ),
        RoutingRule(r"(?i)\bhr\\b", Department.HR, 50, 13),
        # === Fallback (priority 1) ===
        RoutingRule(r".*", Department.OPERATIONS, 25, 1),
    ]

    # Department capabilities (what each department can handle)
    _DEPT_CAPABILITIES: dict[Department, set[str]] = {
        # === STRATEGY & BUSINESS ===
        Department.STRATEGY: {
            "market_intelligence",
            "competitive_analysis",
            "business_strategy",
            "mergers_acquisitions",
            "partnerships",
            "market_entry",
            "expansion_planning",
            "strategic_planning",
            "corporate_development",
            "business_model",
            "value_proposition",
            "market_sizing",
            "go_to_market",
            "swot_analysis",
            "pestel_analysis",
            "porter_analysis",
            "bcg_matrix",
            "ansoff_matrix",
            "blue_ocean_strategy",
        },
        # === PRODUCT & INNOVATION (R&D) ===
        Department.PRODUCT_INNOVATION: {
            "market_gap_analysis",
            "product_strategy",
            "technical_architecture",
            "system_design",
            "ux_ui_design",
            "qa_testing",
            "bug_detection",
            "product_roadmap",
            "feature_prioritization",
            "mvp_definition",
            "prototype_development",
            "user_research",
            "usability_testing",
            "ab_testing",
            "experimentation",
            "api_design",
            "database_design",
            "microservices_architecture",
            "cloud_native_design",
            "code_review",
            "test_automation",
            "performance_testing",
            "security_testing",
            "design_systems",
            "wireframing",
            "mockups",
        },
        # === OPERATIONS & SUPPLY CHAIN ===
        Department.OPERATIONS_SUPPLY_CHAIN: {
            "process_mining",
            "workflow_optimization",
            "inventory_forecasting",
            "demand_planning",
            "vendor_negotiation",
            "logistics_optimization",
            "supply_chain_management",
            "warehouse_management",
            "procurement",
            "sourcing",
            "production_planning",
            "manufacturing",
            "quality_control",
            "lean_manufacturing",
            "six_sigma",
            "kaizen",
            "continuous_improvement",
            "fleet_management",
            "route_optimization",
            "load_optimization",
            "supplier_relationship_management",
            "rfp_management",
            "tender_management",
        },
        # === SALES & MARKETING ===
        Department.SALES_MARKETING: {
            "sdr_outreach",
            "lead_generation",
            "lead_qualification",
            "pipeline_management",
            "dynamic_pricing",
            "price_optimization",
            "promotion_planning",
            "content_creation",
            "multichannel_content",
            "content_strategy",
            "social_media_management",
            "seo",
            "sem",
            "ppc_advertising",
            "email_marketing",
            "marketing_automation",
            "customer_segmentation",
            "personalization",
            "recommendation_systems",
            "customer_journey_mapping",
            "conversion_optimization",
            "growth_hacking",
            "account_based_marketing",
            "event_marketing",
            "webinar_management",
            "pr_communications",
        },
        # === FINANCE & TREASURY ===
        Department.FINANCE: {
            "budget_analysis",
            "financial_forecasting",
            "audit",
            "tax_compliance",
            "invoice_processing",
            "payment_authorization",
            "revenue_reporting",
            "expense_management",
            "cashflow_optimization",
            "roi_analysis",
            "accounts_receivable",
            "accounts_payable",
            "billing",
            "collections",
            "treasury_management",
            "cash_management",
            "fx_management",
            "hedging",
            "investment_analysis",
            "portfolio_management",
            "capital_allocation",
            "financial_planning",
            "fp\\&a",
            "variance_analysis",
            "financial_modeling",
            "valuation",
            "due_diligence",
            "financial_reporting",
            "sox_compliance",
            "transfer_pricing",
            "tax_optimization",
            "capital_budgeting",
        },
        # === HR & CULTURE ===
        Department.HR: {
            "hiring",
            "onboarding",
            "offboarding",
            "payroll_processing",
            "benefits_administration",
            "performance_reviews",
            "training_coordination",
            "skill_assessment",
            "culture_analysis",
            "retention_analysis",
            "talent_acquisition",
            "recruiting",
            "interviewing",
            "offer_management",
            "employee_sentiment",
            "engagement_surveys",
            "stay_interviews",
            "exit_interviews",
            "skill_gap_analysis",
            "learning_paths",
            "succession_planning",
            "internal_mobility",
            "career_development",
            "compensation_analysis",
            "leave_management",
            "hr_compliance",
            "diversity_inclusion",
        },
        # === IT, INFRA & CYBER SECURITY ===
        Department.IT_SECURITY: {
            "vulnerability_assessment",
            "threat_detection",
            "incident_response",
            "access_management",
            "compliance_auditing",
            "security_monitoring",
            "penetration_testing",
            "log_analysis",
            "encryption_management",
            "threat_hunting",
            "threat_intelligence",
            "ioc_analysis",
            "cloud_orchestration",
            "devops",
            "devsecops",
            "infrastructure_as_code",
            "identity_management",
            "iam",
            "mfa",
            "sso",
            "pki",
            "network_security",
            "firewall_management",
            "siem",
            "soc",
            "gdpr_compliance",
            "privacy_impact_assessment",
            "data_protection",
            "disaster_recovery",
            "backup_management",
            "business_continuity",
        },
        # === LEGAL, RISK & COMPLIANCE ===
        Department.LEGAL_COMPLIANCE: {
            "contract_lifecycle",
            "contract_drafting",
            "contract_review",
            "clause_analysis",
            "contract_negotiation",
            "contract_management",
            "gdpr_compliance",
            "privacy_guard",
            "data_protection",
            "ccpa_compliance",
            "regulatory_tracking",
            "compliance_monitoring",
            "policy_management",
            "legal_research",
            "precedent_analysis",
            "case_law_research",
            "ip_management",
            "patent_filing",
            "trademark_registration",
            "litigation_support",
            "dispute_resolution",
            "arbitration",
            "risk_assessment",
            "risk_mitigation",
            "compliance_training",
        },
        # === CUSTOMER EXPERIENCE (CX) & SUPPORT ===
        Department.CUSTOMER_EXPERIENCE: {
            "sentiment_analysis",
            "support_ticket_management",
            "helpdesk",
            "technical_support",
            "troubleshooting",
            "issue_resolution",
            "customer_success",
            "customer_onboarding",
            "product_adoption",
            "health_scoring",
            "renewal_management",
            "expansion_upsell",
            "community_management",
            "forum_moderation",
            "user_groups",
            "nps_surveys",
            "csat_surveys",
            "feedback_collection",
            "escalation_management",
            "complaint_resolution",
            "service_recovery",
            "knowledge_base",
            "faq_management",
            "self_service_portal",
        },
        # === DATA & AI GOVERNANCE ===
        Department.DATA_AI_GOVERNANCE: {
            "data_quality",
            "data_lineage",
            "data_catalog",
            "master_data_management",
            "data_governance",
            "data_stewardship",
            "data_policy",
            "ai_ethics",
            "algorithm_auditing",
            "bias_detection",
            "fairness_assessment",
            "explainability",
            "interpretability",
            "model_governance",
            "mlops",
            "data_science",
            "machine_learning",
            "model_training",
            "model_evaluation",
            "feature_engineering",
            "model_deployment",
            "model_monitoring",
            "drift_detection",
            "model_retraining",
            "a_b_testing_ml",
        },
        # === OPERATIONS (fallback) ===
        Department.OPERATIONS: {"general_task", "coordination", "escalation"},
    }

    def __init__(self) -> None:
        # Compile regex patterns for performance
        self._compiled_rules = [
            (re.compile(rule.pattern), rule)
            for rule in sorted(self._ROUTING_RULES, key=lambda r: -r.priority)
        ]

    def route(
        self,
        task_type: str,
        task_description: str = "",
        available_prana: dict[Department, int] | None = None,
    ) -> Department | None:
        """
        Determine target department for a task.

        Args:
            task_type: Type of task (e.g., "invoice_processing")
            task_description: Optional description for pattern matching
            available_prana: Dict[str, Any] of department -> available prana budget  # TODO(TYPE): replace Any with concrete type

        Returns:
            Target Department or None if no route found

        Complexity: O(n) where n = number of rules (small constant)
        """
        available_prana = available_prana or {}
        search_text = f"{task_type} {task_description}".lower()

        for compiled_pattern, rule in self._compiled_rules:
            if compiled_pattern.search(search_text):
                # Check if department has budget
                dept_budget = available_prana.get(rule.target_department, float("inf"))
                if dept_budget >= rule.min_prana_required:
                    return rule.target_department

                # Department matched but no budget - continue to next rule
                continue

        return None

    def can_handle(self, department: Department, task_type: str) -> bool:
        """Check if department can handle specific task type."""
        capabilities = self._DEPT_CAPABILITIES.get(department, set())
        normalized_task = task_type.lower().replace(" ", "_").replace("-", "_")
        return normalized_task in capabilities

    def get_capabilities(self, department: Department) -> set[str]:
        """Get all capabilities for a department."""
        return self._DEPT_CAPABILITIES.get(department, set()).copy()

    def get_all_departments(self) -> list[Department]:
        """Get list of all routable departments (all 10 enterprise departments)."""
        return [
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


# Convenience function for direct routing
def route_task(
    task_type: str,
    task_description: str = "",
    available_prana: dict[Department, int] | None = None,
) -> Department | None:
    """
    Static routing function - stateless, deterministic.

    Usage:
        dept = route_task("invoice_processing", "Process vendor invoice")
        # Returns: Department.FINANCE
    """
    router = DeterministicRouter()
    return router.route(task_type, task_description, available_prana)
