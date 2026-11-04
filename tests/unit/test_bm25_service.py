"""
Unit Tests for BM25Service

Tests all BM25Service methods with mocked dependencies.
Target coverage: >= 95%
"""

import asyncio
import json
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, mock_open, patch

import pytest

# Import module under test
from src.core.search.bm25_service import BM25Service, bm25_service

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def service():
    """Create fresh BM25Service instance for each test"""
    return BM25Service(index_dir="tests/temp/bm25_indexes")


@pytest.fixture
def sample_documents():
    """Sample documents for testing"""
    return [
        {
            "id": "doc1",
            "content": "Ancient temples of India represent cultural heritage",
        },
        {"id": "doc2", "content": "Mughal architecture features intricate designs"},
        {"id": "doc3", "content": "Traditional dance forms express spiritual devotion"},
        {"id": "doc4", "content": "Sanskrit manuscripts preserve ancient knowledge"},
        {"id": "doc5", "content": "Temple sculptures depict mythological stories"},
    ]


@pytest.fixture
def large_corpus():
    """Large corpus for performance testing"""
    return [
        {
            "id": f"doc_{i}",
            "content": f"Document {i} about cultural heritage topic {i % 10}",
        }
        for i in range(1000)
    ]


# ============================================================================
# INITIALIZATION TESTS
# ============================================================================


class TestBM25ServiceInit:
    """Tests for BM25Service initialization"""

    def test_init_creates_index_directory(self, tmp_path):
        """Verify index directory is created on init"""
        index_dir = tmp_path / "test_indexes"
        service = BM25Service(index_dir=str(index_dir))

        assert index_dir.exists()
        assert service.index_dir == index_dir

    def test_init_with_existing_directory(self, tmp_path):
        """Verify service works with existing directory"""
        index_dir = tmp_path / "existing"
        index_dir.mkdir()

        service = BM25Service(index_dir=str(index_dir))
        assert service.index_dir == index_dir

    def test_init_empty_indexes(self, service):
        """Verify indexes dict is empty on init"""
        assert service.indexes == {}

    def test_global_singleton_exists(self):
        """Verify global bm25_service singleton is available"""
        assert bm25_service is not None
        assert isinstance(bm25_service, BM25Service)


# ============================================================================
# BUILD INDEX TESTS
# ============================================================================


class TestBuildIndex:
    """Tests for build_index() method"""

    @pytest.mark.asyncio
    async def test_build_index_success(self, service, sample_documents):
        """Verify index builds successfully with valid documents"""
        await service.build_index(tenant_id=1, documents=sample_documents, persist=False)

        assert 1 in service.indexes
        # Note: corpora is not stored in memory anymore

    @pytest.mark.asyncio
    async def test_build_index_empty_documents_raises(self, service):
        """Verify ValueError raised for empty documents"""
        with pytest.raises(ValueError, match="empty documents"):
            await service.build_index(tenant_id=1, documents=[], persist=False)

    @pytest.mark.asyncio
    async def test_build_index_missing_content_raises(self, service):
        """Verify ValueError raised for documents without content"""
        invalid_docs = [{"id": "doc1"}]  # Missing 'content' key

        with pytest.raises(ValueError, match="content"):
            await service.build_index(tenant_id=1, documents=invalid_docs, persist=False)

    @pytest.mark.asyncio
    async def test_build_index_with_persistence(self, service, sample_documents, tmp_path):
        """Verify index is persisted to disk"""
        service.index_dir = tmp_path / "indexes"
        service.index_dir.mkdir()

        await service.build_index(tenant_id=1, documents=sample_documents, persist=True)

        index_path = service._get_tenant_index_path(1)
        assert index_path.exists()
        assert (index_path / "metadata.json").exists()

    @pytest.mark.asyncio
    async def test_build_index_tenant_isolation(self, service, sample_documents):
        """Verify separate indexes per tenant"""
        await service.build_index(tenant_id=1, documents=sample_documents[:2], persist=False)
        await service.build_index(tenant_id=2, documents=sample_documents[2:], persist=False)

        assert 1 in service.indexes
        assert 2 in service.indexes


# ============================================================================
# SEARCH TESTS
# ============================================================================


