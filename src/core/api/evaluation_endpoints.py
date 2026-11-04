# orphan:exempt reason: nog niet gemigreerd naar v1/; TODO(SP-VOLGENDE): migreer naar v1/<domein>/
"""
Evaluation API Endpoints

This module provides endpoints for RAG (Retrieval-Augmented Generation) evaluation,
including batch evaluation runs, statistics, and detailed results.

## Evaluation Process

1. **Start Evaluation**: POST /evaluate - Initiates a batch evaluation run
2. **Monitor Progress**: GET /runs - List all runs and their status
3. **Get Details**: GET /results/{run_id} - Retrieve detailed results
4. **Statistics**: GET /stats - Get aggregated metrics

## Metrics Explained

- **Faithfulness**: Measures if the response is supported by the retrieved context
- **Context Precision**: Measures relevance of retrieved context
- **Answer Relevancy**: Measures how well the answer matches the query
- **Context Recall**: Measures if all relevant context was retrieved
"""

from typing import Optional, cast

from fastapi import APIRouter, Depends, HTTPException, Path, Query

from src.core.api.schemas.evaluation_schemas import (
    EvaluationBatchRequest,
    EvaluationBatchRunResponse,
    EvaluationRequest,
    EvaluationRunDetailResponse,
    EvaluationRunResponse,
    EvaluationStatsResponse,
    TenantStatsResponse,
)
from src.core.api.dependencies import get_current_tenant_id
from src.core.evaluation.batch_evaluation_service import batch_evaluation_service
from src.core.evaluation.evaluation_service import evaluation_service
import logging
logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/evaluation",
    tags=["Evaluation"],
    responses={
        401: {"description": "Unauthorized - Invalid or missing authentication token"},
        403: {"description": "Forbidden - Access denied to this resource"},
        500: {"description": "Internal Server Error"},
    },
)


@router.post(
    "/evaluate",
    response_model=EvaluationBatchRunResponse,
    status_code=201,
    summary="Start Batch Evaluation",
    description="""
    Start a new batch RAG evaluation run with multiple samples.

    The evaluation will assess:
    - Faithfulness: How well the response is grounded in context
    - Context Precision: Relevance of retrieved documents
    - Answer Relevancy: Appropriateness of the answer
    - Context Recall: Coverage of relevant information

    Returns immediately with a run ID. Use GET /runs to monitor progress.
    """,
    responses={
        201: {
            "description": "Evaluation run created successfully",
            "content": {
                "application/json": {
                    "example": {
                        "id": "eval-123",
                        "name": "Batch Evaluation 1",
                        "status": "pending",
                        "num_samples": 100,
                        "created_at": "2026-03-07T10:00:00Z",
                    }
                }
            },
        }
    },
)
async def trigger_batch_evaluation(
    request: EvaluationBatchRequest, tenant_id: int = Depends(get_current_tenant_id)
) -> EvaluationBatchRunResponse:
    """
    Start a batch RAG evaluation run.

    - **tenant_id**: Automatically extracted from JWT token
    - **num_samples**: Number of evaluation samples (10-1000)
    - Returns run ID for tracking progress
    """
    try:
        run = await batch_evaluation_service.start_batch_evaluation(
            tenant_id=tenant_id,
            num_samples=request.num_samples,
            name=f"Batch Evaluation {tenant_id}",
            metadata=request.metadata,
        )
        return run
    except Exception as e:
        logger.error("trigger_batch_evaluation mislukt: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="Er is een interne fout opgetreden.",
        )


@router.get(
    "/runs",
    response_model=list[EvaluationBatchRunResponse],
    summary="List Evaluation Runs",
    description="""
    Retrieve a list of all evaluation runs for the current tenant.

    Supports filtering by status and pagination via limit parameter.
    Results are ordered by creation date (newest first).
    """,
    responses={
        200: {
            "description": "List of evaluation runs",
            "content": {
                "application/json": {
                    "example": [
                        {
                            "id": "eval-123",
                            "name": "Batch Evaluation 1",
                            "status": "completed",
                            "num_samples": 100,
                            "created_at": "2026-03-07T10:00:00Z",
                            "metrics": {
                                "faithfulness": 0.92,
                                "context_precision": 0.88,
                                "answer_relevancy": 0.91,
                            },
                        }
                    ]
                }
            },
        }
    },
)
async def list_evaluation_runs(
    tenant_id: int = Depends(get_current_tenant_id),
    status: str | None = Query(
        None,
        description="Filter by run status: pending, running, completed, failed",
        enum=["pending", "running", "completed", "failed"],
    ),
    limit: int = Query(50, ge=1, le=100, description="Maximum number of runs to return"),
) -> list[EvaluationBatchRunResponse]:
    """
    List all evaluation runs for the current tenant.

    - **status**: Optional filter by status
    - **limit**: Maximum results (1-100, default 50)
    """
    try:
        runs = await batch_evaluation_service.list_runs(
            tenant_id=tenant_id,
            status=status,
            limit=limit,
        )
        return [EvaluationBatchRunResponse.model_validate(run) for run in runs]
    except Exception as e:
        logger.error("list_evaluation_runs mislukt: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")


