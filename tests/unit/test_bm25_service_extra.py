"""
Unit tests for BM25Service extra functionality (rebuild, integrity, export)
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.search.bm25_service import BM25Service

# ============================================================================
# REBUILD INDEX TESTS
# ============================================================================


class TestRebuildIndex:
    """Tests for rebuild_index() method"""

    @pytest.fixture
    def service(self):
        """Create fresh BM25Service instance for each test"""
        return BM25Service(index_dir="tests/temp/bm25_indexes")

    @pytest.fixture
    def sample_documents(self):
        return [
            {"id": "doc1", "content": "Content 1"},
            {"id": "doc2", "content": "Content 2"},
            {"id": "doc3", "content": "Content 3"},
            {"id": "doc4", "content": "Content 4"},
            {"id": "doc5", "content": "Content 5"},
        ]

    @pytest.mark.asyncio
    async def test_rebuild_index_updates_content(self, service, sample_documents):
        """Verify rebuild replaces existing index"""
        # Initial build
        await service.build_index(tenant_id=1, documents=sample_documents[:1], persist=False)
        assert len(service.indexes[1].corpus) == 1

        # Rebuild with more docs
        await service.rebuild_index(tenant_id=1, documents=sample_documents, persist=False)
        assert len(service.indexes[1].corpus) == 5


# ============================================================================
# LOAD INDEX ERROR TESTS
# ============================================================================


class TestLoadIndexErrors:
    """Tests for load_index failure modes"""

    @pytest.fixture
    def service(self):
        return BM25Service(index_dir="tests/temp/bm25_indexes")

    @pytest.mark.asyncio
    async def test_load_index_file_not_found(self, service):
        """Verify load returns False if index missing"""
        loaded = await service.load_index(tenant_id=999)
        assert loaded is False

    @pytest.mark.asyncio
    async def test_load_index_corrupted(self, service, tmp_path):
        """Verify load fails gracefully on corruption"""
        service.index_dir = tmp_path / "corrupt_indexes"
        service.index_dir.mkdir()

        # Create invalid index file
        idx_path = service._get_tenant_index_path(1)
        idx_path.mkdir()
        (idx_path / "bm25_index.pkl").touch()  # Empty file

        loaded = await service.load_index(tenant_id=1)
        assert loaded is False


# ============================================================================
# INTEGRITY CHECK TESTS
# ============================================================================


class TestIntegrityCheck:
    """Tests for check_index_integrity"""

    @pytest.fixture
    def service(self):
        return BM25Service(index_dir="tests/temp/bm25_indexes")

    @pytest.mark.asyncio
    async def test_integrity_missing_directory(self, service):
        result = await service.check_index_integrity(999)
        assert result["is_valid"] is False
        assert "Directory missing" in result["errors"][0]

    @pytest.mark.asyncio
    async def test_repair_index_success(self, service):
        """Verify repair rebuilds the index"""
        sample_documents = [{"id": "1", "content": "test"}]
        with patch.object(service, "rebuild_index", new_callable=AsyncMock) as mock_rebuild:
            success = await service.repair_index(1, sample_documents)
            assert success is True
            mock_rebuild.assert_called_once()

    @pytest.mark.asyncio
    async def test_repair_index_failure(self, service):
        """Verify repair handles errors"""
        sample_documents = [{"id": "1", "content": "test"}]
        with patch.object(service, "rebuild_index", side_effect=Exception("Fail")):
            success = await service.repair_index(1, sample_documents)
            assert success is False


# ============================================================================
# EXPORT/IMPORT TESTS
# ============================================================================


class TestExportImport:
    """Tests for backup functionality"""

    @pytest.fixture
    def service(self):
        return BM25Service(index_dir="tests/temp/bm25_indexes")

    @pytest.mark.asyncio
    async def test_export_index_missing(self, service):
        """Verify export fails if index missing"""
        success = await service.export_index(999, "backup.tar.gz")
        assert success is False

    @pytest.mark.asyncio
    async def test_import_index_failure(self, service):
        """Verify import handles errors"""
        success = await service.import_index(1, "nonexistent.tar.gz")
        assert success is False
