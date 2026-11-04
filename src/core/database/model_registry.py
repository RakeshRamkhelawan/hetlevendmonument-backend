"""
Centralized Model Registry for SQLAlchemy Base.metadata registration.

This module is the SINGLE SOURCE OF TRUTH for importing all SQLAlchemy models.
It replaces the fragile 40+ import block in alembic/env.py with a resilient,
grouped import system that:

1. Logs import failures instead of crashing
2. Groups imports by domain for easier maintenance
3. Makes it trivial to add new models
4. Can be imported by both alembic env.py and test conftest.py

Usage:
    from src.core.database.model_registry import register_all_models
    failures = register_all_models()
    # failures is a list of (group_name, error_message) tuples
"""

import importlib
import logging
from typing import Any

logger = logging.getLogger(__name__)

# Each entry is (group_name, module_path, specific_names_or_None)
# If specific_names is None, we do `import module` (for star imports / side-effect registration)
# If specific_names is a list, we do `from module import name1, name2, ...`
_MODEL_GROUPS: list[
    tuple[str, str, list[Any] | None]  # TODO(TYPE): replace Any with concrete type
] = [  # TODO(TYPE): replace Any with concrete type
    # --- Core Database ---
    ("core.agents", "src.core.agents.models", None),
    (
        "core.agents.strategy",
        "src.core.agents.strategy_models",
        ["StrategicInsightModel", "StrategicObjectiveModel", "StrategyModel"],
    ),
    # --- ALS (Agent Learning System) ---
    ("als.synapse", "src.core.als.models.agent_synapse", ["AgentSynapse"]),
    (
        "als.collective_knowledge",
        "src.core.als.models.collective_knowledge",
        ["CollectiveKnowledge"],
    ),
    ("als.immune_antibody", "src.core.als.models.immune_antibody", ["ImmuneAntibody"]),
    (
        "als.immune_memory_cell",
        "src.core.als.models.immune_memory_cell",
        ["ImmuneMemoryCell"],
    ),
    ("als.organism_registry", "src.core.als.models.organism_registry", ["OrganismRegistry"]),
    ("als.signal_audit_log", "src.core.als.models.signal_audit_log", ["SignalAuditLog"]),
    ("als.signal_cooldown", "src.core.als.models.signal_cooldown", ["SignalCooldown"]),
    # --- Analytics ---
    ("core.analytics", "src.core.analytics.models", None),
    (
        "core.analytics.benchmarks",
        "src.core.database.models.analytics",
        ["PackUsageAggregate", "CompanyAnalyticsOptOut"],
    ),
    # --- Auth ---
    ("core.auth.lockout", "src.core.auth.models.account_lockout", None),
    ("core.auth.oauth2", "src.core.auth.oauth2_service", ["TokenBlacklist"]),
    ("core.auth.two_factor", "src.core.auth.two_factor_auth", ["TwoFactorAuth"]),
    # --- Autonomous Workflow ---
    (
        "core.autonomous_workflow",
        "src.core.autonomous_workflow.models",
        ["WorkflowExperience"],
    ),
    # --- Company Layer (Fase 2) ---
    ("core.company", "src.core.company.models", None),
    # --- Conversations ---
    ("core.conversations", "src.core.conversations.models", None),
    # --- Experiments (A/B Testing) ---
    (
        "core.experiments",
        "src.core.database.models.experiment",
        ["Experiment", "ExperimentAssignment", "ExperimentEvent", "ExperimentVariant"],
    ),
    # --- Feature Flags ---
    ("core.feature_flags", "src.core.feature_flags.models", None),
    # --- Foundation Portal (ADR-029) ---
    (
        "core.foundation",
        "src.core.models.foundation_content",
        [
            "FoundationContent",
            "ContentTag",
            "FoundationPortalSettings",
            "PortalUser",
            "MagicLinkToken",
            "TakedownRequest",
            "NewsletterSubscription",
            "EducationalAccess",
            "StudyCollection",
            "FoundationContactSubmission",
            "FoundationDonation",
        ],
    ),
    # --- Focus Builder ---
    (
        "core.focus_builder",
        "src.core.focus_builder.models",
        ["FocusBuilderFlow"],
    ),
    # --- GDPR ---
    ("core.gdpr", "src.core.database.gdpr_deletion", ["DeletionAudit"]),
    # --- Governance ---
    ("core.governance", "src.core.governance.models", None),
    # --- Knowledge ---
    ("core.knowledge", "src.core.knowledge.models", None),
    # --- Learning ---
    ("core.learning", "src.core.learning.models", None),
    (
        "core.learning.persistence",
        "src.core.learning.persistence_models",
        ["AdaptationRuleModel", "LearningInsightModel", "LearningPatternModel"],
    ),
    # --- Campaign Models (P2-006) ---
    (
        "core.campaigns",
        "src.core.models.campaign_models",
        [
            "ABTest",
            "CampaignAnalytics",
            "CampaignSegment",
            "EmailCampaign",
            "EmailTemplate",
            "UserEmailPreference",
        ],
    ),
    # --- Evaluation ---
    ("core.evaluation", "src.core.models.evaluation_models", None),
    # --- Gamification (2027 UX) ---
    (
        "core.gamification",
        "src.core.models.gamification_models",
        ["Badge", "PointTransaction", "UserBadge", "UserPoints"],
    ),
    # --- Integration ---
    ("core.integration", "src.core.models.integration_models", ["TenantIntegration"]),
    # --- AI Persona (2027 UX) ---
    (
        "core.persona",
        "src.core.models.persona_models",
        ["Persona", "UserPersonaPreference"],
    ),
    # --- RBAC ---
    ("core.rbac", "src.core.models.rbac_models", None),
    # --- HR-vaardigheden (ADR-036 OP-26): hangt aan roles/users uit RBAC hierboven ---
    (
        "core.hr_skills",
        "src.core.models.hr_skills_models",
        ["Skill", "RoleRequiredSkill", "EmployeeSkill"],
    ),
    # --- Tenant Custom Data ---
    ("core.tenant_custom_data", "src.core.models.tenant_custom_data", ["TenantCustomData"]),
    # --- Usage ---
    ("core.usage", "src.core.models.usage_models", None),
    # --- Mission ---
    ("core.mission", "src.core.models.mission_models", ["Mission"]),
    # --- Workflow ---
    ("core.workflow_models", "src.core.models.workflow_models", None),
    ("core.workflow_version", "src.core.models.workflow_version_models", None),
    # --- Procedures & Domain Packs ---
    (
        "core.procedures",
        "src.core.procedures.models",
        ["AIQualityEvent", "DomainPack", "ProcedureExecution", "ProcedureMetadata"],
    ),
    # --- Workflow Engine ---
    ("core.workflow", "src.core.workflow.models", None),
    # --- Domain: Agentic ---
    ("domains.agentic", "src.domains.agentic.models", None),
    # --- Domain: Tasks ---
    ("domains.tasks", "src.domains.tasks.models", ["Task"]),
    # --- Domain: Billing ---
    ("domains.billing", "src.domains.billing.models", ["BillingEvent"]),
    # --- Domain: Comments ---
    ("domains.comments", "src.domains.comments.models", ["Comment"]),
    # --- Domain: Documents ---
    ("domains.documents", "src.domains.documents.models", ["Document"]),
    # --- Domain: Flows ---
    ("domains.flows", "src.domains.flows.models", ["Flow", "PiecesCacheMetadata"]),
    # --- Domain: Notifications ---
    ("domains.notifications", "src.domains.notifications.models", ["Notification"]),
    # --- Domain: Tagging ---
    ("domains.tagging", "src.domains.tagging.models", ["EntityTag", "Tag"]),
    # --- Domain: Webhooks ---
    (
        "domains.webhooks",
        "src.domains.webhooks.models",
        ["WebhookDelivery", "WebhookEndpoint"],
    ),
    # --- Domain: Canvas ---
    (
        "domains.canvas",
        "src.domains.canvas.models",
        ["Canvas", "CanvasBlock", "CanvasConnection", "CanvasCollaborator", "CanvasOperation"],
    ),
    # --- ActivePieces Integration ---
    ("core.activepieces", "src.core.activepieces.models", None),
]


def register_all_models() -> list[tuple[str, str]]:
    """
    Import all SQLAlchemy model modules to register them with Base.metadata.

    Returns a list of (group_name, error_message) for any groups that failed
    to import. An empty list means all imports succeeded.
    """
    failures: list[tuple[str, str]] = []

    for group_name, module_path, specific_names in _MODEL_GROUPS:
        try:
            mod = importlib.import_module(module_path)
            if specific_names:
                for name in specific_names:
                    if not hasattr(mod, name):
                        logger.warning(
                            "[ModelRegistry] %s: attribute '%s' not found in %s",
                            group_name,
                            name,
                            module_path,
                        )
        except Exception as exc:
            error_msg = f"{type(exc).__name__}: {exc}"
            logger.warning(
                "[ModelRegistry] Failed to import %s (%s): %s",
                group_name,
                module_path,
                error_msg,
            )
            failures.append((group_name, error_msg))

    if failures:
        logger.warning(
            "[ModelRegistry] %d/%d model groups failed to import",
            len(failures),
            len(_MODEL_GROUPS),
        )
    else:
        logger.info(
            "[ModelRegistry] All %d model groups imported successfully",
            len(_MODEL_GROUPS),
        )

    return failures
