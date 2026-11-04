# tests/unit/test_performance_profiler.py
"""
Unit Tests for Performance Profiler

Task 5.4.1: Performance Optimization
Tests for the performance profiling middleware and utilities.
"""

import asyncio
import time
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.middleware.performance_profiler import (
    CRITICAL_REQUEST_THRESHOLD_MS,
    MAX_LATENCY_SAMPLES,
    SLOW_REQUEST_THRESHOLD_MS,
    VERY_SLOW_REQUEST_THRESHOLD_MS,
    EndpointMetrics,
    PerformanceProfiler,
    PerformanceProfilingMiddleware,
    QueryProfiler,
    get_performance_profiler,
    profile_function,
)


class TestEndpointMetrics:
    """Tests for EndpointMetrics class"""

    def test_init_creates_empty_metrics(self):
        """Test that EndpointMetrics initializes with empty values"""
        metrics = EndpointMetrics(endpoint="/test", method="GET")

        assert metrics.endpoint == "/test"
        assert metrics.method == "GET"
        assert metrics.latencies_ms == []
        assert metrics.request_count == 0
        assert metrics.error_count == 0
        assert metrics.slow_count == 0

    def test_add_latency_increments_count(self):
        """Test that add_latency increments request count"""
        metrics = EndpointMetrics(endpoint="/test", method="GET")

        metrics.add_latency(50.0)
        assert metrics.request_count == 1
        assert len(metrics.latencies_ms) == 1
        assert metrics.latencies_ms[0] == 50.0

    def test_add_latency_tracks_errors(self):
        """Test that add_latency tracks errors"""
        metrics = EndpointMetrics(endpoint="/test", method="GET")

        metrics.add_latency(50.0, is_error=True)
        assert metrics.error_count == 1

        metrics.add_latency(60.0, is_error=False)
        assert metrics.error_count == 1  # Still 1
        assert metrics.request_count == 2

    def test_add_latency_classifies_slow_requests(self):
        """Test that add_latency classifies slow requests correctly"""
        metrics = EndpointMetrics(endpoint="/test", method="GET")

        # Fast request (<200ms)
        metrics.add_latency(100.0)
        assert metrics.slow_count == 0

        # Slow request (200-500ms)
        metrics.add_latency(250.0)
        assert metrics.slow_count == 1

        # Very slow request (500-1000ms)
        metrics.add_latency(750.0)
        assert metrics.very_slow_count == 1

        # Critical request (>1000ms)
        metrics.add_latency(1500.0)
        assert metrics.critical_count == 1

    def test_add_latency_trims_old_samples(self):
        """Test that add_latency trims samples when MAX_LATENCY_SAMPLES exceeded"""
        metrics = EndpointMetrics(endpoint="/test", method="GET")

        # Add more than MAX_LATENCY_SAMPLES
        for i in range(MAX_LATENCY_SAMPLES + 100):
            metrics.add_latency(float(i))

        assert len(metrics.latencies_ms) == MAX_LATENCY_SAMPLES
        # Should keep the latest samples
        assert metrics.latencies_ms[-1] == float(MAX_LATENCY_SAMPLES + 99)

    def test_get_percentiles_empty(self):
        """Test get_percentiles returns zeros for empty metrics"""
        metrics = EndpointMetrics(endpoint="/test", method="GET")

        percentiles = metrics.get_percentiles()
        assert percentiles["p50"] == 0
        assert percentiles["p95"] == 0
        assert percentiles["mean"] == 0

    def test_get_percentiles_calculates_correctly(self):
        """Test get_percentiles calculates percentiles correctly"""
        metrics = EndpointMetrics(endpoint="/test", method="GET")

        # Add 100 samples from 1-100
        for i in range(1, 101):
            metrics.add_latency(float(i))

        percentiles = metrics.get_percentiles()
        # Note: Our implementation uses index-based percentiles, so P50 is around 50-51
        assert 49.0 <= percentiles["p50"] <= 52.0  # Allow small variance
        assert 94.0 <= percentiles["p95"] <= 96.0  # Allow small variance
        assert percentiles["min"] == 1.0
        assert percentiles["max"] == 100.0
        assert 50.0 <= percentiles["mean"] <= 51.0  # ~50.5

    def test_get_summary_includes_all_fields(self):
        """Test get_summary returns all required fields"""
        metrics = EndpointMetrics(endpoint="/test", method="POST")
        metrics.add_latency(150.0)
        metrics.add_latency(250.0)  # Slow
        metrics.add_latency(100.0, is_error=True)

        summary = metrics.get_summary()

        assert summary["endpoint"] == "/test"
        assert summary["method"] == "POST"
        assert summary["request_count"] == 3
        assert summary["error_count"] == 1
        assert summary["slow_count"] == 1
        assert "latency_p95_ms" in summary
        assert "meets_sla" in summary

    def test_meets_sla_is_true_for_fast_endpoints(self):
        """Test meets_sla is true when P95 < 200ms"""
        metrics = EndpointMetrics(endpoint="/test", method="GET")

        for _ in range(100):
            metrics.add_latency(50.0)  # All fast

        summary = metrics.get_summary()
        assert summary["meets_sla"] is True

    def test_meets_sla_is_false_for_slow_endpoints(self):
        """Test meets_sla is false when P95 >= 200ms"""
        metrics = EndpointMetrics(endpoint="/test", method="GET")

        for _ in range(100):
            metrics.add_latency(250.0)  # All slow

        summary = metrics.get_summary()
        assert summary["meets_sla"] is False


