"""Unit tests for prediction domain schemas."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from src.core.api.v1.prediction.schemas import (
    HealthCheckResponse,
    InitializeResponse,
    MetricCollectionResponse,
    MetricsHistoryResponse,
    OptimizationExecutionResponse,
    PredictionRequest,
    PredictionResponse,
    RecentPredictionsResponse,
    SystemStatusResponse,
    TrendsResponse,
)


def test_prediction_request_defaults() -> None:
    req = PredictionRequest()
    assert req.hours_ahead == 24
    assert req.include_optimization_plan is True


def test_prediction_request_custom_values() -> None:
    req = PredictionRequest(hours_ahead=48, prediction_types=["load"])
    assert req.hours_ahead == 48
    assert req.prediction_types == ["load"]


def test_metric_collection_response() -> None:
    resp = MetricCollectionResponse(
        status="ok", metrics_collected=5, timestamp="2026-06-13T00:00:00Z"
    )
    assert resp.status == "ok"


def test_prediction_response_accepts_dict_metadata() -> None:
    resp = PredictionResponse(
        predictions=[{"metric": "cpu", "value": 0.8}],
        optimization_plan={"action": "scale"},
        system_status={"healthy": True},
    )
    assert len(resp.predictions) == 1
    assert resp.optimization_plan is not None


def test_prediction_response_allows_none_plan() -> None:
    resp = PredictionResponse(
        predictions=[{"metric": "cpu"}],
        optimization_plan=None,
        system_status={"healthy": True},
    )
    assert resp.optimization_plan is None


def test_system_status_response() -> None:
    resp = SystemStatusResponse(
        system_status="ok",
        prediction_engine={"version": "1.0"},
        timestamp="2026-06-13T00:00:00Z",
        version="1.0",
    )
    assert resp.prediction_engine["version"] == "1.0"


def test_recent_predictions_response() -> None:
    resp = RecentPredictionsResponse(
        predictions=[{"id": "p1"}],
        total_count=1,
        returned_count=1,
        timestamp="2026-06-13T00:00:00Z",
    )
    assert resp.total_count == 1


def test_metrics_history_response() -> None:
    resp = MetricsHistoryResponse(
        metrics=[{"value": 1.0}],
        count=1,
        time_range_hours=24,
        metric_type_filter="cpu",
        timestamp="2026-06-13T00:00:00Z",
    )
    assert resp.count == 1


def test_trends_response() -> None:
    resp = TrendsResponse(
        trends={"cpu": "up"},
        analysis_period_hours=24,
        total_metrics_analyzed=10,
        trend_summary={"up": 5},
        timestamp="2026-06-13T00:00:00Z",
    )
    assert resp.total_metrics_analyzed == 10


def test_health_check_response() -> None:
    resp = HealthCheckResponse(
        status="ok", prediction_engine="v1", timestamp="2026-06-13T00:00:00Z", version="1.0"
    )
    assert resp.error is None


def test_optimization_execution_response() -> None:
    resp = OptimizationExecutionResponse(
        status="started",
        plan_id="plan-1",
        message="ok",
        estimated_completion="2026-06-13T01:00:00Z",
        timestamp="2026-06-13T00:00:00Z",
    )
    assert resp.plan_id == "plan-1"


def test_initialize_response() -> None:
    resp = InitializeResponse(
        status="ready",
        message="initialized",
        timestamp="2026-06-13T00:00:00Z",
        capabilities=["forecast"],
    )
    assert "forecast" in resp.capabilities
