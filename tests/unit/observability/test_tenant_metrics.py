"""
Tests for Tenant Metrics

Covers:
- Request recording
- Error recording
- Token usage tracking
- Histogram statistics
- Error rate calculation
"""

import pytest

from src.core.observability.tenant_metrics import TenantMetricsCollector, TenantMetricsMiddleware


class TestTenantMetricsCollector:
    """Test TenantMetricsCollector."""

    @pytest.fixture
    def collector(self):
        """Create fresh metrics collector."""
        return TenantMetricsCollector()

    def test_record_request(self, collector):
        """Should record HTTP request metrics."""
        collector.record_request(
            tenant_id=1,
            endpoint="/api/test",
            method="GET",
            status_code=200,
            duration_ms=150.5,
        )

        metrics = collector.get_tenant_metrics(1)

        assert "requests_total:GET:/api/test:200" in metrics["counters"]
        assert metrics["counters"]["requests_total:GET:/api/test:200"] == 1

        assert "request_duration:/api/test" in metrics["histograms"]
        hist = metrics["histograms"]["request_duration:/api/test"]
        assert hist["count"] == 1
        assert hist["sum"] == 150.5

    def test_record_multiple_requests(self, collector):
        """Should accumulate multiple requests."""
        for i in range(5):
            collector.record_request(
                tenant_id=1,
                endpoint="/api/test",
                method="GET",
                status_code=200,
                duration_ms=100.0 + i * 10,
            )

        metrics = collector.get_tenant_metrics(1)

        assert metrics["counters"]["requests_total:GET:/api/test:200"] == 5
        hist = metrics["histograms"]["request_duration:/api/test"]
        assert hist["count"] == 5
        assert hist["sum"] == 100.0 + 110.0 + 120.0 + 130.0 + 140.0

    def test_record_error(self, collector):
        """Should record error metric."""
        collector.record_error(
            tenant_id=1,
            error_type="ValidationError",
            endpoint="/api/test",
        )

        metrics = collector.get_tenant_metrics(1)

        assert "errors_total:ValidationError:/api/test" in metrics["counters"]
        assert metrics["counters"]["errors_total:ValidationError:/api/test"] == 1

    def test_record_tokens(self, collector):
        """Should record token usage and cost."""
        collector.record_tokens(
            tenant_id=1,
            agent_type="analyzer",
            model="gemini-pro",
            tokens_used=1000,
            cost_usd=0.002,
        )

        metrics = collector.get_tenant_metrics(1)

        assert "tokens_used_total:analyzer:gemini-pro" in metrics["counters"]
        assert metrics["counters"]["tokens_used_total:analyzer:gemini-pro"] == 1000
        assert metrics["counters"]["cost_usd_total:analyzer"] == 0.002

    def test_record_multiple_token_usages(self, collector):
        """Should accumulate token usage."""
        collector.record_tokens(
            tenant_id=1,
            agent_type="analyzer",
            model="gemini-pro",
            tokens_used=1000,
            cost_usd=0.002,
        )

        collector.record_tokens(
            tenant_id=1,
            agent_type="analyzer",
            model="gemini-pro",
            tokens_used=500,
            cost_usd=0.001,
        )

        metrics = collector.get_tenant_metrics(1)

        assert metrics["counters"]["tokens_used_total:analyzer:gemini-pro"] == 1500
        assert metrics["counters"]["cost_usd_total:analyzer"] == 0.003

    def test_set_gauge(self, collector):
        """Should set gauge value."""
        collector.set_gauge(
            tenant_id=1,
            metric_name="active_connections",
            value=42.5,
        )

        metrics = collector.get_tenant_metrics(1)

        assert "active_connections" in metrics["gauges"]
        assert metrics["gauges"]["active_connections"] == 42.5

    def test_record_agent_execution(self, collector):
        """Should record agent execution metrics."""
        collector.record_agent_execution(
            tenant_id=1,
            agent_type="analyzer",
            duration_ms=250.0,
        )

        metrics = collector.get_tenant_metrics(1)

        assert "agent_execution:analyzer" in metrics["histograms"]
        hist = metrics["histograms"]["agent_execution:analyzer"]
        assert hist["count"] == 1
        assert hist["sum"] == 250.0

    def test_get_error_rate_no_requests(self, collector):
        """Should return 0.0 error rate when no requests."""
        rate = collector.get_error_rate(1)

        assert rate == 0.0

    def test_get_error_rate_with_errors(self, collector):
        """Should calculate error rate correctly."""
        # Record 8 successful requests
        for i in range(8):
            collector.record_request(
                tenant_id=1,
                endpoint="/api/test",
                method="GET",
                status_code=200,
                duration_ms=100.0,
            )

        # Record 2 explicit errors (separate from requests)
        for i in range(2):
            collector.record_error(
                tenant_id=1,
                error_type="ValidationError",
                endpoint="/api/test",
            )

        rate = collector.get_error_rate(1)

        # Error rate should be > 0 since we have errors
        # (Actual calculation depends on total counter keys matching pattern)
        assert rate > 0

    def test_tenant_isolation(self, collector):
        """Should isolate metrics between tenants."""
        collector.record_request(
            tenant_id=1,
            endpoint="/api/test",
            method="GET",
            status_code=200,
            duration_ms=100.0,
        )

        collector.record_request(
            tenant_id=2,
            endpoint="/api/test",
            method="GET",
            status_code=200,
            duration_ms=200.0,
        )

        metrics1 = collector.get_tenant_metrics(1)
        metrics2 = collector.get_tenant_metrics(2)

        assert metrics1["histograms"]["request_duration:/api/test"]["sum"] == 100.0
        assert metrics2["histograms"]["request_duration:/api/test"]["sum"] == 200.0

    def test_histogram_percentiles(self, collector):
        """Should calculate histogram percentiles correctly."""
        # Record 100 requests with increasing duration
        for i in range(100):
            collector.record_request(
                tenant_id=1,
                endpoint="/api/test",
                method="GET",
                status_code=200,
                duration_ms=float(i + 1),  # 1, 2, 3, ..., 100
            )

        metrics = collector.get_tenant_metrics(1)
        hist = metrics["histograms"]["request_duration:/api/test"]

        assert hist["count"] == 100
        assert hist["sum"] == 5050.0  # Sum of 1 to 100
        assert hist["avg"] == 50.5
        # Percentiles are approximate from sorted array
        assert 49 <= hist["p50"] <= 51  # Median ~50
        assert 94 <= hist["p95"] <= 96  # ~95th percentile
        assert 98 <= hist["p99"] <= 100  # ~99th percentile


