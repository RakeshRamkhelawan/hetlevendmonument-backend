# core/middleware/performance_profiler.py
"""
Performance Profiling Middleware for SanskritiSetu.org

Task 5.4.1: Performance Optimization
- Measures API latency baseline
- Tracks p95 latency per endpoint
- Identifies slow endpoints (>200ms)
- Provides profiling data for optimization

Features:
- Per-endpoint latency tracking with percentiles (P50, P90, P95, P99)
- Slow request detection and logging
- Query count tracking per request
- Memory usage tracking
- Real-time bottleneck detection
"""

import asyncio
import functools
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from statistics import mean
from typing import Any
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger(__name__)


# Configuration constants
SLOW_REQUEST_THRESHOLD_MS = 200  # P95 target: <200ms
VERY_SLOW_REQUEST_THRESHOLD_MS = 500  # Alert threshold
CRITICAL_REQUEST_THRESHOLD_MS = 1000  # Critical performance issue
MAX_LATENCY_SAMPLES = 10000  # Keep last N samples per endpoint
CLEANUP_INTERVAL_SECONDS = 300  # Cleanup old data every 5 minutes


@dataclass
class EndpointMetrics:
    """Metrics for a single endpoint"""

    endpoint: str
    method: str
    latencies_ms: list[float] = field(default_factory=list)
    request_count: int = 0
    error_count: int = 0
    slow_count: int = 0  # Requests > 200ms
    very_slow_count: int = 0  # Requests > 500ms
    critical_count: int = 0  # Requests > 1000ms
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def add_latency(self, latency_ms: float, is_error: bool = False) -> None:
        """Add a latency sample"""
        self.latencies_ms.append(latency_ms)
        self.request_count += 1
        self.last_updated = datetime.now(timezone.utc)

        if is_error:
            self.error_count += 1

        if latency_ms >= CRITICAL_REQUEST_THRESHOLD_MS:
            self.critical_count += 1
        elif latency_ms >= VERY_SLOW_REQUEST_THRESHOLD_MS:
            self.very_slow_count += 1
        elif latency_ms >= SLOW_REQUEST_THRESHOLD_MS:
            self.slow_count += 1

        # Trim old samples to prevent memory issues
        if len(self.latencies_ms) > MAX_LATENCY_SAMPLES:
            self.latencies_ms = self.latencies_ms[-MAX_LATENCY_SAMPLES:]

    def get_percentiles(self) -> dict[str, float]:
        """Calculate latency percentiles"""
        if not self.latencies_ms:
            return {
                "p50": 0,
                "p90": 0,
                "p95": 0,
                "p99": 0,
                "mean": 0,
                "min": 0,
                "max": 0,
            }

        sorted_latencies = sorted(self.latencies_ms)
        n = len(sorted_latencies)

        def percentile(p: float) -> float:
            idx = int(n * p / 100)
            return sorted_latencies[min(idx, n - 1)]

        return {
            "p50": percentile(50),
            "p90": percentile(90),
            "p95": percentile(95),
            "p99": percentile(99),
            "mean": mean(self.latencies_ms),
            "min": min(self.latencies_ms),
            "max": max(self.latencies_ms),
        }

    def get_summary(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get full metrics summary"""
        percentiles = self.get_percentiles()
        return {
            "endpoint": self.endpoint,
            "method": self.method,
            "request_count": self.request_count,
            "error_count": self.error_count,
            "error_rate": self.error_count / max(self.request_count, 1),
            "slow_count": self.slow_count,
            "very_slow_count": self.very_slow_count,
            "critical_count": self.critical_count,
            "slow_rate": (self.slow_count + self.very_slow_count + self.critical_count)
            / max(self.request_count, 1),
            "latency_p50_ms": round(percentiles["p50"], 2),
            "latency_p90_ms": round(percentiles["p90"], 2),
            "latency_p95_ms": round(percentiles["p95"], 2),
            "latency_p99_ms": round(percentiles["p99"], 2),
            "latency_mean_ms": round(percentiles["mean"], 2),
            "latency_min_ms": round(percentiles["min"], 2),
            "latency_max_ms": round(percentiles["max"], 2),
            "sample_count": len(self.latencies_ms),
            "last_updated": self.last_updated.isoformat(),
            "meets_sla": percentiles["p95"] < SLOW_REQUEST_THRESHOLD_MS,
        }


class PerformanceProfiler:
    """
    Singleton performance profiler for tracking API latencies

    Usage:
        profiler = get_performance_profiler()
        metrics = profiler.get_metrics()
        slow_endpoints = profiler.get_slow_endpoints()
    """

    _instance: "PerformanceProfiler | None" = None

    def __init__(self) -> None:
        self.endpoint_metrics: dict[str, EndpointMetrics] = {}
        self._lock = asyncio.Lock()
        self._last_cleanup = datetime.now(timezone.utc)
        self._start_time = datetime.now(timezone.utc)

    @classmethod
    def get_instance(cls) -> "PerformanceProfiler":
        """Get singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def _get_endpoint_key(self, method: str, path: str) -> str:
        """Generate unique key for endpoint"""
        # Normalize path by removing IDs (UUIDs, integers)
        import re

        normalized_path = re.sub(
            r"/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            "/{id}",
            path,
        )
        normalized_path = re.sub(r"/\d+", "/{id}", normalized_path)
        return f"{method}:{normalized_path}"

    async def record_request(
        self,
        method: str,
        path: str,
        latency_ms: float,
        status_code: int,
        is_error: bool = False,
    ) -> None:
        """Record a request's latency"""
        key = self._get_endpoint_key(method, path)

        async with self._lock:
            if key not in self.endpoint_metrics:
                self.endpoint_metrics[key] = EndpointMetrics(
                    endpoint=path,
                    method=method,
                )

            self.endpoint_metrics[key].add_latency(latency_ms, is_error)

            # Log slow requests
            if latency_ms >= CRITICAL_REQUEST_THRESHOLD_MS:
                logger.warning(
                    f"[CRITICAL SLOW] {method} {path}: {latency_ms:.2f}ms (status={status_code})"
                )
            elif latency_ms >= VERY_SLOW_REQUEST_THRESHOLD_MS:
                logger.warning(
                    f"[VERY SLOW] {method} {path}: {latency_ms:.2f}ms (status={status_code})"
                )
            elif latency_ms >= SLOW_REQUEST_THRESHOLD_MS:
                logger.info(f"[SLOW] {method} {path}: {latency_ms:.2f}ms (status={status_code})")

            # Periodic cleanup
            await self._maybe_cleanup()

    async def _maybe_cleanup(self) -> None:
        """Clean up old data periodically"""
        now = datetime.now(timezone.utc)
        if (now - self._last_cleanup).total_seconds() > CLEANUP_INTERVAL_SECONDS:
            self._last_cleanup = now
            # Remove endpoints not updated in 24 hours
            cutoff = now - timedelta(hours=24)
            to_remove = [
                key
                for key, metrics in self.endpoint_metrics.items()
                if metrics.last_updated < cutoff
            ]
            for key in to_remove:
                del self.endpoint_metrics[key]

    def get_all_metrics(self) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get metrics for all endpoints"""
        return [metrics.get_summary() for metrics in self.endpoint_metrics.values()]

    def get_slow_endpoints(
        self, threshold_ms: float = SLOW_REQUEST_THRESHOLD_MS
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get endpoints with P95 above threshold"""
        slow: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
        for metrics in self.endpoint_metrics.values():
            percentiles = metrics.get_percentiles()
            if percentiles["p95"] >= threshold_ms:
                slow.append(metrics.get_summary())
        return sorted(slow, key=lambda x: x["latency_p95_ms"], reverse=True)

    def get_top_endpoints_by_latency(
        self, limit: int = 10
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get top N endpoints by P95 latency"""
        all_metrics = self.get_all_metrics()
        return sorted(all_metrics, key=lambda x: x["latency_p95_ms"], reverse=True)[:limit]

    def get_top_endpoints_by_requests(
        self, limit: int = 10
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get top N endpoints by request count"""
        all_metrics = self.get_all_metrics()
        return sorted(all_metrics, key=lambda x: x["request_count"], reverse=True)[:limit]

    def get_top_endpoints_by_errors(
        self, limit: int = 10
    ) -> list[dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get top N endpoints by error rate"""
        all_metrics = self.get_all_metrics()
        return sorted(all_metrics, key=lambda x: x["error_rate"], reverse=True)[:limit]

    def get_summary(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get overall performance summary"""
        all_metrics = self.get_all_metrics()

        if not all_metrics:
            return {
                "total_endpoints": 0,
                "total_requests": 0,
                "total_errors": 0,
                "global_error_rate": 0,
                "endpoints_meeting_sla": 0,
                "endpoints_violating_sla": 0,
                "sla_compliance_rate": 1.0,
                "average_p95_ms": 0,
                "uptime_seconds": (datetime.now(timezone.utc) - self._start_time).total_seconds(),
            }

        total_requests = sum(m["request_count"] for m in all_metrics)
        total_errors = sum(m["error_count"] for m in all_metrics)
        meeting_sla = sum(1 for m in all_metrics if m["meets_sla"])
        violating_sla = len(all_metrics) - meeting_sla

        return {
            "total_endpoints": len(all_metrics),
            "total_requests": total_requests,
            "total_errors": total_errors,
            "global_error_rate": total_errors / max(total_requests, 1),
            "endpoints_meeting_sla": meeting_sla,
            "endpoints_violating_sla": violating_sla,
            "sla_compliance_rate": meeting_sla / max(len(all_metrics), 1),
            "average_p95_ms": mean(m["latency_p95_ms"] for m in all_metrics),
            "uptime_seconds": (datetime.now(timezone.utc) - self._start_time).total_seconds(),
        }

    def reset(self) -> None:
        """Reset all metrics"""
        self.endpoint_metrics.clear()
        self._start_time = datetime.now(timezone.utc)


def get_performance_profiler() -> PerformanceProfiler:
    """Get the global performance profiler instance"""
    return PerformanceProfiler.get_instance()


class PerformanceProfilingMiddleware(BaseHTTPMiddleware):
    """
    ASGI middleware for automatic request profiling

    Tracks:
    - Request latency (start to response)
    - Error rates
    - Slow request detection

    NOTE: This middleware uses BaseHTTPMiddleware but does NOT perform any
    async database I/O. All state is kept in-memory (self.profiler).
    Therefore it does not trigger MissingGreenlet issues (unlike
    AuditLoggingMiddleware which was converted to pure ASGI in B-001).
    If DB calls are added in the future, convert to pure ASGI.
    """

    def __init__(
        self,
        app: ASGIApp,
        exclude_paths: list[str] | None = None,
    ) -> None:
        super().__init__(app)
        self.profiler = get_performance_profiler()
        self.exclude_paths = exclude_paths or [
            "/health",
            "/live",
            "/ready",
            "/metrics",
            "/openapi.json",
            "/docs",
            "/redoc",
        ]

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        await super().__call__(scope, receive, send)

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Process request and record metrics"""
        path = request.url.path
        method = request.method

        # Skip excluded paths
        for excluded in self.exclude_paths:
            if path.startswith(excluded):
                return await call_next(request)

        # Record start time
        start_time = time.perf_counter()

        # Process request
        is_error = False
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            is_error = status_code >= 400
            return response
        except Exception:
            is_error = True
            raise
        finally:
            # Calculate latency
            latency_ms = (time.perf_counter() - start_time) * 1000

            # Record metrics
            await self.profiler.record_request(
                method=method,
                path=path,
                latency_ms=latency_ms,
                status_code=status_code,
                is_error=is_error,
            )


def profile_function(
    name: str | None = None,
) -> Callable[
    [Callable[..., Any]], Callable[..., Any]
]:  # TODO(TYPE): replace Any with concrete type
    """
    Decorator to profile individual functions

    Usage:
        @profile_function("my_heavy_operation")
        async def my_function():
            ...
    """

    def decorator(
        func: Callable[..., Any],
    ) -> Callable[..., Any]:  # TODO(TYPE): replace Any with concrete type
        func_name = name or f"{func.__module__}.{func.__name__}"

        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                elapsed_ms = (time.perf_counter() - start) * 1000
                if elapsed_ms >= SLOW_REQUEST_THRESHOLD_MS:
                    logger.info(f"[PROFILE] {func_name}: {elapsed_ms:.2f}ms")
                return result
            except Exception as e:
                elapsed_ms = (time.perf_counter() - start) * 1000
                logger.warning(f"[PROFILE ERROR] {func_name}: {elapsed_ms:.2f}ms - {str(e)}")
                raise

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                elapsed_ms = (time.perf_counter() - start) * 1000
                if elapsed_ms >= SLOW_REQUEST_THRESHOLD_MS:
                    logger.info(f"[PROFILE] {func_name}: {elapsed_ms:.2f}ms")
                return result
            except Exception as e:
                elapsed_ms = (time.perf_counter() - start) * 1000
                logger.warning(f"[PROFILE ERROR] {func_name}: {elapsed_ms:.2f}ms - {str(e)}")
                raise

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


class QueryProfiler:
    """
    Track database query performance per request

    Usage in middleware:
        request.state.query_profiler = QueryProfiler()
        # Later in code:
        request.state.query_profiler.record_query(sql, duration_ms)
    """

    def __init__(self) -> None:
        self.queries: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
        self.total_query_time_ms: float = 0

    def record_query(self, sql: str, duration_ms: float, rows_affected: int = 0) -> None:
        """Record a database query"""
        self.queries.append(
            {
                "sql": sql[:200] + "..." if len(sql) > 200 else sql,
                "duration_ms": duration_ms,
                "rows_affected": rows_affected,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        self.total_query_time_ms += duration_ms

        # Log slow queries
        if duration_ms >= 100:
            logger.warning(f"[SLOW QUERY] {duration_ms:.2f}ms: {sql[:100]}...")

    def get_summary(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get query profiling summary"""
        if not self.queries:
            return {
                "query_count": 0,
                "total_query_time_ms": 0,
                "average_query_time_ms": 0,
                "slowest_query_ms": 0,
            }

        return {
            "query_count": len(self.queries),
            "total_query_time_ms": round(self.total_query_time_ms, 2),
            "average_query_time_ms": round(self.total_query_time_ms / len(self.queries), 2),
            "slowest_query_ms": round(max(q["duration_ms"] for q in self.queries), 2),
            "queries": self.queries[-10:],  # Last 10 queries
        }