class TestPerformanceProfiler:
    """Tests for PerformanceProfiler singleton"""

    @pytest.fixture
    def fresh_profiler(self):
        """Create a fresh profiler instance for testing"""
        profiler = PerformanceProfiler()
        return profiler

    @pytest.mark.asyncio
    async def test_record_request_creates_endpoint(self, fresh_profiler):
        """Test that record_request creates new endpoint metrics"""
        await fresh_profiler.record_request(
            method="GET",
            path="/api/test",
            latency_ms=100.0,
            status_code=200,
        )

        assert len(fresh_profiler.endpoint_metrics) == 1

    @pytest.mark.asyncio
    async def test_record_request_normalizes_ids(self, fresh_profiler):
        """Test that record_request normalizes path IDs"""
        # Record requests with different UUIDs
        await fresh_profiler.record_request(
            method="GET",
            path="/api/users/550e8400-e29b-41d4-a716-446655440000",
            latency_ms=100.0,
            status_code=200,
        )
        await fresh_profiler.record_request(
            method="GET",
            path="/api/users/550e8400-e29b-41d4-a716-446655440001",
            latency_ms=150.0,
            status_code=200,
        )

        # Should be normalized to same endpoint
        assert len(fresh_profiler.endpoint_metrics) == 1
        key = list(fresh_profiler.endpoint_metrics.keys())[0]
        assert "{id}" in key

    @pytest.mark.asyncio
    async def test_record_request_normalizes_numeric_ids(self, fresh_profiler):
        """Test that record_request normalizes numeric path IDs"""
        await fresh_profiler.record_request(
            method="GET",
            path="/api/items/123",
            latency_ms=100.0,
            status_code=200,
        )
        await fresh_profiler.record_request(
            method="GET",
            path="/api/items/456",
            latency_ms=150.0,
            status_code=200,
        )

        # Should be normalized to same endpoint
        assert len(fresh_profiler.endpoint_metrics) == 1

    @pytest.mark.asyncio
    async def test_get_slow_endpoints_filters_correctly(self, fresh_profiler):
        """Test that get_slow_endpoints returns only slow endpoints"""
        # Add a fast endpoint
        for _ in range(10):
            await fresh_profiler.record_request("GET", "/fast", 50.0, 200)

        # Add a slow endpoint
        for _ in range(10):
            await fresh_profiler.record_request("GET", "/slow", 300.0, 200)

        slow = fresh_profiler.get_slow_endpoints()
        assert len(slow) == 1
        assert "slow" in slow[0]["endpoint"]

    @pytest.mark.asyncio
    async def test_get_summary_aggregates_correctly(self, fresh_profiler):
        """Test that get_summary aggregates all metrics"""
        for _ in range(50):
            await fresh_profiler.record_request("GET", "/api/a", 100.0, 200)
        for _ in range(50):
            await fresh_profiler.record_request("POST", "/api/b", 150.0, 500, is_error=True)

        summary = fresh_profiler.get_summary()

        assert summary["total_endpoints"] == 2
        assert summary["total_requests"] == 100
        assert summary["total_errors"] == 50
        assert summary["global_error_rate"] == 0.5

    @pytest.mark.asyncio
    async def test_reset_clears_all_data(self, fresh_profiler):
        """Test that reset clears all metrics"""
        await fresh_profiler.record_request("GET", "/test", 100.0, 200)
        assert len(fresh_profiler.endpoint_metrics) == 1

        fresh_profiler.reset()

        assert len(fresh_profiler.endpoint_metrics) == 0

    def test_get_top_endpoints_by_latency(self, fresh_profiler):
        """Test get_top_endpoints_by_latency returns sorted list"""
        # Add endpoints with different latencies
        fresh_profiler.endpoint_metrics["GET:/fast"] = EndpointMetrics("/fast", "GET")
        fresh_profiler.endpoint_metrics["GET:/fast"].add_latency(50.0)

        fresh_profiler.endpoint_metrics["GET:/slow"] = EndpointMetrics("/slow", "GET")
        fresh_profiler.endpoint_metrics["GET:/slow"].add_latency(500.0)

        fresh_profiler.endpoint_metrics["GET:/medium"] = EndpointMetrics("/medium", "GET")
        fresh_profiler.endpoint_metrics["GET:/medium"].add_latency(200.0)

        top = fresh_profiler.get_top_endpoints_by_latency(limit=2)

        assert len(top) == 2
        assert top[0]["endpoint"] == "/slow"  # Highest first
        assert top[1]["endpoint"] == "/medium"


