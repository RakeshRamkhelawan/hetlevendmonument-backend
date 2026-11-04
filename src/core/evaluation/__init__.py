"""
Evaluation Module - Automated RAG assessment and quality monitoring.
"""

from typing import Any

from src.core.evaluation.evaluation_service import (
    EvaluationMetrics,
    EvaluationRun,
    EvaluationService,
    evaluation_service,
)

__all__ = [
    "evaluation_service",
    "EvaluationService",
    "EvaluationMetrics",
    "EvaluationRun",
]
