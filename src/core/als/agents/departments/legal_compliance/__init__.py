"""Legal, Risk & Compliance Department Agents.

4 Agents:
    - GdprPrivacyGuardAgent (LLM): GDPR compliance, privacy assessments
    - ContractLifecycleAgent (LLM): Contract drafting, negotiation, management
    - RegulatoryTrackingAgent (ML): Regulatory monitoring, compliance tracking
    - ContractAnalysisAgent (LLM): Contract review, clause analysis
"""

from typing import Any

from src.core.als.agents.departments.legal_compliance.contract_analysis_agent import (
    ContractAnalysisAgent,
)
from src.core.als.agents.departments.legal_compliance.contract_lifecycle_agent import (
    ContractLifecycleAgent,
)
from src.core.als.agents.departments.legal_compliance.gdpr_privacy_guard import (
    GDPRPrivacyGuardAgent,
)
from src.core.als.agents.departments.legal_compliance.regulatory_tracking_agent import (
    RegulatoryTrackingAgent,
)

__all__ = [
    "GDPRPrivacyGuardAgent",
    "ContractLifecycleAgent",
    "RegulatoryTrackingAgent",
    "ContractAnalysisAgent",
]
