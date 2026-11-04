"""Performance Tests: Multi-Tenant Parallel Search"""

import asyncio
import shutil
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from statistics import mean, stdev
from typing import List

import pytest

from src.core.knowledge.tenant_vector_manager import TenantVectorManager
from src.core.search.tenant_bm25_manager import TenantBM25Manager


class TestParallelTenantSearch:
    """Benchmark parallel search across multiple tenants"""

    NUM_TENANTS = 10
    DOCS_PER_TENANT = 1000
    QUERIES_PER_TENANT = 10

    @pytest.fixture(scope="class")
    def temp_dir(self):
        d = tempfile.mkdtemp()
        yield d
        shutil.rmtree(d)

    @pytest.fixture(scope="class")
    def vector_manager(self, temp_dir):
        mgr = TenantVectorManager(persist_directory=f"{temp_dir}/vectors")
        # Populate with test data
        for tid in range(1, self.NUM_TENANTS + 1):
            docs = [f"Document {i} for tenant {tid}" for i in range(self.DOCS_PER_TENANT)]
            embeddings = [[float(tid) / 10 + i / 10000] * 384 for i in range(self.DOCS_PER_TENANT)]
            ids = [f"t{tid}_doc{i}" for i in range(self.DOCS_PER_TENANT)]
            mgr.add_documents(tid, docs, embeddings, ids)
        return mgr

    @pytest.fixture(scope="class")
    def bm25_manager(self, temp_dir):
        mgr = TenantBM25Manager(index_dir=f"{temp_dir}/bm25")
        for tid in range(1, self.NUM_TENANTS + 1):
            docs = [f"Document {i} for tenant {tid}" for i in range(self.DOCS_PER_TENANT)]
            ids = [f"t{tid}_doc{i}" for i in range(self.DOCS_PER_TENANT)]
            mgr.build_index(tid, docs, ids)
        return mgr

    def test_sequential_vs_parallel_vector_search(self, vector_manager):
        """Compare sequential vs parallel vector search"""
        query_embedding = [0.5] * 384

        # Sequential
        start = time.perf_counter()
        for tid in range(1, self.NUM_TENANTS + 1):
            for _ in range(self.QUERIES_PER_TENANT):
                vector_manager.search(tid, query_embedding, top_k=10)
        sequential_time = time.perf_counter() - start

        # Parallel with ThreadPoolExecutor
        def search_tenant(tid):
            results = []
            for _ in range(self.QUERIES_PER_TENANT):
                results.append(vector_manager.search(tid, query_embedding, top_k=10))
            return results

        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=self.NUM_TENANTS) as executor:
            list(executor.map(search_tenant, range(1, self.NUM_TENANTS + 1)))
        parallel_time = time.perf_counter() - start

        total_queries = self.NUM_TENANTS * self.QUERIES_PER_TENANT

        print(f"\n{'='*60}")
        print(f"Vector Search: {total_queries} queries across {self.NUM_TENANTS} tenants")
        print(
            f"  Sequential: {sequential_time*1000:.0f}ms ({sequential_time/total_queries*1000:.1f}ms/query)"
        )
        print(
            f"  Parallel:   {parallel_time*1000:.0f}ms ({parallel_time/total_queries*1000:.1f}ms/query)"
        )
        print(f"  Speedup:    {sequential_time/parallel_time:.2f}x")
        print(f"{'='*60}")

        # Parallel should be faster
        assert parallel_time < sequential_time

    def test_sequential_vs_parallel_bm25_search(self, bm25_manager):
        """Compare sequential vs parallel BM25 search"""
        query = "Document tenant"

        # Sequential
        start = time.perf_counter()
        for tid in range(1, self.NUM_TENANTS + 1):
            for _ in range(self.QUERIES_PER_TENANT):
                bm25_manager.search(tid, query, top_k=10)
        sequential_time = time.perf_counter() - start

        # Parallel
        def search_tenant(tid):
            return [
                bm25_manager.search(tid, query, top_k=10) for _ in range(self.QUERIES_PER_TENANT)
            ]

        start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=self.NUM_TENANTS) as executor:
            list(executor.map(search_tenant, range(1, self.NUM_TENANTS + 1)))
        parallel_time = time.perf_counter() - start

        total_queries = self.NUM_TENANTS * self.QUERIES_PER_TENANT

        print(f"\n{'='*60}")
        print(f"BM25 Search: {total_queries} queries across {self.NUM_TENANTS} tenants")
        print(f"  Sequential: {sequential_time*1000:.0f}ms")
        print(f"  Parallel:   {parallel_time*1000:.0f}ms")
        print(f"  Speedup:    {sequential_time/parallel_time:.2f}x")
        print(f"{'='*60}")

    def test_p95_latency_under_100ms(self, vector_manager, bm25_manager):
        """p95 latency should be under 100ms per query"""
        latencies = []
        query_embedding = [0.5] * 384
        query = "Document"

        for tid in range(1, self.NUM_TENANTS + 1):
            for _ in range(self.QUERIES_PER_TENANT):
                start = time.perf_counter()
                vector_manager.search(tid, query_embedding, top_k=10)
                bm25_manager.search(tid, query, top_k=10)
                latencies.append((time.perf_counter() - start) * 1000)

        latencies.sort()
        p50 = latencies[len(latencies) // 2]
        p95 = latencies[int(len(latencies) * 0.95)]
        p99 = latencies[int(len(latencies) * 0.99)]

        print(f"\n{'='*60}")
        print("Latency Distribution (vector + bm25 combined)")
        print(f"  p50: {p50:.1f}ms")
        print(f"  p95: {p95:.1f}ms")
        print(f"  p99: {p99:.1f}ms")
        print(f"{'='*60}")

        # p95 should be under 100ms
        assert p95 < 100, f"p95 latency {p95}ms exceeds 100ms"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