class TestSearch:
    """Tests for search() method"""

    @pytest.mark.asyncio
    async def test_search_returns_results(self, service, sample_documents):
        """Verify search returns relevant results"""
        await service.build_index(tenant_id=1, documents=sample_documents, persist=False)

        results = await service.search(
            tenant_id=1, query="temple architecture", top_k=3, use_cache=False
        )

        assert len(results) <= 3
        assert all(isinstance(r, tuple) for r in results)
        assert all(len(r) == 2 for r in results)  # (doc, score)

    @pytest.mark.asyncio
    async def test_search_scores_descending(self, service, sample_documents):
        """Verify results are sorted by score descending"""
        await service.build_index(tenant_id=1, documents=sample_documents, persist=False)

        results = await service.search(
            tenant_id=1, query="cultural heritage", top_k=5, use_cache=False
        )

        scores = [score for _, score in results]
        assert scores == sorted(scores, reverse=True)

    @pytest.mark.asyncio
    async def test_search_no_index_raises(self, service):
        """Verify ValueError when tenant has no index"""
        with pytest.raises(ValueError, match="Index not loaded"):
            await service.search(tenant_id=999, query="test", auto_load=False, use_cache=False)

    @pytest.mark.asyncio
    async def test_search_tenant_isolation(self, service, sample_documents):
        """Verify search only returns results from correct tenant"""
        await service.build_index(tenant_id=1, documents=sample_documents[:2], persist=False)
        await service.build_index(tenant_id=2, documents=sample_documents[2:], persist=False)

        results1 = await service.search(tenant_id=1, query="temple", top_k=10, use_cache=False)
        results2 = await service.search(tenant_id=2, query="temple", top_k=10, use_cache=False)

        # Verify results content
        # Tenant 1 should have temple/architecture docs
        doc_contents_1 = [doc["content"].lower() for doc, _ in results1]
        assert len(doc_contents_1) > 0
        assert any("temple" in c for c in doc_contents_1)

        # Tenant 2 has dance docs, searching for 'temple' should return docs with 'temple'
        # IF they exist in that tenant. Sample docs 3,4,5:
        # 3: Traditional dance...
        # 4: Sanskrit manuscripts...
        # 5: Temple sculptures...
        # So Tenant 2 DOES have a "temple" doc (doc5).

        doc_contents_2 = [doc["content"].lower() for doc, _ in results2]
        assert len(doc_contents_2) > 0
        assert any("temple" in c for c in doc_contents_2)

        # CRITICAL: Verify NO cross-leakage
        # Tenant 1 results should NOT contain Tenant 2 content
        assert not any("dance" in c for c in doc_contents_1)

        # Tenant 2 results should NOT contain Tenant 1 unique content
        assert not any("mughal" in c for c in doc_contents_2)

    @pytest.mark.asyncio
    async def test_search_with_cache(self, service, sample_documents):
        """Verify caching behavior (mocked Redis)"""
        await service.build_index(tenant_id=1, documents=sample_documents, persist=False)

        with patch("src.core.search.bm25_service.get_redis_client") as mock_redis:
            mock_client = AsyncMock()
            mock_client.get.return_value = None  # Cache miss
            mock_redis.return_value = mock_client

            results = await service.search(tenant_id=1, query="temple", top_k=3, use_cache=True)

            assert len(results) > 0
            mock_client.setex.assert_called_once()  # Results cached


# ============================================================================
# DELETE INDEX TESTS
# ============================================================================


class TestDeleteIndex:
    """Tests for delete_index() method"""

    @pytest.mark.asyncio
    async def test_delete_index_from_memory(self, service, sample_documents):
        """Verify index removed from memory"""
        await service.build_index(tenant_id=1, documents=sample_documents, persist=False)
        assert 1 in service.indexes

        await service.delete_index(tenant_id=1, delete_files=False)

        assert 1 not in service.indexes

    @pytest.mark.asyncio
    async def test_delete_nonexistent_index_no_error(self, service):
        """Verify deleting nonexistent index doesn't raise"""
        await service.delete_index(tenant_id=999, delete_files=False)
        # Should complete without error


# ============================================================================
# STATS TESTS
# ============================================================================


class TestGetStats:
    """Tests for get_stats() method"""

    @pytest.mark.asyncio
    async def test_get_stats_returns_dict(self, service, sample_documents):
        """Verify stats returns dictionary"""
        await service.build_index(tenant_id=1, documents=sample_documents, persist=False)

        stats = service.get_stats(tenant_id=1)

        assert isinstance(stats, dict)
        assert stats["tenant_id"] == 1
        assert stats["in_memory"] is True

    def test_get_stats_no_index_returns_none(self, service):
        """Verify None returned for nonexistent tenant"""
        stats = service.get_stats(tenant_id=999)
        assert stats is None


# ============================================================================
# VALIDATE INDEX TESTS
# ============================================================================


class TestValidateIndex:
    """Tests for validate_index() method"""

    @pytest.mark.asyncio
    async def test_validate_loaded_index(self, service, sample_documents):
        """Verify validation of loaded index"""
        await service.build_index(tenant_id=1, documents=sample_documents, persist=False)

        result = service.validate_index(tenant_id=1)

        assert result["is_valid"] is True
        assert result["tenant_id"] == 1
        assert result["in_memory"] is True

    def test_validate_missing_index(self, service):
        """Verify validation fails for missing index"""
        result = service.validate_index(tenant_id=999)

        assert result["is_valid"] is False
        assert "not loaded" in result["error"].lower()


# ============================================================================
# CACHE INVALIDATION TESTS
# ============================================================================


class TestCacheInvalidation:
    """Tests for invalidate_cache() method"""

    @pytest.mark.asyncio
    async def test_invalidate_cache_all(self, service):
        """Verify cache invalidation for tenant"""
        with patch("src.core.search.bm25_service.get_redis_client") as mock_redis:
            mock_client = AsyncMock()

            # Helper for async iteration
            async def async_gen(match=None):
                for item in [b"key1", b"key2"]:
                    yield item

            # Configure scan_iter to return the async generator
            # scan_iter is NOT async itself, it returns an async iterator
            mock_client.scan_iter = MagicMock(side_effect=async_gen)
            mock_client.delete = AsyncMock(return_value=2)
            mock_redis.return_value = mock_client

            deleted = await service.invalidate_cache(tenant_id=1)

            assert deleted == 2

    @pytest.mark.asyncio
    async def test_invalidate_cache_handles_redis_error(self, service):
        """Verify graceful handling of Redis errors"""
        with patch("src.core.search.bm25_service.get_redis_client") as mock_redis:
            mock_redis.side_effect = Exception("Redis connection failed")

            deleted = await service.invalidate_cache(tenant_id=1)

            assert deleted == 0  # Graceful degradation


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=src/core/search", "--cov-report=term-missing"])
