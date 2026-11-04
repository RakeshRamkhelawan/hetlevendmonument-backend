"""
Batch Evaluation Service
Manages batch RAG evaluation runs with multiple samples.
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select

from src.core.evaluation.schemas import (
    EvaluationBatchRunResponse,
    EvaluationMetricsSchema,
    EvaluationResultItem,
    EvaluationRunDetailResponse,
    EvaluationStatsResponse,
)
from src.core.config.unified_config import config
from src.core.database.database import db_manager
from src.core.models.evaluation_models import EvaluationResult, EvaluationRunModel
from src.core.shared.production_logging import SafeLogger

logger = SafeLogger(__name__)


class BatchEvaluationService:
    """Service for managing batch evaluation runs"""

    def __init__(self) -> None:
        self._active_runs: dict[
            str, asyncio.Task[Any]  # TODO(TYPE): replace Any with concrete type
        ] = {}  # TODO(TYPE): replace Any with concrete type

    async def start_batch_evaluation(
        self,
        tenant_id: int,
        num_samples: int,
        name: str | None = None,
        metadata: dict[str, Any] | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> EvaluationBatchRunResponse:
        """Start a new batch evaluation run"""

        run_id = str(uuid.uuid4())
        run_name = name or f"Evaluation Run {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}"

        # Create run record in database
        async with db_manager.get_session() as session:
            db_run = EvaluationRunModel(
                id=int(uuid.uuid4()) % (2**31),  # Convert to int for compat
                tenant_id=tenant_id,
                name=run_name,
                num_samples=num_samples,
                status="pending",
                metadata_={"requested_run_id": run_id, **(metadata or {})},
            )
            session.add(db_run)
            await session.commit()
            await session.refresh(db_run)

            # Return immediately with pending status
            return self._map_to_batch_response(db_run)

    async def list_runs(
        self,
        tenant_id: int,
        status: str | None = None,
        limit: int = 50,
    ) -> list[EvaluationBatchRunResponse]:
        """List evaluation runs for a tenant"""

        async with db_manager.get_session() as session:
            stmt = (
                select(EvaluationRunModel)
                .where(EvaluationRunModel.tenant_id == tenant_id)
                .order_by(EvaluationRunModel.created_at.desc())
                .limit(limit)
            )

            if status:
                stmt = stmt.where(EvaluationRunModel.status == status)

            result = await session.execute(stmt)
            runs = result.scalars().all()

            return [self._map_to_batch_response(run) for run in runs]

    async def get_run_detail(
        self, run_id: str, tenant_id: int
    ) -> EvaluationRunDetailResponse | None:
        """Get detailed information about a specific run"""

        async with db_manager.get_session() as session:
            # Try to find by string ID first (from frontend)
            try:
                run_id_int = int(run_id)
            except ValueError:
                # If not an int, look up in metadata
                stmt = select(EvaluationRunModel).where(
                    EvaluationRunModel.tenant_id == tenant_id,
                    EvaluationRunModel.metadata_.contains({"requested_run_id": run_id}),
                )
                result = await session.execute(stmt)
                run = result.scalar_one_or_none()
            else:
                run = await session.get(EvaluationRunModel, run_id_int)

            if not run or run.tenant_id != tenant_id:
                return None

            # Get individual results
            results_stmt = select(EvaluationResult).where(EvaluationResult.run_id == run.id)
            results_result = await session.execute(results_stmt)
            db_results = results_result.scalars().all()

            result_items = [
                EvaluationResultItem(
                    query=r.query or "",
                    passed=(r.faithfulness or 0.0) >= 0.7,  # Simple threshold
                    score=r.faithfulness or 0.0,
                    details={
                        "precision": r.precision,
                        "recall": r.recall,
                        "context_precision": r.context_precision,
                    },
                )
                for r in db_results
            ]

            metrics = None
            if run.avg_faithfulness is not None:
                metrics = EvaluationMetricsSchema(
                    faithfulness=run.avg_faithfulness or 0.0,
                    precision=run.avg_precision or 0.0,
                    recall=run.avg_recall or 0.0,
                    context_precision=run.avg_context_precision or 0.0,
                    answer_relevancy=run.avg_answer_relevancy or 0.0,
                    context_recall=run.avg_context_recall,
                )

            return EvaluationRunDetailResponse(
                id=str(run.id),
                name=run.name or "",
                status=run.status or "unknown",
                num_samples=run.num_samples or 0,
                started_at=run.started_at.isoformat() if run.started_at else None,
                completed_at=run.completed_at.isoformat() if run.completed_at else None,
                metrics=metrics,
                results=result_items,
                error=run.error,
            )

    async def get_stats(self, tenant_id: int) -> EvaluationStatsResponse:
        """Get aggregated statistics for a tenant"""

        async with db_manager.get_session() as session:
            # Count runs by status
            status_stmt = (
                select(EvaluationRunModel.status, func.count(EvaluationRunModel.id).label("count"))
                .where(EvaluationRunModel.tenant_id == tenant_id)
                .group_by(EvaluationRunModel.status)
            )

            status_result = await session.execute(status_stmt)
            status_counts = {row.status: row.count for row in status_result.mappings()}

            # Calculate averages for completed runs
            avg_stmt = select(
                func.avg(EvaluationRunModel.avg_faithfulness).label("avg_faith"),
                func.avg(EvaluationRunModel.avg_context_precision).label("avg_ctx_prec"),
                func.avg(EvaluationRunModel.avg_answer_relevancy).label("avg_rel"),
                func.avg(EvaluationRunModel.avg_context_recall).label("avg_ctx_rec"),
                func.sum(EvaluationRunModel.num_samples).label("total_samples"),
            ).where(
                EvaluationRunModel.tenant_id == tenant_id, EvaluationRunModel.status == "completed"
            )

            avg_result = await session.execute(avg_stmt)
            avg_row = avg_result.mappings().one()

            total_runs = sum(status_counts.values())
            completed_runs = status_counts.get("completed", 0)
            failed_runs = status_counts.get("failed", 0)

            return EvaluationStatsResponse(
                total_runs=total_runs,
                completed_runs=completed_runs,
                failed_runs=failed_runs,
                avg_faithfulness=float(avg_row.avg_faith or 0),
                avg_context_precision=float(avg_row.avg_ctx_prec or 0),
                avg_answer_relevancy=float(avg_row.avg_rel or 0),
                avg_context_recall=float(avg_row.avg_ctx_rec) if avg_row.avg_ctx_rec else None,
                total_samples_evaluated=int(avg_row.total_samples or 0),
            )

    async def update_run_status(
        self,
        run_id: int,
        status: str,
        metrics: dict[str, float] | None = None,
        error: str | None = None,
    ) -> None:
        """Update the status of a run"""

        async with db_manager.get_session() as session:
            run = await session.get(EvaluationRunModel, run_id)
            if not run:
                return

            run.status = status

            if status == "running" and not run.started_at:
                run.started_at = datetime.now(timezone.utc)

            if status in ("completed", "failed"):
                run.completed_at = datetime.now(timezone.utc)

            if metrics:
                run.avg_faithfulness = metrics.get("faithfulness")
                run.avg_precision = metrics.get("precision")
                run.avg_recall = metrics.get("recall")
                run.avg_context_precision = metrics.get("context_precision")
                run.avg_answer_relevancy = metrics.get("answer_relevancy")
                run.avg_context_recall = metrics.get("context_recall")

            if error:
                run.error = error

            await session.commit()

    def _map_to_batch_response(self, db_run: EvaluationRunModel) -> EvaluationBatchRunResponse:
        """Map database model to response schema"""

        metrics = None
        if db_run.avg_faithfulness is not None:
            metrics = EvaluationMetricsSchema(
                faithfulness=db_run.avg_faithfulness or 0.0,
                precision=db_run.avg_precision or 0.0,
                recall=db_run.avg_recall or 0.0,
                context_precision=db_run.avg_context_precision or 0.0,
                answer_relevancy=db_run.avg_answer_relevancy or 0.0,
                context_recall=db_run.avg_context_recall,
                latency_ms=None,
            )

        return EvaluationBatchRunResponse(
            id=str(db_run.id),
            name=db_run.name or "",
            status=db_run.status or "unknown",
            num_samples=db_run.num_samples or 0,
            created_at=db_run.created_at.isoformat() if db_run.created_at else "",
            started_at=db_run.started_at.isoformat() if db_run.started_at else None,
            completed_at=db_run.completed_at.isoformat() if db_run.completed_at else None,
            updated_at=db_run.updated_at.isoformat() if db_run.updated_at else None,
            metrics=metrics,
            error=db_run.error,
        )


# Global singleton instance
batch_evaluation_service = BatchEvaluationService()
