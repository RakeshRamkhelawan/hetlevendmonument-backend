"""
Unit Tests for CrossEncoderReranker

Tests reranking functionality with mocked models.
Target coverage: >= 95%
"""

import asyncio
import sys

# Mock torch before importing the module - needs proper module structure
import types
from unittest.mock import MagicMock, call, patch

import numpy as np
import pytest

mock_torch = types.ModuleType("torch")
mock_torch.__spec__ = None
mock_cuda = types.ModuleType("torch.cuda")
mock_cuda.is_available = MagicMock(return_value=False)
mock_torch.cuda = mock_cuda
mock_torch.set_num_threads = MagicMock()
mock_torch.Tensor = MagicMock  # Mock Tensor class
mock_torch.nn = MagicMock()  # Mock nn module

_NEPMODULES = {"torch": mock_torch, "torch.cuda": mock_cuda, "torch.nn": mock_torch.nn}

# De module onder test importeert torch LAZY, binnen `_setup_device()`
# (src/core/search/cross_encoder_reranker.py:95). De nepmodule hoeft dus alleen te
# bestaan ZOLANG een test van dit bestand loopt.
#
# Waarom dat verschil telt: tot 2026-09-10 werden deze drie sleutels op MODULEniveau in
# `sys.modules` gezet -- dus al tijdens het collecteren, in elk xdist-werkproces -- en
# pas teruggezet na de laatste test van dit bestand. Met `-n 4` verdeelt pytest-xdist
# per TEST, dus liepen binnen dat venster tests van andere bestanden in hetzelfde
# werkproces. Een test die daar `importlib.util.find_spec("torch")` doet (wat
# transformers doet zodra `sentence_transformers` wordt geimporteerd) kreeg deze
# nepmodule met `__spec__ = None` en viel om met "ValueError: torch.__spec__ is None".
# Gemeten 2026-09-10: exact de faling van
# tests/unit/test_memory_services.py::TestEmbeddingService::test_initialize in de
# volledige selectie, terwijl dat bestand los EN met -n 4 groen is.
#
# `patch.dict` per TEST is de smalle oplossing: in een werkproces loopt nooit meer dan
# een test tegelijk, dus buiten een test is `sys.modules` weer schoon.


@pytest.fixture(autouse=True)
def _torch_alleen_tijdens_deze_test():
    """Zet de nep-torch klaar voor de duur van EEN test en haal hem daarna weg."""
    with patch.dict(sys.modules, _NEPMODULES):
        yield


with patch.dict(sys.modules, _NEPMODULES):
    from src.core.search.cross_encoder_reranker import (
        CrossEncoderReranker,
        RerankResult,
        get_reranker,
    )


class TestRerankResult:
    """Tests for RerankResult dataclass"""

    def test_rerank_result_creation(self):
        """Test RerankResult dataclass instantiation"""
        result = RerankResult(
            doc_id="doc1",
            content="Test content",
            original_score=0.8,
            rerank_score=0.95,
            rank=1,
            metadata={"source": "test"},
        )

        assert result.doc_id == "doc1"
        assert result.content == "Test content"
        assert result.original_score == 0.8
        assert result.rerank_score == 0.95
        assert result.rank == 1
        assert result.metadata == {"source": "test"}

    def test_rerank_result_empty_metadata(self):
        """Test RerankResult with empty metadata"""
        result = RerankResult(
            doc_id="doc2",
            content="Content",
            original_score=0.5,
            rerank_score=0.6,
            rank=2,
            metadata={},
        )

        assert result.metadata == {}


