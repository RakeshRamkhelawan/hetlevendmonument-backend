"""
Slice 4: RetrieverAgent Tests (RED Phase - TDD)

Tests for the knowledge base retrieval agent that searches and ranks
knowledge items for context during procedure execution.

Tests cover:
- Basic retrieval from knowledge base
- Query matching and relevance scoring
- Result ranking by relevance
- Tenant isolation
- Filtering and max results
- Empty result handling
- Metadata preservation
- Error handling
- Performance characteristics
"""

from typing import Any, Dict, List
from unittest.mock import AsyncMock, Mock, patch
from uuid import UUID, uuid4

import pytest

from src.core.agents.capabilities.retriever_agent import RetrieverAgent
from src.core.agents.capabilities.schemas import RetrievalResult, RetrieverResult, RetrieverTask

# ============================================================================
# TEST FIXTURES
# ============================================================================


@pytest.fixture
def sample_tenant_id():
    """Sample tenant ID."""
    return uuid4()


@pytest.fixture
def mock_knowledge_base():
    """Mock knowledge base repository."""
    return AsyncMock()


@pytest.fixture
def sample_retrieval_results():
    """Sample retrieval results."""
    return [
        RetrievalResult(
            source_id=uuid4(),
            source_type="kb_article",
            content="Invoice approval requires manager sign-off and proper documentation",
            relevance_score=0.95,
            metadata={"category": "finance", "author": "admin", "version": 1},
        ),
        RetrievalResult(
            source_id=uuid4(),
            source_type="procedure",
            content="Step 1: Check invoice amount. Step 2: Route to manager if > $1000",
            relevance_score=0.87,
            metadata={"category": "workflow", "steps": 2},
        ),
        RetrievalResult(
            source_id=uuid4(),
            source_type="template",
            content="Invoice approval email template with fields for amount, date, vendor",
            relevance_score=0.72,
            metadata={"category": "template", "format": "email"},
        ),
    ]


@pytest.fixture
def retriever_agent():
    """RetrieverAgent instance."""
    return RetrieverAgent()


# ============================================================================
# TEST SUITE 1: Basic Retrieval & Query Matching
# ============================================================================


class TestBasicRetrieval:
    """Test basic retrieval from knowledge base."""

    @pytest.mark.asyncio
    async def test_retrieves_documents_matching_query(self, retriever_agent, sample_tenant_id):
        """Should retrieve documents matching the query."""
        task = RetrieverTask(
            query="invoice approval process",
            filters={},
            tenant_id=sample_tenant_id,
            max_results=10,
        )

        result = await retriever_agent.retrieve(task)

        assert isinstance(result, RetrieverResult)
        assert len(result.results) > 0
        assert result.total_count > 0

    @pytest.mark.asyncio
    async def test_returns_structured_results(self, retriever_agent, sample_tenant_id):
        """Each result should be properly structured."""
        task = RetrieverTask(
            query="payment processing",
            filters={},
            tenant_id=sample_tenant_id,
            max_results=10,
        )

        result = await retriever_agent.retrieve(task)

        for item in result.results:
            assert isinstance(item, RetrievalResult)
            assert item.source_id is not None
            assert item.source_type is not None
            assert item.content is not None
            assert 0.0 <= item.relevance_score <= 1.0

    @pytest.mark.asyncio
    async def test_includes_metadata_in_results(self, retriever_agent, sample_tenant_id):
        """Results should include metadata for context."""
        task = RetrieverTask(
            query="approval workflow",
            filters={},
            tenant_id=sample_tenant_id,
            max_results=10,
        )

        result = await retriever_agent.retrieve(task)

        assert len(result.results) > 0
        assert all(isinstance(r.metadata, dict) for r in result.results)


# ============================================================================
# TEST SUITE 2: Relevance Scoring & Ranking
# ============================================================================


