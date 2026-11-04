"""Product & Innovation (R&D) Department Agents."""

from typing import Any

from src.core.als.agents.departments.product_innovation.market_gap_analysis_agent import (
    MarketGapAnalysisAgent,
)
from src.core.als.agents.departments.product_innovation.qa_bug_detection_agent import (
    QABugDetectionAgent,
)
from src.core.als.agents.departments.product_innovation.technical_architect import (
    TechnicalArchitectAgent,
)
from src.core.als.agents.departments.product_innovation.ux_ui_design_synthesizer import (
    UXUIDesignSynthesizerAgent,
)

__all__ = [
    "TechnicalArchitectAgent",
    "MarketGapAnalysisAgent",
    "UXUIDesignSynthesizerAgent",
    "QABugDetectionAgent",
]
