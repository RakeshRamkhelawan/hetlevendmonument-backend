"""Unit Tests for Tenant Isolation"""

import gc
import shutil
import tempfile
import time
from pathlib import Path

import pytest

from src.core.knowledge.tenant_vector_manager import TenantVectorManager
from src.core.search.tenant_bm25_manager import TenantBM25Manager


@pytest.mark.unit
@pytest.mark.security
@pytest.mark.multi_tenant
class TestTenantVectorIsolation:
    """Tests for ChromaDB tenant isolation"""

    @pytest.fixture
    def temp_dir(self):
        d = tempfile.mkdtemp()
        yield d
        gc.collect()  # Force garbage collection to release file handles
        for attempt in range(5):
            try:
                shutil.rmtree(d, ignore_errors=True)
                break
            except Exception:
                time.sleep(0.1)

    @pytest.fixture
    def manager(self, temp_dir):
        return TenantVectorManager(persist_directory=temp_dir)

    @pytest.mark.unit
    @pytest.mark.security
    @pytest.mark.multi_tenant
    def test_separate_collections_per_tenant(self, manager):
        """Each tenant gets a unique collection"""
        col1 = manager.get_collection(tenant_id=1)
        col2 = manager.get_collection(tenant_id=2)

        assert col1.name != col2.name
        assert "1" in col1.name
        assert "2" in col2.name

    def test_no_cross_tenant_search(self, manager):
        """Tenant A cannot search Tenant B's documents"""
        # Add to tenant 1
        manager.add_documents(
            tenant_id=1,
            documents=["Secret tenant 1 data"],
            embeddings=[[0.1] * 384],
            ids=["doc1"],
            metadatas=[{"source": "test", "tenant": "1"}],
        )

        # Add to tenant 2
        manager.add_documents(
            tenant_id=2,
            documents=["Secret tenant 2 data"],
            embeddings=[[0.9] * 384],
            ids=["doc2"],
            metadatas=[{"source": "test", "tenant": "2"}],
        )

        # Search tenant 1 - should NOT find tenant 2's docs
        results = manager.search(
            tenant_id=1,
            query_embedding=[0.9] * 384,
            top_k=10,  # More similar to tenant 2's doc
        )

        # Only tenant 1's doc should be returned
        assert "doc1" in str(results)
        assert "doc2" not in str(results)

    def test_delete_only_own_collection(self, manager):
        """Deleting tenant 1 doesn't affect tenant 2"""
        manager.get_collection(tenant_id=1)
        manager.get_collection(tenant_id=2)

        manager.delete_collection(tenant_id=1)

        # Tenant 2 should still exist
        tenants = manager.list_tenants()
        assert 1 not in tenants
        assert 2 in tenants


class TestTenantBM25Isolation:
    """Tests for BM25 tenant isolation"""

    @pytest.fixture
    def temp_dir(self):
        d = tempfile.mkdtemp()
        yield d
        gc.collect()  # Force garbage collection to release file handles
        for attempt in range(5):
            try:
                shutil.rmtree(d, ignore_errors=True)
                break
            except Exception:
                time.sleep(0.1)

    @pytest.fixture
    def manager(self, temp_dir):
        return TenantBM25Manager(index_dir=temp_dir)

    def test_separate_indexes_per_tenant(self, manager):
        """Each tenant gets a unique index file"""
        manager.build_index(1, ["doc1"], ["id1"])
        manager.build_index(2, ["doc2"], ["id2"])

        path1 = manager._get_index_path(1)
        path2 = manager._get_index_path(2)

        assert path1 != path2
        assert path1.exists()
        assert path2.exists()

    def test_no_cross_tenant_search(self, manager):
        """Tenant A cannot search Tenant B's documents"""
        manager.build_index(1, ["apple banana"], ["doc1"])
        manager.build_index(2, ["cherry date"], ["doc2"])

        # Search tenant 1 for "cherry" - should return nothing
        results = manager.search(tenant_id=1, query="cherry", top_k=1)

        assert len(results) == 0 or results[0][1] == 0

    def test_delete_only_own_index(self, manager):
        """Deleting tenant 1's index doesn't affect tenant 2"""
        manager.build_index(1, ["doc1"], ["id1"])
        manager.build_index(2, ["doc2"], ["id2"])

        manager.delete_index(1)

        tenants = manager.list_tenants()
        assert 1 not in tenants
        assert 2 in tenants


class TestCrossManagerIsolation:
    """Integration tests for complete tenant isolation"""

    def test_tenant_data_never_leaks(self):
        """Comprehensive test: no data leakage between tenants"""
        # This test simulates a real-world scenario
        tmpdir = tempfile.mkdtemp()
        try:
            vector_mgr = TenantVectorManager(persist_directory=f"{tmpdir}/vectors")
            bm25_mgr = TenantBM25Manager(index_dir=f"{tmpdir}/bm25")

            # Setup: 3 tenants with unique data
            for tid in [1, 2, 3]:
                secret = f"TOP_SECRET_TENANT_{tid}"
                vector_mgr.add_documents(
                    tenant_id=tid,
                    documents=[secret],
                    embeddings=[[float(tid)] * 384],
                    ids=[f"secret_{tid}"],
                    metadatas=[{"source": "test", "tenant": str(tid)}],
                )
                bm25_mgr.build_index(tid, [secret], [f"secret_{tid}"])

            # Verify: each tenant only sees their own data
            for tid in [1, 2, 3]:
                for other_tid in [1, 2, 3]:
                    if other_tid != tid:
                        # Vector search
                        vresults = vector_mgr.search(
                            tenant_id=tid, query_embedding=[float(other_tid)] * 384
                        )
                        assert f"secret_{other_tid}" not in str(vresults)

                        # BM25 search
                        bresults = bm25_mgr.search(
                            tenant_id=tid, query=f"TENANT_{other_tid}", top_k=1
                        )
                        for doc_id, score in bresults:
                            assert f"secret_{other_tid}" not in doc_id
        finally:
            gc.collect()  # Force garbage collection to release file handles
            for attempt in range(5):
                try:
                    shutil.rmtree(tmpdir, ignore_errors=True)
                    break
                except Exception:
                    time.sleep(0.1)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=src/core"])