class TestCrossEncoderReranker:
    """Tests for CrossEncoderReranker class"""

    @pytest.fixture
    def mock_cross_encoder(self):
        """Create a mock CrossEncoder model"""
        with patch("src.core.search.cross_encoder_reranker.CrossEncoder") as mock_ce:
            mock_model = MagicMock()
            mock_ce.return_value = mock_model
            yield mock_model

    def test_initialization_default_model(self, mock_cross_encoder):
        """Test reranker initialization with default model"""
        reranker = CrossEncoderReranker()

        assert reranker.model_name == CrossEncoderReranker.DEFAULT_MODEL
        assert reranker.max_length == 512
        assert reranker.model is not None

        # Verify CPU optimization was applied
        mock_torch.set_num_threads.assert_called_with(2)

    def test_initialization_custom_model(self, mock_cross_encoder):
        """Test reranker initialization with custom model name"""
        custom_model = "custom-model-name"
        reranker = CrossEncoderReranker(model_name=custom_model)

        assert reranker.model_name == custom_model

    def test_initialization_custom_max_length(self, mock_cross_encoder):
        """Test reranker initialization with custom max_length"""
        reranker = CrossEncoderReranker(max_length=256)

        assert reranker.max_length == 256

    def test_initialization_with_cuda(self, mock_cross_encoder):
        """Test initialization with CUDA device"""
        # Save original
        orig_available = mock_torch.cuda.is_available.return_value
        orig_set_threads_call_count = mock_torch.set_num_threads.call_count

        # Set CUDA available
        mock_torch.cuda.is_available.return_value = True

        reranker = CrossEncoderReranker(device="cuda")

        # Verify threads not set (call count should not increase)
        # Actually, it still sets threads for CPU even when device is cuda
        # because the check is: if device == "cpu" or not torch.cuda.is_available()
        # So if device="cuda" but cuda is available, it should NOT set threads

        # Restore
        mock_torch.cuda.is_available.return_value = orig_available

    def test_rerank_basic(self, mock_cross_encoder):
        """Test basic reranking with sorting"""
        # Setup mock to return scores
        mock_cross_encoder.predict.return_value = np.array([0.9, 0.7, 0.95])

        reranker = CrossEncoderReranker()

        documents = [
            {"id": "doc1", "content": "First doc", "score": 0.5, "metadata": {"a": 1}},
            {"id": "doc2", "content": "Second doc", "score": 0.6, "metadata": {"b": 2}},
            {"id": "doc3", "content": "Third doc", "score": 0.4, "metadata": {"c": 3}},
        ]

        results = reranker.rerank("test query", documents)

        # Should return 3 results sorted by rerank_score descending
        assert len(results) == 3

        # Verify sorted order
        assert results[0].doc_id == "doc3"  # 0.95
        assert results[0].rerank_score == 0.95
        assert results[0].rank == 1

        assert results[1].doc_id == "doc1"  # 0.9
        assert results[1].rerank_score == 0.9
        assert results[1].rank == 2

        assert results[2].doc_id == "doc2"  # 0.7
        assert results[2].rerank_score == 0.7
        assert results[2].rank == 3

        # Verify original scores preserved
        assert results[0].original_score == 0.4
        assert results[1].original_score == 0.5
        assert results[2].original_score == 0.6

        # Verify metadata preserved
        assert results[0].metadata == {"c": 3}
        assert results[1].metadata == {"a": 1}
        assert results[2].metadata == {"b": 2}

    def test_rerank_top_k(self, mock_cross_encoder):
        """Test reranking with top_k limiting"""
        mock_cross_encoder.predict.return_value = np.array([0.9, 0.7, 0.95, 0.85])

        reranker = CrossEncoderReranker()

        documents = [{"id": f"doc{i}", "content": f"Content {i}", "score": 0.5} for i in range(4)]

        results = reranker.rerank("test query", documents, top_k=2)

        # Should return only top 2
        assert len(results) == 2
        assert results[0].rerank_score == 0.95
        assert results[1].rerank_score == 0.9

    def test_rerank_return_all_with_top_k(self, mock_cross_encoder):
        """Test return_all parameter overrides top_k"""
        mock_cross_encoder.predict.return_value = np.array([0.9, 0.7, 0.95])

        reranker = CrossEncoderReranker()

        documents = [{"id": f"doc{i}", "content": f"Content {i}", "score": 0.5} for i in range(3)]

        results = reranker.rerank("test query", documents, top_k=1, return_all=True)

        # Should return all 3 despite top_k=1
        assert len(results) == 3

    def test_rerank_empty_documents(self, mock_cross_encoder):
        """Test reranking with empty document list"""
        reranker = CrossEncoderReranker()

        results = reranker.rerank("test query", [])

        assert results == []
        # Model should not be called
        mock_cross_encoder.predict.assert_not_called()

    def test_rerank_missing_fields(self, mock_cross_encoder):
        """Test reranking with documents missing optional fields"""
        mock_cross_encoder.predict.return_value = np.array([0.9])

        reranker = CrossEncoderReranker()

        # Document with minimal fields
        documents = [{"content": "Minimal doc"}]

        results = reranker.rerank("test query", documents)

        assert len(results) == 1
        assert results[0].doc_id == "0"  # Default to index
        assert results[0].original_score == 0.0  # Default
        assert results[0].metadata == {}  # Default

    def test_rerank_content_truncation(self, mock_cross_encoder):
        """Test that long content is truncated to max_length"""
        mock_cross_encoder.predict.return_value = np.array([0.9])

        reranker = CrossEncoderReranker(max_length=10)

        long_content = "x" * 100
        documents = [{"id": "doc1", "content": long_content, "score": 0.5}]

        results = reranker.rerank("test query", documents)

        # Verify predict was called with truncated content
        call_args = mock_cross_encoder.predict.call_args[0][0]
        assert len(call_args[0][1]) == 10  # Truncated to max_length

    def test_rerank_preserves_metadata(self, mock_cross_encoder):
        """Test that metadata is preserved correctly"""
        mock_cross_encoder.predict.return_value = np.array([0.9])

        reranker = CrossEncoderReranker()

        complex_metadata = {
            "source": "test",
            "nested": {"key": "value"},
            "list": [1, 2, 3],
        }

        documents = [
            {
                "id": "doc1",
                "content": "Test",
                "score": 0.5,
                "metadata": complex_metadata,
            }
        ]

        results = reranker.rerank("test query", documents)

        assert results[0].metadata == complex_metadata

    def test_rerank_show_progress_bar_false(self, mock_cross_encoder):
        """Test that show_progress_bar=False is passed to model"""
        mock_cross_encoder.predict.return_value = np.array([0.9])

        reranker = CrossEncoderReranker()
        documents = [{"id": "doc1", "content": "Test", "score": 0.5}]

        reranker.rerank("test query", documents)

        # Verify show_progress_bar=False was passed
        mock_cross_encoder.predict.assert_called_once()
        call_kwargs = mock_cross_encoder.predict.call_args[1]
        assert call_kwargs.get("show_progress_bar") is False

    def test_get_score_single_pair(self, mock_cross_encoder):
        """Test get_score method for single query-document pair"""
        mock_cross_encoder.predict.return_value = np.array([0.85])

        reranker = CrossEncoderReranker()

        score = reranker.get_score("test query", "test document")

        assert score == 0.85
        assert isinstance(score, float)

        # Verify model was called with correct pair
        call_args = mock_cross_encoder.predict.call_args[0][0]
        assert call_args == [("test query", "test document")]

    def test_rerank_batch_basic(self, mock_cross_encoder):
        """Test batch reranking with multiple queries"""
        # Return scores for all pairs
        mock_cross_encoder.predict.return_value = np.array([0.9, 0.8, 0.95, 0.75])

        reranker = CrossEncoderReranker()

        queries = ["query1", "query2"]
        documents_per_query = [
            [
                {"id": "q1_doc1", "content": "Q1 Doc1", "score": 0.5},
                {"id": "q1_doc2", "content": "Q1 Doc2", "score": 0.6},
            ],
            [
                {"id": "q2_doc1", "content": "Q2 Doc1", "score": 0.4},
                {"id": "q2_doc2", "content": "Q2 Doc2", "score": 0.7},
            ],
        ]

        results = reranker.rerank_batch(queries, documents_per_query)

        # Should return list of lists
        assert len(results) == 2

        # First query results
        assert len(results[0]) == 2
        assert results[0][0].doc_id == "q1_doc1"  # 0.9 > 0.8
        assert results[0][0].rerank_score == 0.9
        assert results[0][0].rank == 1
        assert results[0][1].doc_id == "q1_doc2"
        assert results[0][1].rank == 2

        # Second query results
        assert len(results[1]) == 2
        assert results[1][0].doc_id == "q2_doc1"  # 0.95 > 0.75
        assert results[1][0].rerank_score == 0.95
        assert results[1][0].rank == 1

    def test_rerank_batch_with_top_k(self, mock_cross_encoder):
        """Test batch reranking with top_k limiting"""
        mock_cross_encoder.predict.return_value = np.array([0.9, 0.8, 0.7])

        reranker = CrossEncoderReranker()

        queries = ["query1"]
        documents_per_query = [
            [{"id": f"doc{i}", "content": f"Doc{i}", "score": 0.5} for i in range(3)]
        ]

        results = reranker.rerank_batch(queries, documents_per_query, top_k=2)

        # Should return only top 2 per query
        assert len(results[0]) == 2
        assert results[0][0].rerank_score == 0.9
        assert results[0][1].rerank_score == 0.8

    def test_rerank_batch_mismatched_lengths(self, mock_cross_encoder):
        """Test batch reranking with mismatched input lengths"""
        reranker = CrossEncoderReranker()

        queries = ["query1", "query2"]
        documents_per_query = [[{"id": "doc1", "content": "Doc1", "score": 0.5}]]

        with pytest.raises(ValueError, match="Queries and documents lists must have same length"):
            reranker.rerank_batch(queries, documents_per_query)

    def test_rerank_batch_empty_queries(self, mock_cross_encoder):
        """Test batch reranking with empty query list"""
        reranker = CrossEncoderReranker()

        results = reranker.rerank_batch([], [])

        assert results == []

    def test_rerank_batch_empty_documents(self, mock_cross_encoder):
        """Test batch reranking with queries but no documents"""
        reranker = CrossEncoderReranker()

        queries = ["query1", "query2"]
        documents_per_query = [[], []]

        results = reranker.rerank_batch(queries, documents_per_query)

        # Should return empty lists for each query
        assert len(results) == 2
        assert results[0] == []
        assert results[1] == []

        # Model should not be called
        mock_cross_encoder.predict.assert_not_called()

    def test_rerank_batch_mixed_empty_documents(self, mock_cross_encoder):
        """Test batch reranking with some queries having no documents"""
        mock_cross_encoder.predict.return_value = np.array([0.9])

        reranker = CrossEncoderReranker()

        queries = ["query1", "query2"]
        documents_per_query = [[{"id": "doc1", "content": "Doc1", "score": 0.5}], []]

        results = reranker.rerank_batch(queries, documents_per_query)

        assert len(results) == 2
        assert len(results[0]) == 1
        assert results[1] == []

    def test_rerank_batch_content_truncation(self, mock_cross_encoder):
        """Test batch reranking truncates long content"""
        mock_cross_encoder.predict.return_value = np.array([0.9])

        reranker = CrossEncoderReranker(max_length=10)

        long_content = "x" * 100
        queries = ["query1"]
        documents_per_query = [[{"id": "doc1", "content": long_content, "score": 0.5}]]

        results = reranker.rerank_batch(queries, documents_per_query)

        # Verify predict was called with truncated content
        call_args = mock_cross_encoder.predict.call_args[0][0]
        assert len(call_args[0][1]) == 10

    def test_rerank_batch_uses_batch_size(self, mock_cross_encoder):
        """Test batch reranking passes batch_size to model"""
        mock_cross_encoder.predict.return_value = np.array([0.9])

        reranker = CrossEncoderReranker()

        queries = ["query1"]
        documents_per_query = [[{"id": "doc1", "content": "Doc1", "score": 0.5}]]

        reranker.rerank_batch(queries, documents_per_query)

        # Verify batch_size=32 was passed
        call_kwargs = mock_cross_encoder.predict.call_args[1]
        assert call_kwargs.get("batch_size") == 32

    @pytest.mark.asyncio
    async def test_rerank_async(self, mock_cross_encoder):
        """Test async rerank wrapper"""
        mock_cross_encoder.predict.return_value = np.array([0.9])

        reranker = CrossEncoderReranker()

        documents = [{"id": "doc1", "content": "Test", "score": 0.5}]

        results = await reranker.rerank_async("test query", documents)

        assert len(results) == 1
        assert results[0].rerank_score == 0.9

    @pytest.mark.asyncio
    async def test_rerank_async_with_top_k(self, mock_cross_encoder):
        """Test async rerank with top_k parameter"""
        mock_cross_encoder.predict.return_value = np.array([0.9, 0.8, 0.7])

        reranker = CrossEncoderReranker()

        documents = [{"id": f"doc{i}", "content": f"Doc{i}", "score": 0.5} for i in range(3)]

        results = await reranker.rerank_async("test query", documents, top_k=2)

        assert len(results) == 2


