"""Evaluation domain response schemas used by domain services and re-exported by the API layer."""

from typing import Any

from pydantic import BaseModel, Field


class EvaluationMetricsSchema(BaseModel):
    """Evaluation metrics for a run"""

    faithfulness: float
    precision: float
    recall: float
    context_precision: float
    answer_relevancy: float
    context_recall: float | None = None
    latency_ms: float | None = None


class EvaluationBatchRunResponse(BaseModel):
    """Response for a batch evaluation run"""

    id: str
    name: str
    status: str
    num_samples: int
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    updated_at: str | None = None
    metrics: EvaluationMetricsSchema | None = None
    error: str | None = None


class EvaluationStatsResponse(BaseModel):
    """Statistics for evaluation runs"""

    total_runs: int
    completed_runs: int
    failed_runs: int
    avg_faithfulness: float
    avg_context_precision: float
    avg_answer_relevancy: float
    avg_context_recall: float | None = None
    total_samples_evaluated: int


class EvaluationResultItem(BaseModel):
    """Individual evaluation result within a run"""

    query: str
    passed: bool
    score: float
    details: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type


class EvaluationRunDetailResponse(BaseModel):
    """Detailed response for a specific run including all results"""

    id: str
    name: str
    status: str
    num_samples: int
    started_at: str | None = None
    completed_at: str | None = None
    metrics: EvaluationMetricsSchema | None = None
    results: list[EvaluationResultItem] = Field(default_factory=list)
    error: str | None = None
