# api/v1/endpoints/performance.py
"""
Performance Metrics API Endpoints

Task 5.4.1: Performance Optimization
- Exposes profiling data via REST API
- Provides endpoints for monitoring P95 latency
- Identifies slow endpoints for optimization
"""

from datetime import datetime, timezone
from typing import Any, cast

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from src.core.auth.auth_service import UserResponse
from src.core.auth.dependencies import get_current_user
from src.core.middleware.performance_profiler import (
    SLOW_REQUEST_THRESHOLD_MS,
    get_performance_profiler,
)

router = APIRouter(prefix="/performance", tags=["performance"])


# Response Models
class LatencyPercentiles(BaseModel):
    """Latency percentile data"""

    p50: float
    p90: float
    p95: float
    p99: float
    mean: float
    min_ms: float
    max_ms: float


class EndpointMetricsResponse(BaseModel):
    """Metrics for a single endpoint"""

    endpoint: str
    method: str
    request_count: int
    error_count: int
    error_rate: float
    slow_count: int
    very_slow_count: int
    critical_count: int
    slow_rate: float
    latency_p50_ms: float
    latency_p90_ms: float
    latency_p95_ms: float
    latency_p99_ms: float
    latency_mean_ms: float
    latency_min_ms: float
    latency_max_ms: float
    sample_count: int
    last_updated: str
    meets_sla: bool


class PerformanceSummaryResponse(BaseModel):
    """Overall performance summary"""

    total_endpoints: int
    total_requests: int
    total_errors: int
    global_error_rate: float
    endpoints_meeting_sla: int
    endpoints_violating_sla: int
    sla_compliance_rate: float
    average_p95_ms: float
    uptime_seconds: float
    sla_threshold_ms: float = SLOW_REQUEST_THRESHOLD_MS


class SlowEndpointsResponse(BaseModel):
    """Response for slow endpoints query"""

    threshold_ms: float
    count: int
    endpoints: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type


class TopEndpointsResponse(BaseModel):
    """Response for top endpoints query"""

    metric: str
    limit: int
    endpoints: list[dict[str, Any]]  # TODO(TYPE): replace Any with concrete type


@router.get("/summary", response_model=PerformanceSummaryResponse)
async def get_performance_summary(
    current_user: UserResponse = Depends(get_current_user),
) -> PerformanceSummaryResponse:
    """
    Get overall performance summary

    Returns:
    - Total endpoints tracked
    - Total requests processed
    - Error rate
    - SLA compliance rate (P95 < 200ms)
    - Average P95 latency across all endpoints
    """
    profiler = get_performance_profiler()
    summary = profiler.get_summary()
    return PerformanceSummaryResponse(**summary, sla_threshold_ms=SLOW_REQUEST_THRESHOLD_MS)


@router.get("/endpoints", response_model=list[dict[str, Any]])  # TODO(TYPE): replace Any with concrete type
async def get_all_endpoint_metrics(
    current_user: UserResponse = Depends(get_current_user),
) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
    """
    Get detailed metrics for all tracked endpoints

    Returns per-endpoint:
    - Request count and error rate
    - Latency percentiles (P50, P90, P95, P99)
    - Slow request counts
    - SLA compliance status
    """
    profiler = get_performance_profiler()
    return profiler.get_all_metrics()


@router.get("/slow", response_model=SlowEndpointsResponse)
async def get_slow_endpoints(
    threshold_ms: float = Query(
        default=SLOW_REQUEST_THRESHOLD_MS, description="P95 threshold in milliseconds"
    ),
    current_user: UserResponse = Depends(get_current_user),
) -> SlowEndpointsResponse:
    """
    Get endpoints with P95 latency above threshold

    Default threshold: 200ms (SLA target)

    Use this to identify endpoints that need optimization.
    """
    profiler = get_performance_profiler()
    slow = profiler.get_slow_endpoints(threshold_ms)
    return SlowEndpointsResponse(
        threshold_ms=threshold_ms,
        count=len(slow),
        endpoints=slow,
    )


@router.get("/top/latency", response_model=TopEndpointsResponse)
async def get_top_latency_endpoints(
    limit: int = Query(default=10, le=50, description="Number of endpoints to return"),
    current_user: UserResponse = Depends(get_current_user),
) -> TopEndpointsResponse:
    """
    Get top endpoints by P95 latency (highest first)

    Use this to identify the slowest endpoints for optimization.
    """
    profiler = get_performance_profiler()
    top = profiler.get_top_endpoints_by_latency(limit)
    return TopEndpointsResponse(
        metric="latency_p95_ms",
        limit=limit,
        endpoints=top,
    )


