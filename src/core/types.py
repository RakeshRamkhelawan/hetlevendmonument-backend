"""
Core Types - SINGLE SOURCE OF TRUTH
All type definitions consolidated here. Import from core.types, NEVER redefine!

CRITICAL: If you need a new type, ADD IT HERE and import from core.types
"""

from enum import Enum

# ========================================
# WORKFLOW & TRIGGER TYPES
# ========================================


class TriggerType(str, Enum):
    """Workflow trigger types - Consolidated from multiple sources"""

    MANUAL = "manual"
    SCHEDULED = "scheduled"
    AUTO = "auto"
    EVENT_DRIVEN = "event_driven"
    INTELLIGENT = "intelligent"
    USER_INITIATED = "user_initiated"
    EMERGENCY = "emergency"


class WorkflowState(str, Enum):
    """Workflow execution state"""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


# ========================================
# TASK & EXECUTION TYPES
# ========================================


class TaskStatus(str, Enum):
    """Task lifecycle status"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    APPROVAL_REQUIRED = "approval_required"


class TaskPriority(int, Enum):
    """Task priority levels"""

    LOW = 1
    MEDIUM = 3
    HIGH = 5
    CRITICAL = 9


class ExecutionStatusContract(str, Enum):
    """ADR-036 D7-001 -- minimaal statuscontract voor ExecutionResult.status.

    Vijf gesloten waarden, geen checkpoint-tabel (dat is Fase 4, buiten deze sprint). Gevuld
    vanuit `specialist_base.py`, `packs.py` EN `base_agent.py` -- de bronnen hieronder per
    waarde bestrijken alle drie:
      - KLAAR: volledige, succesvolle afronding.
      - GEDEELTELIJK: een deel van de stappen slaagde binnen de opgegeven limiet
        (`specialist_base.py`: `max_steps`-overschrijding of gemengd tool-succes/-falen).
      - MEER_BUDGET_NODIG: een budgetgrens werd bereikt -- Prana-tekort, skill-timeout,
        `max_llm_calls` (`specialist_base.py::_run_within_budget()`), of een bereikte
        gelijktijdige-taken-limiet (`base_agent.py::process_task()`, "at capacity").
      - GEBLOKKEERD: een governance-beslissing hield de actie tegen -- de D5-denylist, een
        ontbrekende initiator, of een niet-APPROVED Council-verdict (`specialist_base.py`),
        of een `GovernanceContract`-blokkade resp. een GDPR-art.-21-profileringsweigering
        (`base_agent.py::process_task()`).
      - MISLUKT: een onverwachte fout, of de governance-poort zelf was onbereikbaar
        (`specialist_base.py`); een geweigerde prompt-injectie, een mislukte taakvalidatie,
        of een onverwachte exception in de buitenste `except`-afhandeling
        (`base_agent.py::process_task()`); of een pack-uitvoeringsfout -- SLA-timeout, een
        onbekende of ongewired agent, een pack dat niet in de catalogus staat, of een
        gegooide exception tijdens de skill-uitvoering (`packs.py::run_pack_by_id()`/
        `_run_single_step()`/`_execute_step()`).

    **Verduidelijking na blinde reviewronde 2 (2026-08-21)**: een eerdere versie van deze
    docstring beweerde "de bronnen hieronder bestrijken alle drie bestanden" maar noemde
    `packs.py` daarna nergens meer -- exact het soort ongeverifieerde volledigheidsclaim die
    dit statuscontract zelf moet voorkomen. Alle zes `ExecutionResult`-constructies in
    `packs.py` staan nu met naam in de MISLUKT-opsomming hierboven.
    """

    KLAAR = "klaar"
    GEDEELTELIJK = "gedeeltelijk"
    MEER_BUDGET_NODIG = "meer_budget_nodig"
    GEBLOKKEERD = "geblokkeerd"
    MISLUKT = "mislukt"


# ========================================
# AGENT TYPES
# ========================================


class AgentType(str, Enum):
    """Agent classification types - Consolidated from multiple sources"""

    # Core agent types (from interfaces.py)
    CVA = "cva"
    ORCHESTRATOR = "orchestrator"
    ETHICS = "ethics"
    SPECIALIST = "specialist"
    SANDBOX = "sandbox"
    AUTONOMOUS = "autonomous"

    # Domain agent types (from domains/agents/models.py)
    CORE = "core"
    SPECIALIZED = "specialized"
    ANALYTICAL = "analytical"
    CREATIVE = "creative"
    TECHNICAL = "technical"

    # Subagent types (from agents/subagent_loader.py, core/subagents/agent_factory.py)
    COORDINATOR = "coordinator"
    ANALYZER = "analyzer"
    EXECUTOR = "executor"
    MONITOR = "monitor"
    BRIDGE = "bridge"
    GENERIC = "generic"
    GENERAL = "generic"
    DATA_ANALYSIS = "data_analysis"
    SYSTEM_MONITOR = "system_monitor"
    CODE_REVIEWER = "code_reviewer"
    DEPLOYMENT_SPECIALIST = "deployment_specialist"
    SECURITY_AUDITOR = "security_auditor"
    PERFORMANCE_OPTIMIZER = "performance_optimizer"
    CODE_EXECUTION = "code_execution"
    KNOWLEDGE_RETRIEVAL = "knowledge_retrieval"
    REPORTING = "reporting"
    PERFORMANCE_ANALYSIS = "performance_analysis"
    WORKFLOW_ORCHESTRATION = "workflow_orchestration"
    SECURITY_ANALYSIS = "security_analysis"

    # Generated specialist agent types
    AI_ENGINEER = "ai_engineer"
    API_DOCUMENTER = "api_documenter"
    ARCHITECT_REVIEW = "architect_review"
    BACKEND_ARCHITECT = "backend_architect"
    BUSINESS_ANALYST = "business_analyst"
    CLOUD_ARCHITECT = "cloud_architect"
    CONTENT_MARKETER = "content_marketer"
    CONTEXT_MANAGER = "context_manager"
    CPP_PRO = "cpp_pro"
    CSHARP_PRO = "csharp_pro"
    CUSTOMER_SUPPORT = "customer_support"
    C_PRO = "c_pro"
    DATABASE_ADMIN = "database_admin"
    DATABASE_OPTIMIZER = "database_optimizer"
    DATA_ENGINEER = "data_engineer"
    DATA_SCIENTIST = "data_scientist"
    DJANGO_PRO = "django_pro"
    DOCS_ARCHITECT = "docs_architect"
    DX_OPTIMIZER = "dx_optimizer"
    ELIXIR_PRO = "elixir_pro"
    ERROR_DETECTIVE = "error_detective"
    FASTAPI_PRO = "fastapi_pro"
    FLUTTER_EXPERT = "flutter_expert"
    GOLANG_PRO = "golang_pro"
    GRAPHQL_ARCHITECT = "graphql_architect"
    HR_PRO = "hr_pro"
    HYBRID_CLOUD_ARCHITECT = "hybrid_cloud_architect"
    INCIDENT_RESPONDER = "incident_responder"
    IOS_DEVELOPER = "ios_developer"
    JAVASCRIPT_PRO = "javascript_pro"
    JAVA_PRO = "java_pro"
    KUBERNETES_ARCHITECT = "kubernetes_architect"
    LEGACY_MODERNIZER = "legacy_modernizer"
    LEGAL_ADVISOR = "legal_advisor"
    MERMAID_EXPERT = "mermaid_expert"
    MINECRAFT_BUKKIT_PRO = "minecraft_bukkit_pro"
    MLOPS_ENGINEER = "mlops_engineer"
    ML_ENGINEER = "ml_engineer"
    MOBILE_DEVELOPER = "mobile_developer"
    NETWORK_ENGINEER = "network_engineer"
    PAYMENT_INTEGRATION = "payment_integration"
    PERFORMANCE_ENGINEER = "performance_engineer"
    PHP_PRO = "php_pro"
    PROMPT_ENGINEER = "prompt_engineer"
    PYTHON_PRO = "python_pro"
    QUANT_ANALYST = "quant_analyst"
    REFERENCE_BUILDER = "reference_builder"
    RISK_MANAGER = "risk_manager"
    RUBY_PRO = "ruby_pro"
    RUST_PRO = "rust_pro"
    SALES_AUTOMATOR = "sales_automator"
    SCALA_PRO = "scala_pro"
    SEARCH_SPECIALIST = "search_specialist"
    SEO_AUTHORITY_BUILDER = "seo_authority_builder"
    SEO_CANNIBALIZATION_DETECTOR = "seo_cannibalization_detector"
    SEO_CONTENT_AUDITOR = "seo_content_auditor"
    SEO_CONTENT_PLANNER = "seo_content_planner"
    SEO_CONTENT_REFRESHER = "seo_content_refresher"
    SEO_CONTENT_WRITER = "seo_content_writer"
    SEO_KEYWORD_STRATEGIST = "seo_keyword_strategist"
    SEO_META_OPTIMIZER = "seo_meta_optimizer"
    SEO_SNIPPET_HUNTER = "seo_snippet_hunter"
    SEO_STRUCTURE_ARCHITECT = "seo_structure_architect"
    SQL_PRO = "sql_pro"
    TERRAFORM_SPECIALIST = "terraform_specialist"
    TEST_AUTOMATOR = "test_automator"
    TUTORIAL_ENGINEER = "tutorial_engineer"
    TYPESCRIPT_PRO = "typescript_pro"
    UI_UX_DESIGNER = "ui_ux_designer"
    UI_VISUAL_VALIDATOR = "ui_visual_validator"
    UNITY_DEVELOPER = "unity_developer"

    # ALS pilot agent types
    CODE = "code"
    RESEARCH = "research"

    # Quality & governance
    CRITIC = "critic"

    # Orchestration layer (added 2026-03-16)
    MASTER_ORCHESTRATOR = "master_orchestrator"
    AGENT_ROUTER = "agent_router"
    AGENT_HEALTH_MONITOR = "agent_health_monitor"


class AgentStatus(str, Enum):
    """Agent lifecycle status - Consolidated from domains/agents/models.py"""

    ACTIVE = "active"
    INACTIVE = "inactive"
    TRAINING = "training"
    ARCHIVED = "archived"


# ========================================
# ISOLATION & SANDBOX TYPES
# ========================================


class IsolationLevel(str, Enum):
    """Sandbox isolation levels"""

    MOCK = "mock"  # Week 1 - No isolation, direct execution
    PROCESS = "process"  # Week 2 - Process-level isolation
    CONTAINER = "container"  # Week 2 - Docker container isolation
    DOCKER = "docker"  # Week 2 - Docker daemon isolation
    VM = "vm"  # Week 3 - Full VM isolation


# ========================================
# SECURITY & AUDIT TYPES (OWASP A09)
# ========================================
# Canonical definitions live in src.core.security.types -- re-exported here for
# backward compatibility with existing imports from src.core.types.
# NOTE: import staat hier (niet bovenaan) om de sectiestructuur van dit bestand
# te bewaren; E402 is onderdrukt omdat dit een bewuste backward-compat re-export is.
from src.core.security.types import (  # noqa: E402
    AlertStatus as AlertStatus,
    SecurityEventType as SecurityEventType,
    ThreatLevel as ThreatLevel,
)


# ========================================
# PROCEDURE EXECUTION TYPES
# ========================================


class ProcedureExecutionStatus(str, Enum):
    """Procedure execution lifecycle status"""

    PENDING = "pending"
    PENDING_APPROVAL = "pending_approval"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    ROLLED_BACK = "rolled_back"
