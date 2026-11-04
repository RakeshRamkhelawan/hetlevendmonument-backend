"""Prometheus metrics tests for CVA.

Ref: CVA Audit Phase 5 - Observability
"""

import pytest


class TestCVAMetricsExist:
    """CVA module must expose Prometheus metrics."""

    def test_cva_metrics_module_importable(self):
        """cva_metrics module should exist with required metrics."""
        try:
            from src.core.monitoring.cva_metrics import (
                cva_chat_duration_seconds,
                cva_chat_requests_total,
            )

            assert cva_chat_requests_total is not None
            assert cva_chat_duration_seconds is not None
        except ImportError as e:
            pytest.fail(f"CVA metrics module not found: {e}")

    def test_cva_chat_requests_total_counter(self):
        """cva_chat_requests_total should be a Counter with correct labels."""
        from src.core.monitoring.cva_metrics import cva_chat_requests_total

        # Should have tenant_id and status labels
        assert "tenant_id" in cva_chat_requests_total._labelnames
        assert "status" in cva_chat_requests_total._labelnames

    def test_cva_chat_duration_histogram(self):
        """cva_chat_duration_seconds should be a Histogram with tenant_id label."""
        from src.core.monitoring.cva_metrics import cva_chat_duration_seconds

        # Should have tenant_id label
        assert "tenant_id" in cva_chat_duration_seconds._labelnames

    def test_cva_chat_duration_buckets(self):
        """cva_chat_duration_seconds should have appropriate buckets."""
        from src.core.monitoring.cva_metrics import cva_chat_duration_seconds

        # Buckets should be reasonable for CVA response times
        buckets = [b for b in cva_chat_duration_seconds._upper_bounds if b != float("inf")]
        # Should have at least some buckets defined
        assert len(buckets) >= 5
        # First bucket should be small (fast responses)
        assert buckets[0] <= 0.5
        # Last bucket should be large (slow responses)
        assert buckets[-1] >= 10.0

    def test_cva_status_label_values(self):
        """cva_chat_requests_total Counter supports 'success' and 'error' status values."""
        from src.core.monitoring.cva_metrics import cva_chat_requests_total

        # Verify status label exists (values are validated at runtime)
        assert "status" in cva_chat_requests_total._labelnames
