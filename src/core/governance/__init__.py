"""Governance module for EU AI Act and GDPR compliance."""

from __future__ import annotations

# AI Act Compliance
from src.core.governance.ai_act_classifier import (
    AIActRiskLevel,
    classify_agent,
    is_high_risk_capability,
)

# GDPR Compliance Services
from src.core.governance.ai_transparency_service import (
    AIDecisionRecord,
    AITransparencyService,
    ExplanationRequiredError,
    HumanReviewRequest,
    ProfilingType,
)
from src.core.governance.attribution import (
    AttributionLabel,
    add_attribution_to_response,
    create_attribution_label,
)
from src.core.governance.cookie_consent import (
    ConsentCategory,
    ConsentPreferences,
    CookieConsentManager,
)
from src.core.governance.dsar_service import (
    DSARAuthorizationError,
    DSARDeletionResult,
    DSARExportResult,
    DSARService,
    DSARTenantIsolationError,
)
from src.core.governance.incident_service import (
    IncidentReport,
    IncidentService,
    IncidentSeverity,
    IncidentStatus,
    classify_severity,
    requires_eu_reporting,
)
from src.core.governance.lawful_basis_registry import LawfulBasis, LawfulBasisRegistry
from src.core.governance.model_cards import (
    ModelCard,
    get_model_card,
    list_model_cards,
    register_model_card,
)
from src.core.governance.model_provenance import (
    ProvenanceRecord,
    ProvenanceService,
    new_provenance_record,
)

# GDPR Models
from src.core.governance.models import (
    AIDecision,
    AuditLog,
    DSARRequest,
    UserConsent,
    UserProfilingOptOut,
)
from src.core.governance.oversight_gate import OversightGate, OversightResult
from src.core.governance.public_docs import (
    ModelDocumentation,
    generate_model_documentation,
    get_model_card_docs,
)
from src.core.governance.governance_contract import AutonomyLevel, GovernanceContract
from src.core.governance.retention_cleanup import (
    DataCategory,
    RetentionCleanupService,
    RetentionJurisdiction,
)  # Disabled: imports copilot.council which imports apscheduler

__all__ = [
    # GDPR Services
    "AITransparencyService",
    "AIDecisionRecord",
    "CookieConsentManager",
    "ConsentCategory",
    "ConsentPreferences",
    "DSARService",
    "DSARExportResult",
    "DSARDeletionResult",
    "DSARAuthorizationError",
    "DSARTenantIsolationError",
    "ExplanationRequiredError",
    "HumanReviewRequest",
    "LawfulBasisRegistry",
    "LawfulBasis",
    "ProfilingType",
    "RetentionCleanupService",
    "DataCategory",
    "RetentionJurisdiction",
    # GDPR Models
    "AuditLog",
    "AIDecision",
    "DSARRequest",
    "HumanReviewRequest",
    "UserConsent",
    "UserProfilingOptOut",
    # AI Act
    "AIActRiskLevel",
    "AttributionLabel",
    "IncidentReport",
    "IncidentService",
    "IncidentSeverity",
    "IncidentStatus",
    "ModelCard",
    "ModelDocumentation",
    "OversightGate",
    "OversightResult",
    "ProvenanceRecord",
    "ProvenanceService",
    "add_attribution_to_response",
    "classify_agent",
    "classify_severity",
    "create_attribution_label",
    "generate_model_documentation",
    "get_model_card",
    "get_model_card_docs",
    "is_high_risk_capability",
    "list_model_cards",
    "new_provenance_record",
    "register_model_card",
    "requires_eu_reporting",
    # ADR-031 GovernanceContract
    "AutonomyLevel",
    "GovernanceContract",
]
