"""
Integration Tests for Evaluation Pipeline

Tests end-to-end evaluation flow including ragchecker, persistence, and quality gates.
"""

import asyncio
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Mock ragchecker to avoid heavy ML imports and Windows mlflow bugs
mock_ragchecker = MagicMock()
mock_ragchecker_container = MagicMock()
sys.modules["ragchecker"] = mock_ragchecker
sys.modules["ragchecker.container"] = mock_ragchecker_container

from src.core.database.database import db_manager
from src.core.evaluation.evaluation_service import (
    EvaluationRun,
    LowQualityResponseError,
    QualityGateConfig,
    evaluation_service,
)
from src.core.models.evaluation_models import EvaluationResult

pytestmark = pytest.mark.skip(
    reason="Evaluation pipeline tests rely on deprecated db_manager initialization path"
)


@pytest.fixture
async def setup_db(postgres_engine):
    """Ensure database schema is ready for integration tests"""
    from src.core.database.database import Base

    async with postgres_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    # Cleanup if needed


class TestEvaluationPipeline:
    @pytest.mark.asyncio
    async def test_full_pipeline_flow(self, setup_db):
        """Verify end-to-end flow: Evaluate -> Persist -> Stats"""
        tenant_id = 555

        # Mock ragchecker response
        mock_eval_results = MagicMock()
        mock_eval_results.metrics = {
            "overall_metrics": {
                "faithfulness": 0.95,
                "precision": 0.88,
                "recall": 0.85,
                "context_precision": 0.92,
            }
        }

        with (
            patch(
                "src.core.evaluation.evaluation_service.asyncio.to_thread",
                return_value=mock_eval_results,
            ),
            patch("src.core.evaluation.evaluation_service.LLMService"),
        ):
            run = await evaluation_service.evaluate_rag_response(
                tenant_id=tenant_id,
                query="Integration Test Query",
                response="High quality response",
                contexts=["Relevant context for test"],
            )

            assert isinstance(run, EvaluationRun)
            assert run.metrics.faithfulness == 0.95
            assert run.tenant_id == tenant_id

            # Verify stats aggregation
            stats = await evaluation_service.get_tenant_stats(tenant_id)
            assert stats["total_runs"] >= 1
            assert stats["avg_faithfulness"] == 0.95

    @pytest.mark.asyncio
    async def test_quality_gate_blocking(self, setup_db):
        """Verify that quality gate correctly blocks low-quality responses"""
        tenant_id = 666

        # Mock a low-quality response (faithfulness < 0.7)
        mock_eval_results = MagicMock()
        mock_eval_results.metrics = {
            "overall_metrics": {"faithfulness": 0.45, "precision": 0.5, "recall": 0.5}
        }

        config = QualityGateConfig(min_faithfulness=0.7, block_on_failure=True)

        with (
            patch(
                "src.core.evaluation.evaluation_service.asyncio.to_thread",
                return_value=mock_eval_results,
            ),
            patch("src.core.evaluation.evaluation_service.LLMService"),
        ):
            with pytest.raises(LowQualityResponseError) as exc_info:
                await evaluation_service.evaluate_rag_response(
                    tenant_id=tenant_id,
                    query="Bad Query",
                    response="Hallucinated response",
                    contexts=["Unrelated context"],
                    quality_config=config,
                )

            assert exc_info.value.error_code == "LOW_QUALITY_RESPONSE"
            assert exc_info.value.status_code == 422

            # CRITICAL: Verify the failure is STILL stored in the DB for auditing
            stats = await evaluation_service.get_tenant_stats(tenant_id)
            assert stats["total_runs"] >= 1
            assert stats["avg_faithfulness"] == 0.45

    @pytest.mark.asyncio
    async def test_run_id_persistence(self, setup_db):
        """Verify specific run retrieval from DB"""
        tenant_id = 777
        mock_eval_results = MagicMock()
        mock_eval_results.metrics = {"overall_metrics": {"faithfulness": 1.0}}

        with (
            patch(
                "src.core.evaluation.evaluation_service.asyncio.to_thread",
                return_value=mock_eval_results,
            ),
            patch("src.core.evaluation.evaluation_service.LLMService"),
        ):
            initial_run = await evaluation_service.evaluate_rag_response(
                tenant_id=tenant_id,
                query="Retrieval Test",
                response="Answer",
                contexts=["Ctx"],
            )

            retrieved_run = await evaluation_service.get_run_results(initial_run.id)
            assert retrieved_run is not None
            assert retrieved_run.query == "Retrieval Test"
            assert retrieved_run.metrics.faithfulness == 1.0
