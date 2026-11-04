"""Type definitions for Strategy Engine."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class StrategyType(Enum):
    """Types of strategic approaches"""

    MARKET_ANALYSIS = "market_analysis"
    COMPETITIVE_INTELLIGENCE = "competitive_intelligence"
    PRODUCT_STRATEGY = "product_strategy"
    BUSINESS_DEVELOPMENT = "business_development"
    TECHNOLOGY_ROADMAP = "technology_roadmap"
    RISK_ASSESSMENT = "risk_assessment"
    OPPORTUNITY_ANALYSIS = "opportunity_analysis"
    RESOURCE_ALLOCATION = "resource_allocation"


class StrategicPriority(Enum):
    """Strategic priority levels"""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    EXPLORATORY = "exploratory"


@dataclass
class StrategicObjective:
    """A strategic objective with metrics and timeline"""

    id: str
    title: str
    description: str
    priority: StrategicPriority
    target_date: datetime
    success_metrics: list[str]
    dependencies: list[str] = field(default_factory=list)
    progress: float = 0.0
    status: str = "active"
    stakeholders: list[str] = field(default_factory=list)


@dataclass
class StrategicInsight:
    """A strategic insight or recommendation"""

    id: str
    type: StrategyType
    title: str
    description: str
    confidence: float
    impact_score: float
    urgency_score: float
    supporting_evidence: list[str]
    recommended_actions: list[str]
    risks: list[str]
    opportunities: list[str]
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class StrategicContext:
    """Context for strategic decision making"""

    organization_goals: list[str]
    market_conditions: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    competitive_landscape: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    internal_capabilities: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    constraints: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    time_horizon: str
    success_criteria: list[str]


# Strategy templates by type
STRATEGY_TEMPLATES: dict[StrategyType, dict[str, Any]] = {  # TODO(TYPE): replace Any with concrete type
    StrategyType.MARKET_ANALYSIS: {
        "analysis_framework": [
            "market_size",
            "growth_rate",
            "trends",
            "segments",
            "barriers",
        ],
        "output_format": "comprehensive_market_report",
        "key_metrics": ["tam", "sam", "som", "cagr", "penetration_rate"],
    },
    StrategyType.COMPETITIVE_INTELLIGENCE: {
        "analysis_framework": [
            "competitors",
            "positioning",
            "strengths",
            "weaknesses",
            "market_share",
        ],
        "output_format": "competitive_analysis_report",
        "key_metrics": [
            "market_share",
            "pricing",
            "features",
            "customer_satisfaction",
        ],
    },
    StrategyType.PRODUCT_STRATEGY: {
        "analysis_framework": [
            "product_vision",
            "roadmap",
            "features",
            "pricing",
            "positioning",
        ],
        "output_format": "product_strategy_document",
        "key_metrics": ["adoption", "retention", "revenue", "satisfaction"],
    },
    StrategyType.BUSINESS_DEVELOPMENT: {
        "analysis_framework": [
            "opportunities",
            "partnerships",
            "expansion",
            "revenue_streams",
        ],
        "output_format": "business_development_plan",
        "key_metrics": ["revenue", "partnerships", "market_expansion"],
    },
    StrategyType.TECHNOLOGY_ROADMAP: {
        "analysis_framework": [
            "current_state",
            "future_state",
            "gaps",
            "investments",
        ],
        "output_format": "technology_roadmap",
        "key_metrics": ["innovation_rate", "technical_debt", "investment_roi"],
    },
}


@dataclass
class StrategyResult:
    """Result of strategy development."""

    id: str
    type: StrategyType
    context: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    analysis: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    recommendations: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    implementation_plan: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    success_metrics: dict[str, Any]  # TODO(TYPE): replace Any with concrete type
    created_at: str
    status: str
    confidence_score: float


@dataclass
class AnalysisResult:
    """Result of strategic analysis."""

    current_situation: str
    opportunities: list[str]
    threats: list[str]
    strategic_options: list[str]
    risk_assessment: str
    resource_requirements: list[str]
    raw_data: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
