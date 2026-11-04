"""
Unit Tests for EvaluationService

Verifies RAG evaluation pipeline, metrics mapping, and persistence logic.
Bypasses heavy ML library imports using sys.modules mocking.
"""

import sys
from unittest.mock import AsyncMock, MagicMock

# Mock heavy/broken libraries before they are ever imported
mock_ragchecker = MagicMock()
mock_ragchecker_container = MagicMock()
sys.modules["ragchecker"] = mock_ragchecker
sys.modules["ragchecker.container"] = mock_ragchecker_container

import asyncio
from datetime import datetime
from unittest.mock import patch

import pytest

from src.core.evaluation.evaluation_service import (
    EvaluationMetrics,
    EvaluationRun,
    EvaluationService,
    evaluation_service,
)


class TestEvaluationService:
    @pytest.mark.asyncio
    async def test_initialize_success(self):
        """Verify service initializes correctly with ragchecker"""
        service = EvaluationService()

        # RAGChecker is now a mock from sys.modules
        mock_ragchecker.RAGChecker.return_value = MagicMock()

        success = await service.initialize()
        assert success is True
        assert service._initialized is True
        mock_ragchecker.RAGChecker.assert_called_once()

    @pytest.mark.asyncio
    async def test_evaluate_rag_response_success(self):
        """Verify full evaluation pipeline flow"""
        service = EvaluationService()
        service._initialized = True
        service.checker = MagicMock()

        # Mock ragchecker evaluate result
        mock_eval_results = MagicMock()
        mock_eval_results.metrics = {
            "overall_metrics": {
                "faithfulness": 0.85,
                "precision": 0.9,
                "recall": 0.8,
                "context_precision": 0.95,
                "context_recall": 0.7,
            }
        }

        # Mock database session
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_session.commit = AsyncMock()
        mock_session.refresh = AsyncMock(
            side_effect=lambda x: setattr(x, "id", 123)
            or setattr(x, "created_at", datetime.utcnow())
        )

        with (
            patch(
                "src.core.evaluation.evaluation_service.db_manager.get_session"
            ) as mock_get_session,
            patch(
                "src.core.evaluation.evaluation_service.asyncio.to_thread",
                return_value=mock_eval_results,
            ),
            patch("src.core.services.llm.tenant_deur.TenantTaalmodel"),
        ):
            mock_get_session.return_value.__aenter__.return_value = mock_session

            run = await service.evaluate_rag_response(
                tenant_id=1,
                query="What is the capital of India?",
                response="The capital of India is New Delhi.",
                contexts=["New Delhi is the capital city of India."],
                reference_answer="New Delhi",
            )

            assert isinstance(run, EvaluationRun)
            assert run.id == 123
            assert run.metrics.faithfulness == 0.85
            assert run.metrics.context_precision == 0.95
            mock_session.add.assert_called_once()
            mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_evaluate_rag_response_failure(self):
        """Verify graceful failure when evaluation fails"""
        service = EvaluationService()
        service._initialized = True

        with (
            patch(
                "src.core.evaluation.evaluation_service.asyncio.to_thread",
                side_effect=Exception("LLM Down"),
            ),
            patch("src.core.services.llm.tenant_deur.TenantTaalmodel"),
        ):
            with pytest.raises(RuntimeError, match="Failed to evaluate RAG response"):
                await service.evaluate_rag_response(
                    tenant_id=1, query="fail", response="fail", contexts=["fail"]
                )

    @pytest.mark.asyncio
    async def test_get_tenant_stats_success(self):
        """Verify aggregate statistics calculation from DB"""
        service = EvaluationService()

        mock_stats = {
            "count": 10,
            "avg_faith": 0.8,
            "avg_prec": 0.7,
            "avg_rec": 0.6,
            "avg_ctx_prec": 0.9,
            "avg_ctx_rec": 0.5,
        }

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.one.return_value = mock_stats
        mock_session.execute.return_value = mock_result

        with patch(
            "src.core.evaluation.evaluation_service.db_manager.get_session"
        ) as mock_get_session:
            mock_get_session.return_value.__aenter__.return_value = mock_session

            stats = await service.get_tenant_stats(tenant_id=1)

            assert stats["tenant_id"] == 1
            assert stats["total_runs"] == 10
            assert stats["avg_faithfulness"] == 0.8

    @pytest.mark.asyncio
    async def test_get_tenant_stats_no_data(self):
        """Verify behavior when no evaluation data exists for tenant"""
        service = EvaluationService()

        mock_session = AsyncMock()
        mock_result = MagicMock()
        mock_result.mappings.return_value.one.return_value = {"count": 0}
        mock_session.execute.return_value = mock_result

        with patch(
            "src.core.evaluation.evaluation_service.db_manager.get_session"
        ) as mock_get_session:
            mock_get_session.return_value.__aenter__.return_value = mock_session

            stats = await service.get_tenant_stats(tenant_id=99)
            assert stats["status"] == "no_data"

    @pytest.mark.asyncio
    async def test_custom_llm_wrapper(self):
        """Verify the sync-to-async LLM wrapper works"""
        service = EvaluationService()
        # Initialize to set up the event loop
        await service.initialize()

        mock_resp = {"content": "Answer"}

        import importlib

        modul = importlib.import_module("src.core.evaluation.evaluation_service")

        token = modul._EVALUATIE_TENANT.set(7)
        try:
            with patch.object(
                importlib.import_module("src.core.services.llm.tenant_deur").TenantTaalmodel,
                "generate_response",
                new_callable=AsyncMock,
                return_value=mock_resp,
            ):
                # Test the wrapper - it will use the event loop set during initialize()
                results = service._custom_llm_wrapper(["Prompt 1"])
        finally:
            modul._EVALUATIE_TENANT.reset(token)
        assert len(results) == 1
        assert results[0] == "Answer"

    @pytest.mark.asyncio
    async def test_custom_llm_wrapper_zonder_tenant_is_een_fout(self):
        """Een evaluatie zonder tenant krijgt GEEN platformmodel: het model van een klant is niet te bepalen."""
        service = EvaluationService()
        await service.initialize()

        with pytest.raises(RuntimeError, match="zonder tenant"):
            service._custom_llm_wrapper(["Prompt 1"])
