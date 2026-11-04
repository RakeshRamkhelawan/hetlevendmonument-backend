"""
Learning services for the SanskritiSetu AI system.

These services handle specific aspects of the learning system:
- ObservationService: Recording and managing observations
- PatternService: Pattern recognition and management
- AdaptationService: Adaptation rule creation and application
- InsightService: Insight generation and management
"""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.core.learning.cross_agent_service import CrossAgentLearningService

from src.core.learning.services.adaptation_service import AdaptationService
from src.core.learning.services.insight_service import InsightService
from src.core.learning.services.observation_service import ObservationService
from src.core.learning.services.pattern_service import PatternService

__all__ = [
    "ObservationService",
    "PatternService",
    "AdaptationService",
    "InsightService",
    "CrossAgentLearningService",
]
