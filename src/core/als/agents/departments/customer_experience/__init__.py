"""Customer Experience (CX) & Support Department Agents.

3 Agents:
    - SentimentSupportAgent (Hybrid): Sentiment analysis, ticket routing
    - CustomerSuccessAgent (LLM): Onboarding, adoption, health scoring
    - CommunityManagementAgent (LLM): Community engagement, forum moderation
"""

from typing import Any

from src.core.als.agents.departments.customer_experience.community_management_agent import (
    CommunityManagementAgent,
)
from src.core.als.agents.departments.customer_experience.customer_success_agent import (
    CustomerSuccessAgent,
)
from src.core.als.agents.departments.customer_experience.sentiment_support import (
    SentimentSupportAgent,
)

__all__ = [
    "SentimentSupportAgent",
    "CustomerSuccessAgent",
    "CommunityManagementAgent",
]