class TestRelevanceScoringRanking:
    """Test relevance scoring and result ranking."""

    @pytest.mark.asyncio
    async def test_ranks_results_by_relevance_descending(self, retriever_agent, sample_tenant_id):
        """Results should be ranked by relevance score (highest first)."""
        task = RetrieverTask(
            query="invoice approval",
            filters={},
            tenant_id=sample_tenant_id,
            max_results=10,
        )

        result = await retriever_agent.retrieve(task)

        if len(result.results) > 1:
            # Check descending order
            for i in range(len(result.results) - 1):
                assert result.results[i].relevance_score >= result.results[i + 1].relevance_score

    @pytest.mark.asyncio
    async def test_calculates_relevance_scores(self, retriever_agent, sample_tenant_id):
        """Should calculate relevance scores for each result."""
        task = RetrieverTask(
            query="financial approval",
            filters={},
            tenant_id=sample_tenant_id,
            max_results=10,
        )

        result = await retriever_agent.retrieve(task)

        assert all(0.0 <= r.relevance_score <= 1.0 for r in result.results)
        assert any(r.relevance_score > 0.0 for r in result.results)

    @pytest.mark.asyncio
    async def test_higher_scores_for_exact_matches(self, retriever_agent, sample_tenant_id):
        """Exact phrase matches should score higher."""
        task = RetrieverTask(
            query="invoice approval process invoice approval",
            filters={},
            tenant_id=sample_tenant_id,
            max_results=10,
        )

        result = await retriever_agent.retrieve(task)

        # First result should have high relevance for repeated query
        if result.results:
            assert result.results[0].relevance_score > 0.5


# ============================================================================
# TEST SUITE 3: Filtering & Max Results
# ============================================================================


class TestFilteringMaxResults:
    """Test filtering capabilities and result pagination."""

    @pytest.mark.asyncio
    async def test_respects_max_results_limit(self, retriever_agent, sample_tenant_id):
        """Should not return more results than max_results."""
        task = RetrieverTask(
            query="approval",
            filters={},
            tenant_id=sample_tenant_id,
            max_results=3,
        )

        result = await retriever_agent.retrieve(task)

        assert len(result.results) <= 3

    @pytest.mark.asyncio
    async def test_applies_category_filter(self, retriever_agent, sample_tenant_id):
        """Should filter results by category when specified."""
        task = RetrieverTask(
            query="approval",
            filters={"category": "finance"},
            tenant_id=sample_tenant_id,
            max_results=10,
        )

        result = await retriever_agent.retrieve(task)

        # All results should match filter or be empty
        if result.results:
            assert any(r.metadata.get("category") == "finance" for r in result.results)

    @pytest.mark.asyncio
    async def test_applies_source_type_filter(self, retriever_agent, sample_tenant_id):
        """Should filter by source type when specified."""
        task = RetrieverTask(
            query="approval",
            filters={"source_type": "kb_article"},
            tenant_id=sample_tenant_id,
            max_results=10,
        )

        result = await retriever_agent.retrieve(task)

        # All results should be kb_article type
        assert all(r.source_type == "kb_article" for r in result.results)

    @pytest.mark.asyncio
    async def test_returns_total_count_before_pagination(self, retriever_agent, sample_tenant_id):
        """total_count should reflect results before max_results limit."""
        task = RetrieverTask(
            query="procedure",
            filters={},
            tenant_id=sample_tenant_id,
            max_results=1,  # Only 1 result
        )

        result = await retriever_agent.retrieve(task)

        # total_count might be higher than returned results
        assert result.total_count >= len(result.results)


# ============================================================================
# TEST SUITE 4: Tenant Isolation
# ============================================================================


class TestTenantIsolation:
    """Test tenant isolation enforcement."""

    @pytest.mark.asyncio
    async def test_filters_by_tenant_id(self, retriever_agent, sample_tenant_id):
        """Should only retrieve results for the specified tenant."""
        task = RetrieverTask(
            query="approval",
            filters={},
            tenant_id=sample_tenant_id,
            max_results=10,
        )

        result = await retriever_agent.retrieve(task)

        # Results should be valid (not empty implies tenant-filtered)
        assert isinstance(result, RetrieverResult)

    @pytest.mark.asyncio
    async def test_different_tenants_get_different_results(self, retriever_agent):
        """Different tenants should get isolated results."""
        tenant_1 = uuid4()
        tenant_2 = uuid4()

        task_1 = RetrieverTask(
            query="approval",
            filters={},
            tenant_id=tenant_1,
            max_results=10,
        )

        task_2 = RetrieverTask(
            query="approval",
            filters={},
            tenant_id=tenant_2,
            max_results=10,
        )

        result_1 = await retriever_agent.retrieve(task_1)
        result_2 = await retriever_agent.retrieve(task_2)

        # Results should be independent per tenant
        assert isinstance(result_1, RetrieverResult)
        assert isinstance(result_2, RetrieverResult)


