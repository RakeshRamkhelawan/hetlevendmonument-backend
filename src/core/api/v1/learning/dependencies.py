"""Learning domain FastAPI dependencies (ADR-033)."""

from src.core.database.database import get_db
from src.core.learning.analytics import (
    LearningAnalytics,
    ReportGenerator,
    get_learning_metrics,
    get_roi_report,
)
from src.core.learning.feedback import store_async
from src.core.learning.multi_region import get_regional_context
from src.core.learning.service import AdaptationRuleService, FeedbackProcessingService

__all__ = [
    "AdaptationRuleService",
    "FeedbackProcessingService",
    "LearningAnalytics",
    "ReportGenerator",
    "get_db",
    "get_learning_metrics",
    "get_regional_context",
    "get_roi_report",
    "store_async",
]
