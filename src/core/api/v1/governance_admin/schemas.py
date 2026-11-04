"""Governance Admin domain schemas: enums and Pydantic models."""

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ============================================================================
# Enums
# ============================================================================


class AnomalyType(str, Enum):
    BIAS = "bias"
    COST = "cost"
    PERFORMANCE = "performance"
    SECURITY = "security"
    COMPLIANCE = "compliance"
    QUALITY = "quality"


class AnomalySeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class RiskCategory(str, Enum):
    OPERATIONAL = "operational"
    FINANCIAL = "financial"
    REPUTATIONAL = "reputational"
    COMPLIANCE = "compliance"
    TECHNICAL = "technical"
    SECURITY = "security"


class RiskLevel(str, Enum):
    MINIMAL = "minimal"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


# ============================================================================
# Pydantic Models
# ============================================================================


class AnomalyDetail(BaseModel):
    id: str = Field(..., description="Anomaly ID")
    type: AnomalyType
    severity: AnomalySeverity
    title: str
    description: str
    source: str
    source_id: str | None = Field(None)
    metric_value: float | None = Field(None)
    expected_range: str | None = Field(None)
    detected_at: str
    recommendations: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)  # TODO(TYPE): replace Any with concrete type


class AnomalyStats(BaseModel):
    total: int = 0
    by_type: dict[str, int] = Field(default_factory=dict)
    by_severity: dict[str, int] = Field(default_factory=dict)
    trend: str = "stable"


class AnomaliesResponse(BaseModel):
    anomalies: list[AnomalyDetail]
    stats: AnomalyStats
    period_start: str
    period_end: str
    tenant_id: int


class RiskFactor(BaseModel):
    id: str
    category: RiskCategory
    name: str
    description: str
    score: float = Field(..., ge=0, le=100)
    level: RiskLevel
    likelihood: float = Field(..., ge=0, le=1)
    impact: float = Field(..., ge=0, le=1)
    mitigations: list[str] = Field(default_factory=list)


class RiskAssessment(BaseModel):
    mission_id: str
    overall_score: float = Field(..., ge=0, le=100)
    overall_level: RiskLevel
    risk_factors: list[RiskFactor] = Field(default_factory=list)
    assessed_at: str
    valid_until: str
    recommendations: list[str] = Field(default_factory=list)
    tenant_id: int


class RiskResponse(BaseModel):
    assessment: RiskAssessment
    message: str