@router.get(
    "/results/{run_id}",
    response_model=EvaluationRunDetailResponse,
    summary="Get Evaluation Run Details",
    description="""
    Retrieve detailed results of a specific evaluation run.

    Includes:
    - Run metadata (status, timestamps, configuration)
    - Aggregated metrics (faithfulness, precision, etc.)
    - Individual sample results with scores
    - Error details if the run failed
    """,
    responses={
        200: {
            "description": "Detailed run information",
            "content": {
                "application/json": {
                    "example": {
                        "id": "eval-123",
                        "name": "Batch Evaluation 1",
                        "status": "completed",
                        "num_samples": 100,
                        "metrics": {
                            "faithfulness": 0.92,
                            "precision": 0.88,
                            "recall": 0.85,
                            "context_precision": 0.90,
                            "answer_relevancy": 0.91,
                        },
                        "results": [{"query": "What is AI?", "passed": True, "score": 0.95}],
                    }
                }
            },
        },
        404: {"description": "Evaluation run not found"},
    },
)
async def get_evaluation_run_detail(
    run_id: str = Path(
        ...,
        description="Unique identifier of the evaluation run",
        examples=["eval-123"],
    ),
    tenant_id: int = Depends(get_current_tenant_id),
) -> EvaluationRunDetailResponse:
    """
    Retrieve detailed results of a specific evaluation run.

    - **run_id**: The evaluation run ID
    - Returns 404 if run not found or doesn't belong to tenant
    """
    try:
        run = await batch_evaluation_service.get_run_detail(run_id, tenant_id)
        if not run:
            raise HTTPException(status_code=404, detail="Evaluation run not found")
        return run
    except HTTPException:
        raise
    except Exception as e:
        logger.error("get_evaluation_run_detail mislukt: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")


@router.get(
    "/stats",
    response_model=EvaluationStatsResponse,
    summary="Get Evaluation Statistics",
    description="""
    Get aggregated statistics for all evaluation runs in the tenant.

    Returns:
    - Total number of runs
    - Completion rate
    - Average metrics across all runs
    - Total samples evaluated
    """,
    responses={
        200: {
            "description": "Aggregated statistics",
            "content": {
                "application/json": {
                    "example": {
                        "total_runs": 50,
                        "completed_runs": 45,
                        "failed_runs": 5,
                        "avg_faithfulness": 0.89,
                        "avg_context_precision": 0.87,
                        "avg_answer_relevancy": 0.90,
                        "total_samples_evaluated": 5000,
                    }
                }
            },
        }
    },
)
async def get_evaluation_stats(
    tenant_id: int = Depends(get_current_tenant_id),
) -> EvaluationStatsResponse:
    """
    Get aggregated statistics for all evaluation runs.

    Calculates averages only from completed runs.
    """
    try:
        stats = await batch_evaluation_service.get_stats(tenant_id)
        return stats
    except Exception as e:
        logger.error("get_evaluation_stats mislukt: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")


# Legacy endpoints for backward compatibility


@router.post(
    "/evaluate/legacy",
    response_model=EvaluationRunResponse,
    summary="Legacy: Single Evaluation (Deprecated)",
    description="""
    **DEPRECATED**: Use POST /evaluate instead.

    Manually trigger a single RAG evaluation.
    This endpoint is maintained for backward compatibility.
    """,
    deprecated=True,
)
async def trigger_evaluation(
    request: EvaluationRequest, tenant_id: int = Depends(get_current_tenant_id)
) -> EvaluationRunResponse:
    """Manually trigger a single RAG evaluation (legacy endpoint)."""
    try:
        run = await evaluation_service.evaluate_rag_response(
            tenant_id=tenant_id,
            query=request.query,
            response=request.response,
            contexts=request.contexts,
            reference_answer=request.reference_answer or "",
            metadata=request.metadata,
        )
        return cast(EvaluationRunResponse, run)
    except Exception as e:
        logger.error("trigger_evaluation mislukt: %s: %s", type(e).__name__, e, exc_info=True)
        raise HTTPException(status_code=500, detail="Er is een interne fout opgetreden.")


@router.get(
    "/results/legacy/{run_id}",
    response_model=EvaluationRunResponse,
    summary="Legacy: Get Single Evaluation (Deprecated)",
    description="**DEPRECATED**: Use GET /results/{run_id} instead.",
    deprecated=True,
)
async def get_evaluation_run(
    run_id: int, tenant_id: int = Depends(get_current_tenant_id)
) -> EvaluationRunResponse:
    """Retrieve details of a specific legacy evaluation run."""
    run = await evaluation_service.get_run_results(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Evaluation run not found")

    if run.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Access denied to this evaluation run")

    return cast(EvaluationRunResponse, run)


@router.get(
    "/stats/legacy",
    response_model=TenantStatsResponse,
    summary="Legacy: Get Tenant Stats (Deprecated)",
    description="**DEPRECATED**: Use GET /stats instead.",
    deprecated=True,
)
async def get_tenant_evaluation_stats(
    tenant_id: int = Depends(get_current_tenant_id),
) -> TenantStatsResponse:
    """Get aggregated quality statistics for the current tenant (legacy endpoint)."""
    stats = await evaluation_service.get_tenant_stats(tenant_id)
    if stats.get("status") == "no_data":
        raise HTTPException(status_code=404, detail="No evaluation data found for this tenant")
    return TenantStatsResponse.model_validate(stats)
