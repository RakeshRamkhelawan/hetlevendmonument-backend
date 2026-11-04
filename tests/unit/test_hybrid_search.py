"""
Unit Tests for Hybrid Search

Tests fusion methods, normalization, and orchestration.
Target coverage: >= 95%
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.search.hybrid_search import (
    HybridSearchConfig,
    HybridSearchResult,
    _normalize_scores_minmax,
    _normalize_scores_softmax,
    _reciprocal_rank_fusion,
    _weighted_fusion,
    hybrid_search,
)


class TestNormalization:
    """Tests for score normalization functions"""

    def test_minmax_basic(self):
        scores = [1.0, 2.0, 3.0]
        result = _normalize_scores_minmax(scores)
        assert result == [0.0, 0.5, 1.0]

    def test_minmax_identical_scores(self):
        scores = [5.0, 5.0, 5.0]
        result = _normalize_scores_minmax(scores)
        # Should return all 1.0 if max == min
        assert result == [1.0, 1.0, 1.0]

    def test_minmax_empty(self):
        assert _normalize_scores_minmax([]) == []

    def test_softmax_basic(self):
        scores = [1.0, 2.0, 3.0]
        result = _normalize_scores_softmax(scores)
        assert len(result) == 3
        assert abs(sum(result) - 1.0) < 1e-6
        # Higher score should have higher probability
        assert result[2] > result[1] > result[0]


class TestFusionMethods:
    """Tests for RRF and Weighted fusion"""

    def test_rrf_basic(self):
        # doc1 is 1st in vector, 2nd in bm25
        # doc2 is 2nd in vector, 1st in bm25
        vector = [("doc1", {"content": "a"}, 0.9), ("doc2", {"content": "b"}, 0.8)]
        bm25 = [("doc2", {"content": "b"}, 5.0), ("doc1", {"content": "a"}, 3.0)]

        results = _reciprocal_rank_fusion(vector, bm25, k=60)

        assert len(results) == 2
        # doc1 score: 1/(60+1) + 1/(60+2)
        # doc2 score: 1/(60+2) + 1/(60+1)
        # They should be equal
        assert results[0].hybrid_score == results[1].hybrid_score
        assert any(r.document_id == "doc1" for r in results)
        assert any(r.document_id == "doc2" for r in results)

    def test_rrf_boost(self):
        vector = [("doc1", {"content": "a"}, 0.9)]
        bm25 = [("doc2", {"content": "b"}, 5.0)]

        # Vector boost makes doc1 win
        results = _reciprocal_rank_fusion(vector, bm25, k=60, vector_boost=2.0, bm25_boost=1.0)
        doc1_res = next(r for r in results if r.document_id == "doc1")
        doc2_res = next(r for r in results if r.document_id == "doc2")
        assert doc1_res.hybrid_score > doc2_res.hybrid_score

    def test_weighted_fusion_alpha(self):
        vector = [("doc1", {"content": "a"}, 1.0)]  # Normalized will be 1.0
        bm25 = [("doc2", {"content": "b"}, 1.0)]  # Normalized will be 1.0

        # Alpha 1.0 = pure vector
        res_v = _weighted_fusion(vector, bm25, alpha=1.0)
        doc1_v = next(r for r in res_v if r.document_id == "doc1")
        doc2_v = next(r for r in res_v if r.document_id == "doc2")
        assert doc1_v.hybrid_score == 1.0
        assert doc2_v.hybrid_score == 0.0

        # Alpha 0.0 = pure bm25
        res_b = _weighted_fusion(vector, bm25, alpha=0.0)
        doc1_b = next(r for r in res_b if r.document_id == "doc1")
        doc2_b = next(r for r in res_b if r.document_id == "doc2")
        assert doc1_b.hybrid_score == 0.0
        assert doc2_b.hybrid_score == 1.0


class TestHybridSearchOrchestration:
    """Tests for the main hybrid_search function with mocks"""

    @pytest.mark.asyncio
    async def test_hybrid_search_calls_both_engines(self):
        with (
            patch("src.core.search.hybrid_search._vector_search", new_callable=AsyncMock) as mock_v,
            patch("src.core.search.hybrid_search._bm25_search", new_callable=AsyncMock) as mock_b,
        ):
            mock_v.return_value = [("v1", {"content": "vec", "tenant_id": 1}, 0.9)]
            mock_b.return_value = [("b1", {"content": "bm", "tenant_id": 1}, 0.8)]

            results = await hybrid_search(tenant_id=1, query="test", top_k=5)

            assert len(results) == 2
            mock_v.assert_called_once()
            mock_b.assert_called_once()

    @pytest.mark.asyncio
    async def test_hybrid_search_handles_single_engine_failure(self):
        with (
            patch("src.core.search.hybrid_search._vector_search", new_callable=AsyncMock) as mock_v,
            patch("src.core.search.hybrid_search._bm25_search", new_callable=AsyncMock) as mock_b,
        ):
            mock_v.side_effect = Exception("Vector Down")
            mock_b.return_value = [("b1", {"content": "bm", "tenant_id": 1}, 0.8)]

            # Should not raise, just warn and continue with BM25 only
            results = await hybrid_search(tenant_id=1, query="test", top_k=5)

            assert len(results) == 1
            assert results[0].document_id == "b1"

    @pytest.mark.asyncio
    async def test_hybrid_search_raises_on_double_failure(self):
        with (
            patch("src.core.search.hybrid_search._vector_search", new_callable=AsyncMock) as mock_v,
            patch("src.core.search.hybrid_search._bm25_search", new_callable=AsyncMock) as mock_b,
        ):
            mock_v.side_effect = Exception("Vector Down")
            mock_b.side_effect = Exception("BM25 Down")

            with pytest.raises(RuntimeError, match="Both vector and BM25 search failed"):
                await hybrid_search(tenant_id=1, query="test", top_k=5)


class TestHybridSearchConfig:
    """Tests for HybridSearchConfig validation"""

    def test_config_validation(self):
        # Valid config
        config = HybridSearchConfig(fusion_method="rrf", alpha=0.5)
        config.validate()  # Should not raise

        # Invalid method
        with pytest.raises(ValueError, match="Invalid fusion_method"):
            HybridSearchConfig(fusion_method="invalid").validate()

        # Invalid alpha
        with pytest.raises(ValueError, match="Alpha must be in"):
            HybridSearchConfig(alpha=1.5).validate()
