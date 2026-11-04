"""
Performance Tests: Reranking Latency Overhead

Measures:
1. Per-document reranking latency (test with 5, 10, 20 docs)
2. Reranking overhead compared to simple sorting
3. Batch vs sequential reranking speedup

Assertions:
- Per-doc latency < 20ms
- Total overhead for 10 docs < 200ms
- Batch processing is faster than sequential
"""

import time
from statistics import mean, stdev
from typing import Any, Dict, List

import pytest

from src.core.search.cross_encoder_reranker import CrossEncoderReranker


class TestRerankingLatency:
    """Measure reranking latency overhead"""

    @pytest.fixture
    def reranker(self):
        """Initialize CrossEncoder reranker"""
        return CrossEncoderReranker()

    @pytest.fixture
    def sample_docs(self) -> List[Dict[str, Any]]:
        """Generate sample documents with realistic content"""
        return [
            {
                "id": f"doc_{i}",
                "content": f"This is document number {i} about cultural heritage preservation. "
                f"It discusses various topics including traditional arts, historical artifacts, "
                f"and community engagement in heritage conservation efforts.",
                "score": 0.9 - i * 0.05,
                "metadata": {"source": f"source_{i}"},
            }
            for i in range(20)
        ]

    def test_rerank_latency_per_document(self, reranker, sample_docs):
        """
        Measure per-document reranking latency

        Tests reranking with 5, 10, and 20 documents to understand
        how latency scales with document count.

        Assertion: Per-doc latency < 20ms
        """
        latencies = []
        query = "test query about cultural heritage and traditional arts"

        for num_docs in [5, 10, 20]:
            docs = sample_docs[:num_docs]

            # Warm up the model (first inference is slower)
            reranker.rerank(query, docs[:2])

            # Measure multiple runs for accuracy
            times = []
            for _ in range(5):
                start = time.perf_counter()
                reranker.rerank(query, docs)
                times.append((time.perf_counter() - start) * 1000)

            avg_time = mean(times)
            std_dev = stdev(times) if len(times) > 1 else 0
            per_doc = avg_time / num_docs
            latencies.append((num_docs, avg_time, per_doc, std_dev))

        # Print detailed performance metrics
        print(f"\n{'='*70}")
        print("Reranking Latency Analysis")
        print(f"{'='*70}")
        print(f"{'Docs':<10} {'Total (ms)':<15} {'Per Doc (ms)':<15} {'Std Dev (ms)':<15}")
        print("-" * 70)
        for num_docs, total, per_doc, std_dev in latencies:
            print(f"{num_docs:<10} {total:<15.1f} {per_doc:<15.2f} {std_dev:<15.2f}")
        print(f"{'='*70}")
        print(f"Query: {query}")
        print("Runs per doc count: 5 (with warmup)")
        print(f"{'='*70}\n")

        # Assert per-doc latency < 20ms
        for num_docs, _, per_doc, _ in latencies:
            assert per_doc < 20, f"Per-doc latency {per_doc:.2f}ms > 20ms for {num_docs} docs"

    def test_rerank_vs_no_rerank_overhead(self, reranker, sample_docs):
        """
        Measure overhead of adding reranking compared to simple sorting

        Compares the time it takes to:
        - Sort documents by score (baseline)
        - Rerank documents using cross-encoder (with overhead)

        Assertion: Total overhead for 10 docs < 200ms
        """
        query = "test query about heritage preservation"
        docs = sample_docs[:10]

        # Baseline: Without reranking (just sorting by original score)
        no_rerank_times = []
        for _ in range(10):
            start = time.perf_counter()
            sorted(docs, key=lambda x: x["score"], reverse=True)
            no_rerank_times.append((time.perf_counter() - start) * 1000)

        # With reranking
        # Warm up first
        reranker.rerank(query, docs[:2])

        with_rerank_times = []
        for _ in range(10):
            start = time.perf_counter()
            reranker.rerank(query, docs)
            with_rerank_times.append((time.perf_counter() - start) * 1000)

        no_rerank_avg = mean(no_rerank_times)
        no_rerank_std = stdev(no_rerank_times)
        with_rerank_avg = mean(with_rerank_times)
        with_rerank_std = stdev(with_rerank_times)
        overhead = with_rerank_avg - no_rerank_avg
        overhead_pct = (overhead / no_rerank_avg) * 100 if no_rerank_avg > 0 else 0

        # Print detailed breakdown
        print(f"\n{'='*70}")
        print("Reranking Overhead Analysis (10 docs)")
        print(f"{'='*70}")
        print(f"{'Method':<25} {'Avg (ms)':<15} {'Std Dev (ms)':<15}")
        print("-" * 70)
        print(f"{'Simple sorting':<25} {no_rerank_avg:<15.2f} {no_rerank_std:<15.2f}")
        print(f"{'With reranking':<25} {with_rerank_avg:<15.2f} {with_rerank_std:<15.2f}")
        print("-" * 70)
        print(f"{'Overhead':<25} {overhead:<15.2f}")
        print(f"{'Overhead %':<25} {overhead_pct:<15.1f}%")
        print(f"{'='*70}")
        print("Runs: 10 (with warmup)")
        print(f"{'='*70}\n")

        # Assert overhead < 200ms for 10 docs
        assert overhead < 200, f"Reranking overhead {overhead:.2f}ms > 200ms"

    def test_batch_vs_sequential_rerank(self, reranker, sample_docs):
        """
        Compare batch vs sequential reranking performance

        Tests whether processing multiple queries in a batch is faster
        than processing them sequentially.

        Assertion: Batch processing should be faster
        """
        queries = [f"query about cultural heritage topic {i}" for i in range(5)]
        docs_per_query = [sample_docs[:10] for _ in queries]

        # Warm up
        reranker.rerank(queries[0], docs_per_query[0][:2])

        # Sequential reranking
        sequential_times = []
        for _ in range(3):
            start = time.perf_counter()
            for q, d in zip(queries, docs_per_query):
                reranker.rerank(q, d)
            sequential_times.append((time.perf_counter() - start) * 1000)

        sequential_time = mean(sequential_times)
        sequential_std = stdev(sequential_times)

        # Batch reranking
        batch_times = []
        for _ in range(3):
            start = time.perf_counter()
            reranker.rerank_batch(queries, docs_per_query)
            batch_times.append((time.perf_counter() - start) * 1000)

        batch_time = mean(batch_times)
        batch_std = stdev(batch_times)
        speedup = sequential_time / batch_time if batch_time > 0 else 0

        # Calculate per-query metrics
        sequential_per_query = sequential_time / len(queries)
        batch_per_query = batch_time / len(queries)

        # Print detailed comparison
        print(f"\n{'='*70}")
        print(f"Batch vs Sequential Reranking ({len(queries)} queries x 10 docs)")
        print(f"{'='*70}")
        print(f"{'Method':<20} {'Total (ms)':<15} {'Per Query (ms)':<15} {'Std Dev (ms)':<15}")
        print("-" * 70)
        print(
            f"{'Sequential':<20} {sequential_time:<15.0f} {sequential_per_query:<15.1f} {sequential_std:<15.2f}"
        )
        print(f"{'Batch':<20} {batch_time:<15.0f} {batch_per_query:<15.1f} {batch_std:<15.2f}")
        print("-" * 70)
        print(f"{'Speedup':<20} {speedup:<15.2f}x")
        print(f"{'Time saved':<20} {sequential_time - batch_time:<15.0f}ms")
        print(f"{'Efficiency gain':<20} {((speedup - 1) * 100):<15.1f}%")
        print(f"{'='*70}")
        print("Runs: 3 per method (with warmup)")
        print(f"Total documents processed: {len(queries) * 10}")
        print(f"{'='*70}\n")

        # Assert batch is faster than sequential
        assert (
            batch_time < sequential_time
        ), f"Batch ({batch_time:.0f}ms) not faster than sequential ({sequential_time:.0f}ms)"

        # Assert at least some speedup (even if marginal)
        assert speedup > 1.0, f"Batch speedup {speedup:.2f}x should be > 1.0x"

    def test_latency_distribution(self, reranker, sample_docs):
        """
        Test latency distribution and percentiles

        Provides comprehensive latency statistics including
        p50, p90, p95, and p99 percentiles.
        """
        query = "test query about heritage artifacts"
        docs = sample_docs[:10]

        # Warm up
        reranker.rerank(query, docs[:2])

        # Collect many samples for distribution analysis
        latencies = []
        for _ in range(50):
            start = time.perf_counter()
            reranker.rerank(query, docs)
            latencies.append((time.perf_counter() - start) * 1000)

        # Sort for percentile calculation
        latencies.sort()

        # Calculate percentiles
        def percentile(data, p):
            idx = int(len(data) * p / 100)
            return data[min(idx, len(data) - 1)]

        p50 = percentile(latencies, 50)
        p90 = percentile(latencies, 90)
        p95 = percentile(latencies, 95)
        p99 = percentile(latencies, 99)
        avg = mean(latencies)
        std = stdev(latencies)
        min_lat = min(latencies)
        max_lat = max(latencies)

        # Print distribution statistics
        print(f"\n{'='*70}")
        print("Reranking Latency Distribution (10 docs)")
        print(f"{'='*70}")
        print(f"{'Metric':<20} {'Value (ms)':<15}")
        print("-" * 70)
        print(f"{'Min':<20} {min_lat:<15.2f}")
        print(f"{'p50 (median)':<20} {p50:<15.2f}")
        print(f"{'p90':<20} {p90:<15.2f}")
        print(f"{'p95':<20} {p95:<15.2f}")
        print(f"{'p99':<20} {p99:<15.2f}")
        print(f"{'Max':<20} {max_lat:<15.2f}")
        print(f"{'Average':<20} {avg:<15.2f}")
        print(f"{'Std Dev':<20} {std:<15.2f}")
        print(f"{'='*70}")
        print(f"Samples: {len(latencies)}")
        print(f"{'='*70}\n")

        # Sanity checks
        assert p95 < 300, f"p95 latency {p95:.2f}ms too high"
        assert p50 < 150, f"p50 latency {p50:.2f}ms too high"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
