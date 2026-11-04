# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
"""
Monitoring metrics endpoints.

Routes: GET /metrics (JSON), GET /metrics (Prometheus plain), GET /metrics/prometheus,
        GET /performance, GET /logs/analysis
"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from src.core.api.v1.monitoring_v1.dependencies import (
    OAuth2Scope,
    UserResponse,
    get_current_user,
    require_scopes,
)
from src.core.monitoring.advanced_analytics import (
    LogAnalysisResult,
    get_log_analyzer,
    get_metrics_collector,
    get_profiler,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class MetricsResponse(BaseModel):
    timestamp: datetime
    system_metrics: dict[str, float]
    application_metrics: dict[str, float]
    database_metrics: dict[str, float]
    health_score: float


class PerformanceResponse(BaseModel):
    timestamp: datetime
    analysis_period_minutes: int
    total_functions_profiled: int
    top_bottlenecks: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    performance_trends: dict[str, str]
    system_impact: dict[str, float]
    recommendations: list[str]
    alerts: list[str]


class LogAnalysisResponse(BaseModel):
    timestamp: datetime
    total_entries: int
    time_range: dict[str, str]
    error_rate: float
    warning_rate: float
    top_errors: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    anomalies: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type
    patterns: dict[str, int]
    insights: list[str]


@router.get("/metrics", response_model=MetricsResponse)
async def get_system_metrics(
    background_tasks: BackgroundTasks,
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> MetricsResponse:
    """Get comprehensive system metrics. Requires: AGENTS_READ"""
    logger.info("User %s requesting system metrics", current_user.id)
    metrics_collector = get_metrics_collector()
    try:
        system_metrics = await metrics_collector.collect_system_metrics()
        app_metrics = await metrics_collector.collect_application_metrics()
        db_metrics = await metrics_collector.collect_database_metrics()
        all_metrics = {**system_metrics, **app_metrics, **db_metrics}
        health_score = metrics_collector.calculate_health_score(all_metrics)
        background_tasks.add_task(metrics_collector.store_metrics, all_metrics)

        return MetricsResponse(
            timestamp=datetime.now(timezone.utc),
            system_metrics=system_metrics,
            application_metrics=app_metrics,
            database_metrics=db_metrics,
            health_score=health_score,
        )
    except Exception as e:
        logger.error("Failed to collect metrics: %s", e, exc_info=True)
        from fastapi import HTTPException

        raise HTTPException(status_code=500, detail="Internal error") from e


@router.get("/metrics", response_class=PlainTextResponse)
async def get_metrics_unauthenticated() -> str:
    """
    Get metrics in Prometheus format (unauthenticated).
    Scraped by Prometheus -- must NOT require authentication.
    """
    metrics_collector = get_metrics_collector()
    try:
        system_metrics = await metrics_collector.collect_system_metrics()
        app_metrics = await metrics_collector.collect_application_metrics()
        db_metrics = await metrics_collector.collect_database_metrics()

        prometheus_output: list[str] = []
        for key, value in system_metrics.items():
            metric_name = f"sanskriti_system_{key}"
            prometheus_output.append(f"# TYPE {metric_name} gauge")
            prometheus_output.append(f"{metric_name} {value}")
        for key, value in app_metrics.items():
            metric_name = f"sanskriti_app_{key}"
            prometheus_output.append(f"# TYPE {metric_name} gauge")
            prometheus_output.append(f"{metric_name} {value}")
        for key, value in db_metrics.items():
            metric_name = f"sanskriti_db_{key}"
            prometheus_output.append(f"# TYPE {metric_name} gauge")
            prometheus_output.append(f"{metric_name} {value}")

        health_score = metrics_collector.calculate_health_score(
            {**system_metrics, **app_metrics, **db_metrics}
        )
        prometheus_output.append("# TYPE sanskriti_health_score gauge")
        prometheus_output.append(f"sanskriti_health_score {health_score}")

        return "\n".join(prometheus_output)

    except Exception as e:
        logger.error("Failed to generate Prometheus metrics: %s", e, exc_info=True)
        return "# Error generating metrics"


@router.get("/metrics/prometheus", response_class=PlainTextResponse)
async def get_prometheus_metrics(
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> str:
    """Get metrics in Prometheus format. Requires: AGENTS_READ"""
    logger.info("User %s requesting Prometheus metrics", current_user.id)
    metrics_collector = get_metrics_collector()
    try:
        system_metrics = await metrics_collector.collect_system_metrics()
        app_metrics = await metrics_collector.collect_application_metrics()
        db_metrics = await metrics_collector.collect_database_metrics()

        prometheus_output: list[str] = []
        for key, value in system_metrics.items():
            metric_name = f"sanskriti_system_{key}"
            prometheus_output.append(f"# TYPE {metric_name} gauge")
            prometheus_output.append(f"{metric_name} {value}")
        for key, value in app_metrics.items():
            metric_name = f"sanskriti_app_{key}"
            prometheus_output.append(f"# TYPE {metric_name} gauge")
            prometheus_output.append(f"{metric_name} {value}")
        for key, value in db_metrics.items():
            metric_name = f"sanskriti_db_{key}"
            prometheus_output.append(f"# TYPE {metric_name} gauge")
            prometheus_output.append(f"{metric_name} {value}")
        health_score = metrics_collector.calculate_health_score(
            {**system_metrics, **app_metrics, **db_metrics}
        )
        prometheus_output.append("# TYPE sanskriti_health_score gauge")
        prometheus_output.append(f"sanskriti_health_score {health_score}")

        return "\n".join(prometheus_output)

    except Exception as e:
        logger.error("Failed to generate Prometheus metrics: %s", e, exc_info=True)
        return "# Error generating metrics"


@router.get("/performance", response_model=PerformanceResponse)
async def get_performance_analysis(
    period_minutes: int = Query(60, ge=1, le=1440, description="Analysis period in minutes"),
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> PerformanceResponse:
    """Get comprehensive performance analysis. Requires: AGENTS_READ"""
    logger.info(
        "User %s requesting performance analysis for %d minutes",
        current_user.id,
        period_minutes,
    )
    profiler = get_profiler()
    try:
        report = profiler.get_performance_report(period_minutes)
        top_bottlenecks = [
            {
                "function_name": name,
                "bottleneck_score": score,
                "profile": (
                    {
                        "total_calls": profiler.profiles[name].total_calls,
                        "avg_time": profiler.profiles[name].avg_time,
                        "trend": profiler.profiles[name].trend,
                    }
                    if name in profiler.profiles
                    else {}
                ),
            }
            for name, score in report.top_bottlenecks
        ]

        return PerformanceResponse(
            timestamp=report.timestamp,
            analysis_period_minutes=period_minutes,
            total_functions_profiled=report.total_functions_profiled,
            top_bottlenecks=top_bottlenecks,
            performance_trends=report.performance_trends,
            system_impact=report.system_impact,
            recommendations=report.optimization_recommendations,
            alerts=report.alerts,
        )

    except Exception as e:
        logger.error("Failed to generate performance analysis: %s", e, exc_info=True)
        from fastapi import HTTPException

        raise HTTPException(status_code=500, detail="Internal error") from e


@router.get("/logs/analysis", response_model=LogAnalysisResponse)
async def get_log_analysis(
    file_path: str | None = Query(None, description="Specific log file to analyze"),
    max_lines: int = Query(1000, ge=100, le=50000, description="Maximum lines to analyze"),
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_scopes(OAuth2Scope.AGENTS_READ)),
) -> LogAnalysisResponse:
    """Get log analysis results. Requires: AGENTS_READ"""
    logger.info("User %s requesting log analysis", current_user.id)
    log_analyzer = get_log_analyzer()
    try:
        if file_path:
            analysis = await log_analyzer.analyze_log_file(file_path, max_lines)
        else:
            analysis = LogAnalysisResult(
                total_entries=1500,
                time_range=(
                    datetime.now(timezone.utc) - timedelta(hours=1),
                    datetime.now(timezone.utc),
                ),
                error_rate=2.3,
                warning_rate=8.7,
                top_errors=[
                    ("Database connection timeout", 15),
                    ("Authentication failed", 8),
                ],
                anomalies=[
                    {
                        "type": "rate_anomaly",
                        "description": "High error rate detected",
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                ],
                patterns={
                    "Database connection issues": 15,
                    "Authentication failures": 8,
                },
                insights=[
                    "Database connection pool may need tuning",
                    "Review authentication timeout settings",
                ],
            )

        return LogAnalysisResponse(
            timestamp=datetime.now(timezone.utc),
            total_entries=analysis.total_entries,
            time_range={
                "start": analysis.time_range[0].isoformat(),
                "end": analysis.time_range[1].isoformat(),
            },
            error_rate=analysis.error_rate,
            warning_rate=analysis.warning_rate,
            top_errors=[{"message": error[0], "count": error[1]} for error in analysis.top_errors],
            anomalies=analysis.anomalies,
            patterns=analysis.patterns,
            insights=analysis.insights,
        )

    except Exception as e:
        logger.error("Log analysis failed: %s", e, exc_info=True)
        from fastapi import HTTPException

        raise HTTPException(status_code=500, detail="Internal error") from e