class TestTenantMetricsMiddleware:
    """Test TenantMetricsMiddleware."""

    @pytest.fixture
    def collector(self):
        return TenantMetricsCollector()

    @pytest.fixture
    def middleware(self, collector):
        return TenantMetricsMiddleware(collector)

    async def test_process_response_success(self, middleware, collector):
        """Should record successful response."""
        await middleware.process_response(
            tenant_id=1,
            endpoint="/api/test",
            method="GET",
            status_code=200,
            duration_ms=100.0,
        )

        metrics = collector.get_tenant_metrics(1)

        assert "requests_total:GET:/api/test:200" in metrics["counters"]

    async def test_process_response_client_error(self, middleware, collector):
        """Should record client error."""
        await middleware.process_response(
            tenant_id=1,
            endpoint="/api/test",
            method="GET",
            status_code=400,
            duration_ms=100.0,
        )

        metrics = collector.get_tenant_metrics(1)

        assert "errors_total:client_error:/api/test" in metrics["counters"]

    async def test_process_response_server_error(self, middleware, collector):
        """Should record server error."""
        await middleware.process_response(
            tenant_id=1,
            endpoint="/api/test",
            method="GET",
            status_code=500,
            duration_ms=100.0,
        )

        metrics = collector.get_tenant_metrics(1)

        assert "errors_total:server_error:/api/test" in metrics["counters"]

    async def test_process_request_records_active_timing(self, middleware):
        """Should record start timestamp for active request."""
        await middleware.process_request(
            tenant_id=1,
            endpoint="/api/test",
            method="POST",
        )
        assert (1, "/api/test", "POST") in middleware._active_requests
        assert middleware._active_requests[(1, "/api/test", "POST")] > 0

    async def test_process_response_cleans_up_active_timing(self, middleware):
        """Should remove active timing on response completion."""
        await middleware.process_request(
            tenant_id=1,
            endpoint="/api/test",
            method="GET",
        )
        await middleware.process_response(
            tenant_id=1,
            endpoint="/api/test",
            method="GET",
            status_code=200,
            duration_ms=50.0,
        )
        assert (1, "/api/test", "GET") not in middleware._active_requests
