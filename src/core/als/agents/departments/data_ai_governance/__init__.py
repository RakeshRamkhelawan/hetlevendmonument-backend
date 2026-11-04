"""Data & AI Governance Department Agents.

3 Agents:
    - DataIntegrityEthicsAgent (ML): Data quality, lineage, ethics
    - DataScienceAgent (ML): ML models, feature engineering, analysis
    - AiEthicsAuditorAgent (LLM): AI bias detection, fairness, explainability
    - DataQualitySentinelAgent (ML): Data quality monitoring
"""

from typing import Any

from src.core.als.agents.departments.data_ai_governance.ai_ethics_auditor_agent import (
    AIEthicsAuditorAgent,
)
from src.core.als.agents.departments.data_ai_governance.data_integrity_ethics_agent import (
    DataIntegrityEthicsAgent,
)
from src.core.als.agents.departments.data_ai_governance.data_quality_sentinel import (
    DataQualitySentinelAgent,
)
from src.core.als.agents.departments.data_ai_governance.data_science_agent import DataScienceAgent

__all__ = [
    "DataIntegrityEthicsAgent",
    "DataScienceAgent",
    "AIEthicsAuditorAgent",
    "DataQualitySentinelAgent",
]