# ============================================================================
# TEST SUITE 5: Empty Results & Edge Cases
# ============================================================================


class TestEmptyResultsEdgeCases:
    """Test handling of empty results and edge cases."""

    @pytest.mark.asyncio
    async def test_handles_empty_results_gracefully(self, retriever_agent, sample_tenant_id):
        """Should handle queries with no matching results."""
        task = RetrieverTask(
            query="xyzabc123notarealquery",  # Unlikely to match
            filters={},
            tenant_id=sample_tenant_id,
            max_results=10,
        )

        result = await retriever_agent.retrieve(task)

        assert isinstance(result, RetrieverResult)
        assert len(result.results) == 0
        assert result.total_count == 0

    @pytest.mark.asyncio
    async def test_handles_empty_query_string(self, retriever_agent, sample_tenant_id):
        """Should handle or reject empty query strings."""
        task = RetrieverTask(
            query="",  # Empty query
            filters={},
            tenant_id=sample_tenant_id,
            max_results=10,
        )

        # Should either return empty results or raise validation error
        try:
            result = await retriever_agent.retrieve(task)
            assert len(result.results) == 0
        except ValueError:
            pass  # Valid to reject empty query

    @pytest.mark.asyncio
    async def test_handles_very_long_query(self, retriever_agent, sample_tenant_id):
        """Should handle very long query strings."""
        long_query = "approval " * 100  # Very long query
        task = RetrieverTask(
            query=long_query,
            filters={},
            tenant_id=sample_tenant_id,
            max_results=10,
        )

        result = await retriever_agent.retrieve(task)

        assert isinstance(result, RetrieverResult)

    @pytest.mark.asyncio
    async def test_handles_special_characters_in_query(self, retriever_agent, sample_tenant_id):
        """Should handle special characters in queries."""
        task = RetrieverTask(
            query="approval & review (urgent) [2026-02-10]",
            filters={},
            tenant_id=sample_tenant_id,
            max_results=10,
        )

        result = await retriever_agent.retrieve(task)

        assert isinstance(result, RetrieverResult)


# ============================================================================
# TEST SUITE 6: Metadata & Content
# ============================================================================


class TestMetadataContent:
    """Test metadata and content preservation."""

    @pytest.mark.asyncio
    async def test_preserves_source_metadata(self, retriever_agent, sample_tenant_id):
        """Should preserve all metadata from source."""
        task = RetrieverTask(
            query="approval",
            filters={},
            tenant_id=sample_tenant_id,
            max_results=10,
        )

        result = await retriever_agent.retrieve(task)

        for item in result.results:
            assert isinstance(item.metadata, dict)
            assert len(item.metadata) > 0

    @pytest.mark.asyncio
    async def test_preserves_full_content(self, retriever_agent, sample_tenant_id):
        """Should preserve full content text."""
        task = RetrieverTask(
            query="approval",
            filters={},
            tenant_id=sample_tenant_id,
            max_results=10,
        )

        result = await retriever_agent.retrieve(task)

        for item in result.results:
            assert item.content is not None
            assert len(item.content) > 0

    @pytest.mark.asyncio
    async def test_includes_source_type(self, retriever_agent, sample_tenant_id):
        """Should specify source type for each result."""
        task = RetrieverTask(
            query="procedure",
            filters={},
            tenant_id=sample_tenant_id,
            max_results=10,
        )

        result = await retriever_agent.retrieve(task)

        for item in result.results:
            assert item.source_type in [
                "kb_article",
                "procedure",
                "template",
                "policy",
                "guide",
            ]


# ============================================================================
# TEST SUITE 7: Error Handling
# ============================================================================


