"""
Evaluation API Schemas
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from src.core.evaluation.schemas import (
    EvaluationBatchRunResponse as EvaluationBatchRunResponse,
    EvaluationMetricsSchema as EvaluationMetricsSchema,
    EvaluationResultItem as EvaluationResultItem,
    EvaluationRunDetailResponse as EvaluationRunDetailResponse,
    EvaluationStatsResponse as EvaluationStatsResponse,
)


class EvaluationRunResponse(BaseModel):
    """Complete evaluation run data"""

    id: int
    tenant_id: int
    timestamp: datetime
    query: str
    response: str
    retrieved_contexts: list[str]
    metrics: EvaluationMetricsSchema
    metadata: dict[str, Any] = Field(  # TODO(TYPE): replace Any with concrete type
        default_factory=dict
    )  # TODO(TYPE): replace Any with concrete type


class TenantStatsResponse(BaseModel):
    """Aggregated statistics for a tenant"""

    tenant_id: int
    total_runs: int
    avg_faithfulness: float
    avg_precision: float
    avg_recall: float
    avg_context_precision: float
    last_updated: datetime


class EvaluationRequest(BaseModel):
    """Request to trigger an evaluation manually"""

    query: str = Field(..., min_length=1)
    response: str = Field(..., min_length=1)
    contexts: list[str] = Field(..., min_length=1)
    reference_answer: str | None = None
    metadata: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type


class EvaluationRunStatus(str):
    """Status of an evaluation run"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class EvaluationBatchRequest(BaseModel):
    """Request to start a batch evaluation"""

    num_samples: int = Field(default=100, ge=10, le=1000)
    dataset: str | None = None
    metadata: dict[str, Any] | None = None  # TODO(TYPE): replace Any with concrete type
