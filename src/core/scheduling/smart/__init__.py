"""Smart Scheduling Intelligence Module.

Phase 3: AI-powered scheduling capabilities including:
- Predictive availability analysis
- Multi-participant optimization
- Smart conflict resolution
- Meeting quality scoring
- Auto-buffer management
"""

from src.core.scheduling.smart.models import AvailabilityPattern, UserSchedulingProfile
from src.core.scheduling.smart.optimizer import MultiParticipantOptimizer
from src.core.scheduling.smart.predictor import AvailabilityPredictor
from src.core.scheduling.smart.resolver import ConflictResolver
from src.core.scheduling.smart.scorer import MeetingQualityScorer
from src.core.scheduling.smart.service import SmartSchedulingService

__all__ = [
    "AvailabilityPattern",
    "UserSchedulingProfile",
    "AvailabilityPredictor",
    "MultiParticipantOptimizer",
    "MeetingQualityScorer",
    "ConflictResolver",
    "SmartSchedulingService",
]
