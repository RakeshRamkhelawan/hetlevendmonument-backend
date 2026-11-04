"""Tests for Art. 15 Accuracy Monitor.

EU AI Act Compliance - Art. 15: Accuracy, robustness, and cybersecurity.
Tests cover the pure-Python drift detection logic and recommendation thresholds.
"""

from __future__ import annotations

import pytest

from src.core.governance.accuracy_monitor import AccuracyMetric, AccuracyMonitor


class TestAccuracyMetricModel:
    """AccuracyMetric SQLAlchemy model structure tests."""

    def test_tablename(self) -> None:
        assert AccuracyMetric.__tablename__ == "governance_accuracy_metrics"

    def test_has_tenant_id_column(self) -> None:
        assert "tenant_id" in AccuracyMetric.__table__.c

    def test_tenant_id_is_not_nullable(self) -> None:
        col = AccuracyMetric.__table__.c["tenant_id"]
        assert col.nullable is False

    def test_has_required_columns(self) -> None:
        cols = set(AccuracyMetric.__table__.c.keys())
        required = {"id", "tenant_id", "agent_name", "success", "recorded_at"}
        assert required.issubset(cols)

    def test_has_optional_columns(self) -> None:
        cols = set(AccuracyMetric.__table__.c.keys())
        assert "confidence_score" in cols
        assert "execution_time_ms" in cols


class TestAccuracyMonitorConstants:
    """AccuracyMonitor drift thresholds and window constants."""

    def test_drift_threshold_is_ten_percent(self) -> None:
        assert AccuracyMonitor.DRIFT_THRESHOLD == 0.10

    def test_baseline_window_is_thirty_days(self) -> None:
        assert AccuracyMonitor.BASELINE_WINDOW_DAYS == 30

    def test_recent_window_is_seven_days(self) -> None:
        assert AccuracyMonitor.RECENT_WINDOW_DAYS == 7

    def test_min_samples_is_twenty(self) -> None:
        assert AccuracyMonitor.MIN_SAMPLES == 20


class TestAccuracyMonitorRecommendation:
    """AccuracyMonitor._recommendation() threshold tests (Art. 15 severity levels)."""

    def test_accuracy_below_70_is_critical(self) -> None:
        assert "CRITICAL" in AccuracyMonitor._recommendation(0.65)

    def test_accuracy_exactly_70_is_not_critical(self) -> None:
        result = AccuracyMonitor._recommendation(0.70)
        assert "CRITICAL" not in result

    def test_accuracy_between_70_and_80_is_high(self) -> None:
        result = AccuracyMonitor._recommendation(0.75)
        assert "HIGH" in result

    def test_accuracy_exactly_80_is_medium(self) -> None:
        result = AccuracyMonitor._recommendation(0.80)
        assert "MEDIUM" in result

    def test_accuracy_above_80_is_medium(self) -> None:
        result = AccuracyMonitor._recommendation(0.95)
        assert "MEDIUM" in result

    def test_accuracy_zero_is_critical(self) -> None:
        result = AccuracyMonitor._recommendation(0.0)
        assert "CRITICAL" in result

    def test_returns_string(self) -> None:
        assert isinstance(AccuracyMonitor._recommendation(0.85), str)


class TestAccuracyMonitorInit:
    """AccuracyMonitor initialization tests."""

    def test_init_requires_db_session(self) -> None:
        """AccuracyMonitor must accept a db session."""
        from unittest.mock import MagicMock

        mock_db = MagicMock()
        monitor = AccuracyMonitor(db=mock_db)
        assert monitor is not None