class TestQueryProfiler:
    """Tests for QueryProfiler class"""

    def test_record_query_adds_to_list(self):
        """Test that record_query adds query to list"""
        profiler = QueryProfiler()

        profiler.record_query("SELECT * FROM users", 50.0)

        assert len(profiler.queries) == 1
        assert profiler.total_query_time_ms == 50.0

    def test_record_query_truncates_long_sql(self):
        """Test that record_query truncates long SQL"""
        profiler = QueryProfiler()

        long_sql = "SELECT " + "a, " * 200 + "FROM table"
        profiler.record_query(long_sql, 10.0)

        assert len(profiler.queries[0]["sql"]) <= 203  # 200 + "..."

    def test_get_summary_empty(self):
        """Test get_summary for empty profiler"""
        profiler = QueryProfiler()

        summary = profiler.get_summary()

        assert summary["query_count"] == 0
        assert summary["total_query_time_ms"] == 0

    def test_get_summary_with_queries(self):
        """Test get_summary with recorded queries"""
        profiler = QueryProfiler()

        profiler.record_query("SELECT 1", 10.0)
        profiler.record_query("SELECT 2", 20.0)
        profiler.record_query("SELECT 3", 100.0)

        summary = profiler.get_summary()

        assert summary["query_count"] == 3
        assert summary["total_query_time_ms"] == 130.0
        assert summary["average_query_time_ms"] == pytest.approx(43.33, rel=0.1)
        assert summary["slowest_query_ms"] == 100.0


class TestProfileFunctionDecorator:
    """Tests for profile_function decorator"""

    @pytest.mark.asyncio
    async def test_profile_async_function(self):
        """Test profile_function decorator on async function"""

        @profile_function("test_async")
        async def slow_async_function():
            await asyncio.sleep(0.01)
            return "done"

        result = await slow_async_function()
        assert result == "done"

    def test_profile_sync_function(self):
        """Test profile_function decorator on sync function"""

        @profile_function("test_sync")
        def slow_sync_function():
            time.sleep(0.01)
            return "done"

        result = slow_sync_function()
        assert result == "done"

    @pytest.mark.asyncio
    async def test_profile_function_preserves_exceptions(self):
        """Test that profile_function preserves exceptions"""

        @profile_function("test_error")
        async def error_function():
            raise ValueError("test error")

        with pytest.raises(ValueError, match="test error"):
            await error_function()


class TestPerformanceProfilingMiddleware:
    """Tests for PerformanceProfilingMiddleware"""

    @pytest.fixture
    def mock_app(self):
        """Create a mock ASGI app"""

        async def app(scope, receive, send):
            pass

        return app

    @pytest.fixture
    def middleware(self, mock_app):
        """Create middleware instance"""
        return PerformanceProfilingMiddleware(mock_app)

    def test_middleware_excludes_health_endpoints(self, middleware):
        """Test that middleware excludes health check endpoints"""
        assert "/health" in middleware.exclude_paths
        assert "/metrics" in middleware.exclude_paths
        assert "/live" in middleware.exclude_paths
        assert "/ready" in middleware.exclude_paths

    @pytest.mark.asyncio
    async def test_middleware_records_request_latency(self, middleware):
        """Test that middleware records request latency"""
        # Create mock request and response
        request = MagicMock()
        request.url.path = "/api/test"
        request.method = "GET"

        async def call_next(req):
            response = MagicMock()
            response.status_code = 200
            return response

        # Reset profiler
        middleware.profiler.reset()

        # Dispatch request
        await middleware.dispatch(request, call_next)

        # Check that request was recorded
        assert len(middleware.profiler.endpoint_metrics) == 1

    @pytest.mark.asyncio
    async def test_middleware_skips_excluded_paths(self, middleware):
        """Test that middleware skips excluded paths"""
        request = MagicMock()
        request.url.path = "/health"
        request.method = "GET"

        async def call_next(req):
            response = MagicMock()
            response.status_code = 200
            return response

        # Reset profiler
        middleware.profiler.reset()

        # Dispatch request
        await middleware.dispatch(request, call_next)

        # Should not record health check
        assert len(middleware.profiler.endpoint_metrics) == 0


class TestGetPerformanceProfiler:
    """Tests for get_performance_profiler function"""

    def test_returns_singleton(self):
        """Test that get_performance_profiler returns singleton"""
        profiler1 = get_performance_profiler()
        profiler2 = get_performance_profiler()

        assert profiler1 is profiler2

    def test_returns_profiler_instance(self):
        """Test that get_performance_profiler returns PerformanceProfiler"""
        profiler = get_performance_profiler()

        assert isinstance(profiler, PerformanceProfiler)