class TestGetRerankerSingleton:
    """Tests for singleton get_reranker function"""

    def test_get_reranker_returns_instance(self):
        """Test get_reranker returns a CrossEncoderReranker instance"""
        with patch("src.core.search.cross_encoder_reranker.CrossEncoder"):
            # Reset singleton
            import src.core.search.cross_encoder_reranker as reranker_module

            reranker_module._reranker_instance = None

            reranker = get_reranker()

            assert isinstance(reranker, CrossEncoderReranker)

    def test_get_reranker_singleton_pattern(self):
        """Test get_reranker returns same instance on multiple calls"""
        with patch("src.core.search.cross_encoder_reranker.CrossEncoder"):
            # Reset singleton
            import src.core.search.cross_encoder_reranker as reranker_module

            reranker_module._reranker_instance = None

            reranker1 = get_reranker()
            reranker2 = get_reranker()

            # Should be the exact same instance
            assert reranker1 is reranker2

    def test_get_reranker_uses_default_model(self):
        """Test get_reranker uses default model configuration"""
        with patch("src.core.search.cross_encoder_reranker.CrossEncoder"):
            # Reset singleton
            import src.core.search.cross_encoder_reranker as reranker_module

            reranker_module._reranker_instance = None

            reranker = get_reranker()

            assert reranker.model_name == CrossEncoderReranker.DEFAULT_MODEL
            assert reranker.max_length == 512


