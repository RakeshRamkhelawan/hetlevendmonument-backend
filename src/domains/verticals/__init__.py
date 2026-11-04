"""
Verticals Module
Provides vertical-specific agent templates for Healthcare, Nonprofit, and Media.
"""

from typing import Any

from .healthcare import ComplianceStatus, HealthcareComplianceAgent, PatientRecord
from .media import BiasType, ContentSubmission, MediaModerationAgent, ModerationAction
from .nonprofit import ChurnRisk, DonorProfile, EngagementAction, NonprofitEngagementAgent

__all__ = [
    # Healthcare
    "HealthcareComplianceAgent",
    "ComplianceStatus",
    "PatientRecord",
    # Nonprofit
    "NonprofitEngagementAgent",
    "ChurnRisk",
    "EngagementAction",
    "DonorProfile",
    # Media
    "MediaModerationAgent",
    "BiasType",
    "ModerationAction",
    "ContentSubmission",
]