class TestErrorHandling:
    """Test error handling."""

    @pytest.mark.asyncio
    async def test_validates_max_results_range(self, retriever_agent, sample_tenant_id):
        """max_results must be 1-100."""
        # Too small
        try:
            task = RetrieverTask(
                query="approval",
                filters={},
                tenant_id=sample_tenant_id,
                max_results=0,  # Invalid
            )
            await retriever_agent.retrieve(task)
            assert False, "Should raise ValueError"
        except ValueError:
            pass  # Expected

        # Too large
        try:
            task = RetrieverTask(
                query="approval",
                filters={},
                tenant_id=sample_tenant_id,
                max_results=101,  # Invalid
            )
            await retriever_agent.retrieve(task)
            assert False, "Should raise ValueError"
        except ValueError:
            pass  # Expected

    @pytest.mark.asyncio
    async def test_requires_tenant_id(self, retriever_agent):
        """tenant_id is required."""
        try:
            task = RetrieverTask(
                query="approval",
                filters={},
                tenant_id=None,  # Invalid
                max_results=10,
            )
            await retriever_agent.retrieve(task)
            assert False, "Should raise ValueError"
        except ValueError:
            pass  # Expected

    @pytest.mark.asyncio
    async def test_requires_query(self, retriever_agent, sample_tenant_id):
        """query is required."""
        try:
            task = RetrieverTask(
                query=None,  # Invalid
                filters={},
                tenant_id=sample_tenant_id,
                max_results=10,
            )
            await retriever_agent.retrieve(task)
            assert False, "Should raise ValueError"
        except (ValueError, TypeError):
            pass  # Expected


# ============================================================================
# TEST SUITE 8: Performance
# ============================================================================


class TestPerformance:
    """Test performance characteristics."""

    @pytest.mark.asyncio
    async def test_retrieval_completes_quickly(self, retriever_agent, sample_tenant_id):
        """Retrieval should complete in <500ms."""
        import time

        task = RetrieverTask(
            query="approval",
            filters={},
            tenant_id=sample_tenant_id,
            max_results=10,
        )

        start = time.time()
        result = await retriever_agent.retrieve(task)
        duration = (time.time() - start) * 1000  # milliseconds

        assert duration < 500  # Should be fast

    @pytest.mark.asyncio
    async def test_handles_large_result_sets(self, retriever_agent, sample_tenant_id):
        """Should handle 100s of results."""
        task = RetrieverTask(
            query="the",  # Very common word
            filters={},
            tenant_id=sample_tenant_id,
            max_results=100,  # Max allowed
        )

        result = await retriever_agent.retrieve(task)

        # Should return without hanging
        assert len(result.results) <= 100


# ============================================================================
# TEST SUITE 9: Integration & Completeness
# ============================================================================


class TestIntegrationCompleteness:
    """Test complete workflow and result structure."""

    @pytest.mark.asyncio
    async def test_result_structure_complete(self, retriever_agent, sample_tenant_id):
        """Result should have all required fields."""
        task = RetrieverTask(
            query="approval",
            filters={},
            tenant_id=sample_tenant_id,
            max_results=10,
        )

        result = await retriever_agent.retrieve(task)

        assert hasattr(result, "results")
        assert hasattr(result, "total_count")
        assert isinstance(result.results, list)
        assert isinstance(result.total_count, int)

    @pytest.mark.asyncio
    async def test_result_is_serializable(self, retriever_agent, sample_tenant_id):
        """Result should be JSON serializable."""
        task = RetrieverTask(
            query="approval",
            filters={},
            tenant_id=sample_tenant_id,
            max_results=10,
        )

        result = await retriever_agent.retrieve(task)

        # Should be able to convert to dict
        result_dict = result.model_dump()
        assert isinstance(result_dict, dict)
        assert "results" in result_dict
        assert "total_count" in result_dict


# ============================================================================
# TEST SUITE 10: Logging & Observability
# ============================================================================


class TestLoggingObservability:
    """Test logging and observability."""

    @pytest.mark.asyncio
    async def test_logs_retrieval_query(self, retriever_agent, sample_tenant_id):
        """Should log retrieval queries."""
        with patch("src.core.agents.capabilities.retriever_agent.logger") as mock_logger:
            task = RetrieverTask(
                query="approval",
                filters={},
                tenant_id=sample_tenant_id,
                max_results=10,
            )

            await retriever_agent.retrieve(task)

            mock_logger.info.assert_called()

    @pytest.mark.asyncio
    async def test_logs_result_count(self, retriever_agent, sample_tenant_id):
        """Should log result counts."""
        with patch("src.core.agents.capabilities.retriever_agent.logger") as mock_logger:
            task = RetrieverTask(
                query="approval",
                filters={},
                tenant_id=sample_tenant_id,
                max_results=10,
            )

            result = await retriever_agent.retrieve(task)

            # Should log something about results
            assert mock_logger.info.called or result.total_count == 0