@router.get("/top/requests", response_model=TopEndpointsResponse)
async def get_top_request_endpoints(
    limit: int = Query(default=10, le=50, description="Number of endpoints to return"),
    current_user: UserResponse = Depends(get_current_user),
) -> TopEndpointsResponse:
    """
    Get top endpoints by request count (busiest first)

    Use this to identify high-traffic endpoints that may need scaling.
    """
    profiler = get_performance_profiler()
    top = profiler.get_top_endpoints_by_requests(limit)
    return TopEndpointsResponse(
        metric="request_count",
        limit=limit,
        endpoints=top,
    )


@router.get("/top/errors", response_model=TopEndpointsResponse)
async def get_top_error_endpoints(
    limit: int = Query(default=10, le=50, description="Number of endpoints to return"),
    current_user: UserResponse = Depends(get_current_user),
) -> TopEndpointsResponse:
    """
    Get top endpoints by error rate (highest first)

    Use this to identify endpoints with reliability issues.
    """
    profiler = get_performance_profiler()
    top = profiler.get_top_endpoints_by_errors(limit)
    return TopEndpointsResponse(
        metric="error_rate",
        limit=limit,
        endpoints=top,
    )


@router.get("/baseline")
async def get_latency_baseline(
    current_user: UserResponse = Depends(get_current_user),
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Get latency baseline report for all endpoints

    Returns a comprehensive report suitable for:
    - Performance baseline documentation
    - Optimization planning
    - SLA verification

    Format:
    {
        "generated_at": "2025-01-01T00:00:00",
        "sla_target_p95_ms": 200,
        "summary": { ... },
        "compliant_endpoints": [ ... ],
        "non_compliant_endpoints": [ ... ],
        "optimization_recommendations": [ ... ]
    }
    """

    profiler = get_performance_profiler()
    all_metrics = profiler.get_all_metrics()
    summary = profiler.get_summary()

    # Separate compliant and non-compliant endpoints
    compliant = [m for m in all_metrics if m["meets_sla"]]
    non_compliant = [m for m in all_metrics if not m["meets_sla"]]

    # Generate optimization recommendations
    recommendations: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type

    for endpoint in sorted(non_compliant, key=lambda x: x["latency_p95_ms"], reverse=True):
        severity = (
            "critical"
            if endpoint["latency_p95_ms"] >= 1000
            else "high"
            if endpoint["latency_p95_ms"] >= 500
            else "medium"
        )

        rec = {
            "endpoint": f"{endpoint['method']} {endpoint['endpoint']}",
            "current_p95_ms": endpoint["latency_p95_ms"],
            "target_p95_ms": SLOW_REQUEST_THRESHOLD_MS,
            "reduction_needed_ms": endpoint["latency_p95_ms"] - SLOW_REQUEST_THRESHOLD_MS,
            "severity": severity,
            "suggestions": [],
        }

        # Add specific suggestions based on latency profile
        if endpoint["latency_p99_ms"] > endpoint["latency_p95_ms"] * 2:
            rec["suggestions"].append(
                "Large P99/P95 gap suggests occasional slow queries - investigate database"
            )

        if endpoint["request_count"] > 100 and endpoint["latency_mean_ms"] > 100:
            rec["suggestions"].append("High traffic + high mean latency - consider caching")

        if endpoint["error_rate"] > 0.05:
            rec["suggestions"].append("High error rate may indicate underlying issues")

        if not rec["suggestions"]:
            rec["suggestions"].append(
                "Profile endpoint to identify bottleneck (DB, external API, computation)"
            )

        recommendations.append(rec)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sla_target_p95_ms": SLOW_REQUEST_THRESHOLD_MS,
        "summary": {
            "total_endpoints": len(all_metrics),
            "compliant_count": len(compliant),
            "non_compliant_count": len(non_compliant),
            "compliance_rate": len(compliant) / max(len(all_metrics), 1),
            "average_p95_ms": summary["average_p95_ms"] if all_metrics else 0,
            "total_requests": summary["total_requests"],
            "global_error_rate": summary["global_error_rate"],
        },
        "compliant_endpoints": sorted(
            compliant, key=lambda x: cast(dict[str, Any], x)["latency_p95_ms"]  # TODO(TYPE): replace Any with concrete type
        ),
        "non_compliant_endpoints": sorted(
            non_compliant,
            key=lambda x: cast(dict[str, Any], x)["latency_p95_ms"],  # TODO(TYPE): replace Any with concrete type
            reverse=True,
        ),
        "optimization_recommendations": recommendations,
    }


