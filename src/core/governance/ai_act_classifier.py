"""AI Act Risk Classifier for EU AI Act compliance.

Task 1: Risk Classification System
Classifies AI agents into EU AI Act risk levels:
- HIGH_RISK: Annex III systems (HR recruitment, credit scoring, etc.)
- LIMITED: Article 52 GPAI systems with transparency obligations
- MINIMAL: No AI capabilities or low-risk applications

Reference: Regulation (EU) 2024/1689
"""

from __future__ import annotations

from src.core.shared.ai_act_types import AIActRiskLevel as AIActRiskLevel


# Annex III High-Risk AI Systems - Keywords for detection
HIGH_RISK_KEYWORDS = {
    # HR/Employment (Annex III.4)
    "recruitment",
    "hiring",
    "talent_acquisition",
    "resume_screening",
    "candidate_ranking",
    "performance_evaluation",
    "promotion_recommendation",
    "employee_monitoring",
    "workplace_surveillance",
    "termination_decision",
    # Credit/Finance (Annex III.5)
    "credit_scoring",
    "creditworthiness",
    "loan_assessment",
    "loan_approval",
    "credit_decision",
    "mortgage_assessment",
    "insurance_pricing",
    # Law Enforcement (Annex III.6)
    "risk_assessment",
    "polygraph",
    "evidence_evaluation",
    # Migration/Asylum (Annex III.7)
    "visa_assessment",
    "asylum_decision",
    "border_control",
    # Justice (Annex III.8)
    "legal_research",
    "case_prioritization",
    # Biometric (Annex III.1)
    "face_recognition",
    "facial_recognition",
    "emotion_recognition",
    "biometric_identification",
    "biometric_categorization",
    # Education/Vocational (Annex III.3)
    "admission_decision",
    "exam_scoring",
    "student_evaluation",
    # Access to Services (Annex III.4a)
    "benefit_eligibility",
    "benefit_decision",
    # Critical Infrastructure (Annex III.2)
    "fraud_detection",  # For critical infrastructure
    "anomaly_detection",  # For critical systems
}

# High-risk department indicators
HIGH_RISK_DEPARTMENTS = {
    "hr",
    "human_resources",
    "personnel",
    "talent",
    "recruiting",
    "finance",
    "credit",
    "lending",
    "risk",
    "fraud",
    "security",
    "law_enforcement",
    "justice",
    "legal",
    "immigration",
    "border",
    "education",
    "admissions",
    "benefits",
}

# High-risk specialisation indicators
HIGH_RISK_SPECIALISATIONS = {
    "recruitment",
    "hiring",
    "talent_acquisition",
    "performance_evaluation",
    "credit_analysis",
    "credit_scoring",
    "fraud_detection",
    "security",
    "biometric",
    "surveillance",
    "risk_assessment",
}

# General AI capability keywords (Article 52 transparency obligations)
AI_CAPABILITIES = {
    "text_generation",
    "document_processing",
    "data_analysis",
    "reporting",
    "classification",
    "prediction",
    "recommendation",
    "nlp",
    "natural_language",
    "ml",
    "machine_learning",
    "ai",
    "automation",
    "chatbot",
    "conversation",
    "summarization",
    "translation",
}


# Art. 5 prohibited practices - absolute ban, no exceptions
UNACCEPTABLE_CAPABILITIES: set[str] = {
    "social_scoring",
    "mass_surveillance",
    "biometric_categorization_sensitive",
    "emotion_recognition_workplace",
    "emotion_recognition_education",
    "predictive_policing_individual",
    "subliminal_manipulation",
    "exploitation_vulnerable_groups",
}


def is_unacceptable_capability(capability: str) -> bool:
    """Check if a capability is prohibited under Art. 5 EU AI Act.

    Args:
        capability: The capability name to check.

    Returns:
        True if the capability is an Art. 5 prohibited practice.
    """
    return capability.lower().replace(" ", "_") in UNACCEPTABLE_CAPABILITIES


def is_high_risk_capability(capability: str) -> bool:
    """Check if a capability is classified as high-risk under Annex III.

    Args:
        capability: The capability name to check.

    Returns:
        True if the capability is high-risk, False otherwise.
    """
    capability_lower = capability.lower().replace(" ", "_")

    # Direct keyword match
    if capability_lower in HIGH_RISK_KEYWORDS:
        return True

    # Partial match for compound terms
    for keyword in HIGH_RISK_KEYWORDS:
        if keyword in capability_lower or capability_lower in keyword:
            return True

    return False


def classify_agent(
    name: str,
    department: str,
    specialisation: str,
    capabilities: list[str],
) -> AIActRiskLevel:
    """Classify an AI agent into EU AI Act risk levels.

    Classification logic:
    1. HIGH_RISK if:
       - Any capability matches Annex III high-risk keywords, OR  # TODO(TYPE): replace Any with concrete type
       - 2+ of 3 signals match (department, specialisation, capabilities)
    2. LIMITED if:
       - Has AI capabilities but no high-risk indicators (Article 52 GPAI)
    3. MINIMAL if:
       - No AI capabilities and no high-risk indicators

    Args:
        name: Agent name (for logging/context)
        department: Department the agent belongs to
        specialisation: Agent's specialisation area
        capabilities: List of agent capabilities

    Returns:
        AIActRiskLevel enum value
    """
    dept_lower = department.lower().replace(" ", "_")
    spec_lower = specialisation.lower().replace(" ", "_")

    # Check 0: Art. 5 prohibited practices - absolute ban, checked FIRST
    for capability in capabilities:
        if is_unacceptable_capability(capability):
            return AIActRiskLevel.UNACCEPTABLE

    # Check 1: Direct capability match = automatic HIGH_RISK
    for capability in capabilities:
        if is_high_risk_capability(capability):
            return AIActRiskLevel.HIGH_RISK

    # Check 2: Count high-risk signals (2+ needed for HIGH_RISK)
    signals = 0

    # Signal 1: High-risk department
    if dept_lower in HIGH_RISK_DEPARTMENTS:
        signals += 1

    # Signal 2: High-risk specialisation
    if spec_lower in HIGH_RISK_SPECIALISATIONS:
        signals += 1

    # Signal 3: Any high-risk capability (already checked above, but count here)
    # Note: Direct capability match returns early above, this is for counting
    high_risk_cap_count = sum(1 for cap in capabilities if is_high_risk_capability(cap))
    if high_risk_cap_count > 0:
        signals += 1

    # Require 2+ signals for HIGH_RISK classification
    if signals >= 2:
        return AIActRiskLevel.HIGH_RISK

    # Check 3: Has AI capabilities = LIMITED (Article 52)
    if capabilities:
        return AIActRiskLevel.LIMITED

    # No capabilities, no high-risk indicators = MINIMAL
    return AIActRiskLevel.MINIMAL
