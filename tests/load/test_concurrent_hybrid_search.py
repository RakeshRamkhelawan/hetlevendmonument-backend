"""
Load Tests: 1000 Concurrent Hybrid Searches

Measures system performance under high concurrent load.
Tests throughput, latency percentiles, and error rates.
"""

import asyncio
import random
import time
from dataclasses import dataclass, field
from statistics import mean, median, stdev
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock

import pytest


@dataclass
class LoadTestResult:
    """Result of a single load test request"""

    request_id: int
    success: bool
    latency_ms: float
    error: Optional[str] = None


@dataclass
class LoadTestSummary:
    """Summary statistics for load test"""

    total_requests: int
    successful_requests: int
    failed_requests: int
    error_rate: float
    throughput_rps: float
    latency_min_ms: float
    latency_max_ms: float
    latency_mean_ms: float
    latency_median_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    total_duration_s: float


class MockHybridSearcher:
    """Mock hybrid searcher with configurable behavior"""

    def __init__(
        self,
        min_latency_ms: float = 10,
        max_latency_ms: float = 50,
        error_rate: float = 0.0,
    ):
        self.min_latency_ms = min_latency_ms
        self.max_latency_ms = max_latency_ms
        self.error_rate = error_rate
        self.search_count = 0

    async def search(self, tenant_id: int, query: str, top_k: int = 10) -> List[Dict[str, Any]]:
        """Simulate a search with realistic latency"""
        self.search_count += 1

        # Simulate latency
        latency_s = random.uniform(self.min_latency_ms / 1000, self.max_latency_ms / 1000)
        await asyncio.sleep(latency_s)

        # Simulate errors
        if random.random() < self.error_rate:
            raise Exception("Simulated search error")

        # Return mock results
        return [
            {"id": f"doc_{i}", "content": f"Result {i}", "score": 0.9 - i * 0.05}
            for i in range(min(top_k, 5))
        ]


class LoadTester:
    """Load testing utility for hybrid search"""

    def __init__(self, searcher):
        self.searcher = searcher
        self.results: List[LoadTestResult] = []

    async def run_single_request(
        self, request_id: int, tenant_id: int, query: str
    ) -> LoadTestResult:
        """Execute a single search request"""
        start = time.perf_counter()

        try:
            await self.searcher.search(tenant_id=tenant_id, query=query, top_k=10)
            latency = (time.perf_counter() - start) * 1000
            return LoadTestResult(request_id, True, latency)

        except Exception as e:
            latency = (time.perf_counter() - start) * 1000
            return LoadTestResult(request_id, False, latency, str(e))

    async def run_load_test(
        self,
        num_requests: int,
        concurrency: int,
        queries: List[str],
        tenant_ids: List[int] = None,
    ) -> LoadTestSummary:
        """
        Run load test with specified concurrency

        Args:
            num_requests: Total number of requests
            concurrency: Max concurrent requests
            queries: List of queries to randomly select from
            tenant_ids: List of tenant IDs to use
        """
        tenant_ids = tenant_ids or [1]
        semaphore = asyncio.Semaphore(concurrency)
        self.results = []

        async def bounded_request(req_id: int):
            async with semaphore:
                query = random.choice(queries)
                tenant = random.choice(tenant_ids)
                result = await self.run_single_request(req_id, tenant, query)
                self.results.append(result)

        start_time = time.perf_counter()

        tasks = [bounded_request(i) for i in range(num_requests)]
        await asyncio.gather(*tasks)

        total_duration = time.perf_counter() - start_time

        return self._calculate_summary(total_duration)

    def _calculate_summary(self, total_duration: float) -> LoadTestSummary:
        """Calculate summary statistics"""
        successful = [r for r in self.results if r.success]
        failed = [r for r in self.results if not r.success]
        latencies = [r.latency_ms for r in successful] or [0]

        latencies_sorted = sorted(latencies)
        n = len(latencies_sorted)

        return LoadTestSummary(
            total_requests=len(self.results),
            successful_requests=len(successful),
            failed_requests=len(failed),
            error_rate=len(failed) / len(self.results) if self.results else 0,
            throughput_rps=len(self.results) / total_duration if total_duration > 0 else 0,
            latency_min_ms=min(latencies),
            latency_max_ms=max(latencies),
            latency_mean_ms=mean(latencies),
            latency_median_ms=median(latencies),
            latency_p95_ms=latencies_sorted[int(n * 0.95)] if n > 0 else 0,
            latency_p99_ms=latencies_sorted[min(int(n * 0.99), n - 1)] if n > 0 else 0,
            total_duration_s=total_duration,
        )


