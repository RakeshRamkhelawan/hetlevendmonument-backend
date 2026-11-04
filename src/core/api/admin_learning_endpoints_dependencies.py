"""Dependency facade for admin_learning_endpoints.py (ADR-033 flat-file patroon)."""

from src.core.database.database import get_db as get_db
from src.core.governance.models import AuditLog as AuditLog
from src.core.governance.rate_limiter import (
    consent_read_limit as consent_read_limit,
    consent_update_limit as consent_update_limit,
)
from src.core.learning.budget_service import LearningBudgetService as LearningBudgetService
from src.core.learning.gdpr_service import LearningGDPRService as LearningGDPRService

__all__ = [
    "AuditLog",
    "LearningBudgetService",
    "LearningGDPRService",
    "consent_read_limit",
    "consent_update_limit",
    "get_db",
]
