"""Prediction domain schemas (ADR-033 Laag 1)."""

from pydantic import BaseModel


class PredictionRequest(BaseModel):
    hours_ahead: int = 24
    prediction_types: list[str] | None = None
    include_optimization_plan: bool = True


class MetricCollectionResponse(BaseModel):
    status: str
    metrics_collected: int
    timestamp: str


class PredictionResponse(BaseModel):
    predictions: list[dict[str, object]]
    optimization_plan: dict[str, object] | None
    system_status: dict[str, object]


class InitializeResponse(BaseModel):
    status: str
    message: str
    timestamp: str
    capabilities: list[str]


class SystemStatusResponse(BaseModel):
    system_status: str
    prediction_engine: dict[str, object]
    timestamp: str
    version: str


class RecentPredictionsResponse(BaseModel):
    predictions: list[dict[str, object]]
    total_count: int
    returned_count: int
    timestamp: str


class MetricsHistoryResponse(BaseModel):
    metrics: list[dict[str, object]]
    count: int
    time_range_hours: int
    metric_type_filter: str | None
    timestamp: str


class TrendsResponse(BaseModel):
    trends: dict[str, object]
    analysis_period_hours: int
    total_metrics_analyzed: int
    trend_summary: dict[str, int]
    timestamp: str


class HealthCheckResponse(BaseModel):
    status: str
    prediction_engine: str
    timestamp: str
    version: str
    error: str | None = None


class OptimizationExecutionResponse(BaseModel):
    status: str
    plan_id: str
    message: str
    estimated_completion: str
    timestamp: str