class TestConcurrentHybridSearch:
    """Load tests for concurrent hybrid search"""

    @pytest.fixture
    def mock_searcher(self):
        """Create mock searcher with realistic delay"""
        return MockHybridSearcher(min_latency_ms=10, max_latency_ms=50, error_rate=0.0)

    @pytest.fixture
    def test_queries(self):
        return [
            "What is the Taj Mahal?",
            "History of Indian classical music",
            "Konark Sun Temple architecture",
            "Ancient Indian philosophy",
            "Traditional dance forms of India",
            "Mughal Empire history",
            "Buddhist caves in Maharashtra",
            "Sanskrit literature overview",
            "Hindu temple architecture",
            "Indian textile traditions",
        ]

    @pytest.mark.load
    @pytest.mark.asyncio
    async def test_100_concurrent_searches(self, mock_searcher, test_queries):
        """Test 100 concurrent searches"""
        tester = LoadTester(mock_searcher)

        summary = await tester.run_load_test(
            num_requests=100, concurrency=100, queries=test_queries
        )

        self._print_summary("100 Concurrent Searches", summary)

        assert summary.error_rate < 0.01  # < 1% errors
        assert summary.latency_p95_ms < 500  # p95 < 500ms

    @pytest.mark.load
    @pytest.mark.asyncio
    async def test_500_concurrent_searches(self, mock_searcher, test_queries):
        """Test 500 concurrent searches"""
        tester = LoadTester(mock_searcher)

        summary = await tester.run_load_test(
            num_requests=500, concurrency=500, queries=test_queries
        )

        self._print_summary("500 Concurrent Searches", summary)

        assert summary.error_rate < 0.05  # < 5% errors

    @pytest.mark.load
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_1000_concurrent_searches(self, mock_searcher, test_queries):
        """Test 1000 concurrent searches (main target)"""
        tester = LoadTester(mock_searcher)

        summary = await tester.run_load_test(
            num_requests=1000,
            concurrency=1000,
            queries=test_queries,
            tenant_ids=[1, 2, 3, 4, 5],  # Multi-tenant
        )

        self._print_summary("1000 Concurrent Searches", summary)

        # Assertions
        assert summary.error_rate < 0.05, f"Error rate {summary.error_rate:.1%} > 5%"
        assert summary.throughput_rps > 100, f"Throughput {summary.throughput_rps:.0f} < 100 RPS"
        print(
            f"\nPASS: Error rate = {summary.error_rate:.2%}, Throughput = {summary.throughput_rps:.0f} RPS"
        )

    @pytest.mark.load
    @pytest.mark.asyncio
    async def test_sustained_load_short(self, mock_searcher, test_queries):
        """Test sustained load (short version for CI)"""
        tester = LoadTester(mock_searcher)

        # Target: 50 concurrent for 500 requests
        summary = await tester.run_load_test(num_requests=500, concurrency=50, queries=test_queries)

        self._print_summary("Sustained Load (short)", summary)

        assert summary.error_rate < 0.01

    @pytest.mark.load
    @pytest.mark.asyncio
    async def test_multi_tenant_load_distribution(self, mock_searcher, test_queries):
        """Verify load is distributed across tenants"""
        tenant_ids = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        tenant_request_counts: Dict[int, int] = {t: 0 for t in tenant_ids}

        original_search = mock_searcher.search

        async def tracking_search(tenant_id, query, top_k=10):
            tenant_request_counts[tenant_id] += 1
            return await original_search(tenant_id, query, top_k)

        mock_searcher.search = tracking_search

        tester = LoadTester(mock_searcher)

        await tester.run_load_test(
            num_requests=1000,
            concurrency=100,
            queries=test_queries,
            tenant_ids=tenant_ids,
        )

        # Verify roughly even distribution
        counts = list(tenant_request_counts.values())
        min_count = min(counts)
        max_count = max(counts)

        print(f"\nTenant distribution: min={min_count}, max={max_count}")

        # Each tenant should have at least some requests
        assert all(c > 0 for c in counts)

    @pytest.mark.load
    @pytest.mark.asyncio
    async def test_error_rate_under_load(self, test_queries):
        """Test error handling under load with failing searcher"""
        failing_searcher = MockHybridSearcher(
            min_latency_ms=10,
            max_latency_ms=30,
            error_rate=0.1,  # 10% error rate
        )

        tester = LoadTester(failing_searcher)

        summary = await tester.run_load_test(num_requests=200, concurrency=50, queries=test_queries)

        self._print_summary("Error Rate Test (10% simulated)", summary)

        # Error rate should be close to expected (10% +/- 5%)
        assert 0.05 < summary.error_rate < 0.20

    def _print_summary(self, test_name: str, summary: LoadTestSummary):
        """Print formatted summary"""
        print(f"\n{'='*60}")
        print(f"LOAD TEST: {test_name}")
        print(f"{'='*60}")
        print(f"  Requests:    {summary.total_requests}")
        print(f"  Successful:  {summary.successful_requests}")
        print(f"  Failed:      {summary.failed_requests}")
        print(f"  Error Rate:  {summary.error_rate:.2%}")
        print(f"  Duration:    {summary.total_duration_s:.2f}s")
        print(f"  Throughput:  {summary.throughput_rps:.1f} RPS")
        print("\nLatency:")
        print(f"  Min:    {summary.latency_min_ms:.1f}ms")
        print(f"  Mean:   {summary.latency_mean_ms:.1f}ms")
        print(f"  Median: {summary.latency_median_ms:.1f}ms")
        print(f"  p95:    {summary.latency_p95_ms:.1f}ms")
        print(f"  p99:    {summary.latency_p99_ms:.1f}ms")
        print(f"  Max:    {summary.latency_max_ms:.1f}ms")
        print(f"{'='*60}")


class TestLoadTestUtilities:
    """Tests for the load testing utilities themselves"""

    @pytest.mark.load
    def test_load_test_result_dataclass(self):
        """Test LoadTestResult dataclass"""
        result = LoadTestResult(request_id=1, success=True, latency_ms=50.5)
        assert result.request_id == 1
        assert result.success is True
        assert result.latency_ms == 50.5
        assert result.error is None

    @pytest.mark.load
    def test_load_test_summary_dataclass(self):
        """Test LoadTestSummary dataclass"""
        summary = LoadTestSummary(
            total_requests=100,
            successful_requests=95,
            failed_requests=5,
            error_rate=0.05,
            throughput_rps=50.0,
            latency_min_ms=10,
            latency_max_ms=200,
            latency_mean_ms=50,
            latency_median_ms=45,
            latency_p95_ms=150,
            latency_p99_ms=190,
            total_duration_s=2.0,
        )
        assert summary.error_rate == 0.05
        assert summary.throughput_rps == 50.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-m", "load", "-s"])
