"""HR & Culture Department Agents.

4 Agents:
    - TalentAcquisitionAgent (ML): Recruiting, candidate screening
    - EmployeeSentimentAgent (ML): Engagement surveys, sentiment analysis
    - SkillsGapTrainingAgent (LLM): Learning paths, training recommendations
    - InternalMobilityAgent (ML): Career pathing, succession planning
"""

from typing import Any

from src.core.als.agents.departments.hr_culture.employee_sentiment_agent import (
    EmployeeSentimentAgent,
)
from src.core.als.agents.departments.hr_culture.internal_mobility_agent import InternalMobilityAgent
from src.core.als.agents.departments.hr_culture.skills_gap_training_agent import (
    SkillsGapTrainingAgent,
)
from src.core.als.agents.departments.hr_culture.talent_acquisition_agent import (
    TalentAcquisitionAgent,
)

__all__ = [
    "TalentAcquisitionAgent",
    "EmployeeSentimentAgent",
    "SkillsGapTrainingAgent",
    "InternalMobilityAgent",
]