class TestEdgeCases:
    """Tests for edge cases and error handling"""

    def test_rerank_single_document(self):
        """Test reranking with only one document"""
        with patch("src.core.search.cross_encoder_reranker.CrossEncoder") as mock_ce:
            mock_model = MagicMock()
            mock_ce.return_value = mock_model
            mock_model.predict.return_value = np.array([0.9])

            reranker = CrossEncoderReranker()

            documents = [{"id": "doc1", "content": "Only doc", "score": 0.5}]
            results = reranker.rerank("test query", documents)

            assert len(results) == 1
            assert results[0].rank == 1

    def test_rerank_with_negative_scores(self):
        """Test reranking handles negative scores correctly"""
        with patch("src.core.search.cross_encoder_reranker.CrossEncoder") as mock_ce:
            mock_model = MagicMock()
            mock_ce.return_value = mock_model
            mock_model.predict.return_value = np.array([-0.5, 0.3, -0.8])

            reranker = CrossEncoderReranker()

            documents = [{"id": f"doc{i}", "content": f"Doc{i}", "score": 0.5} for i in range(3)]

            results = reranker.rerank("test query", documents)

            # Should sort correctly: 0.3 > -0.5 > -0.8
            assert results[0].rerank_score == 0.3
            assert results[1].rerank_score == -0.5
            assert results[2].rerank_score == -0.8

    def test_rerank_with_identical_scores(self):
        """Test reranking with identical scores maintains order"""
        with patch("src.core.search.cross_encoder_reranker.CrossEncoder") as mock_ce:
            mock_model = MagicMock()
            mock_ce.return_value = mock_model
            mock_model.predict.return_value = np.array([0.5, 0.5, 0.5])

            reranker = CrossEncoderReranker()

            documents = [{"id": f"doc{i}", "content": f"Doc{i}", "score": 0.5} for i in range(3)]

            results = reranker.rerank("test query", documents)

            # All should have same score but increasing ranks
            assert all(r.rerank_score == 0.5 for r in results)
            assert [r.rank for r in results] == [1, 2, 3]

    def test_rerank_empty_content(self):
        """Test reranking with documents having empty content"""
        with patch("src.core.search.cross_encoder_reranker.CrossEncoder") as mock_ce:
            mock_model = MagicMock()
            mock_ce.return_value = mock_model
            mock_model.predict.return_value = np.array([0.9])

            reranker = CrossEncoderReranker()

            documents = [{"id": "doc1", "content": "", "score": 0.5}]
            results = reranker.rerank("test query", documents)

            assert len(results) == 1
            assert results[0].content == ""

    def test_rerank_top_k_larger_than_results(self):
        """Test top_k larger than number of documents"""
        with patch("src.core.search.cross_encoder_reranker.CrossEncoder") as mock_ce:
            mock_model = MagicMock()
            mock_ce.return_value = mock_model
            mock_model.predict.return_value = np.array([0.9, 0.8])

            reranker = CrossEncoderReranker()

            documents = [{"id": f"doc{i}", "content": f"Doc{i}", "score": 0.5} for i in range(2)]

            results = reranker.rerank("test query", documents, top_k=10)

            # Should return all 2 documents
            assert len(results) == 2

    def test_rerank_top_k_zero(self):
        """Test top_k=0 is treated as 'return all' (0 is falsy in Python)"""
        with patch("src.core.search.cross_encoder_reranker.CrossEncoder") as mock_ce:
            mock_model = MagicMock()
            mock_ce.return_value = mock_model
            mock_model.predict.return_value = np.array([0.9])

            reranker = CrossEncoderReranker()

            documents = [{"id": "doc1", "content": "Doc1", "score": 0.5}]
            results = reranker.rerank("test query", documents, top_k=0)

            # top_k=0 is falsy, so all documents are returned
            assert len(results) == 1
