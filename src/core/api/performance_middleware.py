"""
PERFORMANCE OPTIMIZATION MIDDLEWARE
Caching and async optimization for significant speed improvements
"""

import asyncio
import hashlib
import time
from datetime import datetime, timedelta, timezone
from functools import wraps
from typing import Any, Optional
from collections.abc import Awaitable, Callable

from fastapi import Request, Response

from src.core.middleware.tenant_context import get_tenant_id


class PerformanceCache:
    """Simple in-memory cache with TTL support"""

    def __init__(self, default_ttl: int = 300) -> None:  # 5 minutes default
        self.cache: dict[str, dict[str, Any]] = {}  # TODO(TYPE): replace Any with concrete type
        self.default_ttl = default_ttl

    def get(self, key: str) -> Any | None:  # TODO(TYPE): replace Any with concrete type
        """Get cached value if not expired"""
        if key not in self.cache:
            return None

        entry = self.cache[key]
        if datetime.now(timezone.utc) > entry["expires"]:
            del self.cache[key]
            return None

        return entry["value"]

    def set(
        self,
        key: str,
        value: Any,  # TODO(TYPE): replace Any with concrete type
        ttl: int | None = None,  # TODO(TYPE): replace Any with concrete type
    ) -> None:  # TODO(TYPE): replace Any with concrete type
        """Set cached value with expiration"""
        ttl = ttl or self.default_ttl
        self.cache[key] = {
            "value": value,
            "expires": datetime.now(timezone.utc) + timedelta(seconds=ttl),
        }

    def clear(self) -> None:
        """Clear all cache entries"""
        self.cache.clear()

    def get_stats(self) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get cache statistics"""
        active_entries = 0
        expired_entries = 0

        now = datetime.now(timezone.utc)
        for entry in self.cache.values():
            if now <= entry["expires"]:
                active_entries += 1
            else:
                expired_entries += 1

        return {
            "active_entries": active_entries,
            "expired_entries": expired_entries,
            "total_entries": len(self.cache),
        }


# Global cache instance
performance_cache = PerformanceCache()


def cached_response(
    ttl: int = 300,
) -> Callable[
    [Callable[..., Any]], Callable[..., Any]
]:  # TODO(TYPE): replace Any with concrete type
    """Decorator for caching endpoint responses"""

    def decorator(
        func: Callable[..., Any],
    ) -> Callable[..., Any]:  # TODO(TYPE): replace Any with concrete type
        @wraps(func)
        async def wrapper(
            *args: Any, **kwargs: Any
        ) -> Any:  # TODO(TYPE): replace Any with concrete type
            # Create cache key from function name and args -- prefixed with tenant_id (SP-SEC-001 TI-003)
            _tid = get_tenant_id() or 0
            # NOTE: t0 = system namespace; never a real tenant (tenant_id > 0 per ADR-005)
            _arg_hash = hashlib.md5(
                (str(args) + str(kwargs)).encode(), usedforsecurity=False
            ).hexdigest()
            cache_key = f"t{_tid}:{func.__name__}:{_arg_hash}"

            # Try to get from cache first
            cached_result = performance_cache.get(cache_key)
            if cached_result is not None:
                return cached_result

            # Execute function and cache result
            result = await func(*args, **kwargs)
            performance_cache.set(cache_key, result, ttl)

            return result

        return wrapper

    return decorator


def background_task(
    func: Callable[..., Any],
) -> Callable[..., Any]:  # TODO(TYPE): replace Any with concrete type
    """Decorator to run functions in background"""

    @wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        return asyncio.create_task(func(*args, **kwargs))

    return wrapper


class ResponseTimeTracker:
    """Track response times for performance monitoring"""

    def __init__(self) -> None:
        self.response_times: dict[str, list[float]] = {}
        self.max_samples = 100  # Keep last 100 samples per endpoint

    def add_response_time(self, endpoint: str, response_time: float) -> None:
        """Add response time sample"""
        if endpoint not in self.response_times:
            self.response_times[endpoint] = []

        samples = self.response_times[endpoint]
        samples.append(response_time)

        # Keep only recent samples
        if len(samples) > self.max_samples:
            samples.pop(0)

    def get_stats(
        self, endpoint: str
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get performance stats for endpoint"""
        if endpoint not in self.response_times or not self.response_times[endpoint]:
            return {"samples": 0}

        times = self.response_times[endpoint]
        return {
            "samples": len(times),
            "avg_response_time": sum(times) / len(times),
            "min_response_time": min(times),
            "max_response_time": max(times),
            "recent_response_time": times[-1] if times else 0,
        }

    def get_all_stats(
        self,
    ) -> dict[str, dict[str, Any]]:  # TODO(TYPE): replace Any with concrete type
        """Get stats for all endpoints"""
        return {endpoint: self.get_stats(endpoint) for endpoint in self.response_times}


# Global response tracker
response_tracker = ResponseTimeTracker()


def performance_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Callable[..., Awaitable[Response]]:
    """FastAPI middleware for performance tracking and optimization"""

    async def middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        start_time = time.time()

        # Process request
        response = await call_next(request)

        # Track response time
        response_time = time.time() - start_time
        endpoint = f"{request.method} {request.url.path}"
        response_tracker.add_response_time(endpoint, response_time)

        # Add performance headers
        response.headers["X-Response-Time"] = str(response_time)
        response.headers["X-Cache-Status"] = "MISS"  # Default, overridden by cache

        return response

    return middleware


async def async_health_check() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Optimized async health check"""
    return {
        "status": "healthy",
        "system": "operational",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "cache_stats": performance_cache.get_stats(),
        "performance_optimized": True,
    }


def get_performance_stats() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get comprehensive performance statistics"""
    return {
        "cache_stats": performance_cache.get_stats(),
        "response_times": response_tracker.get_all_stats(),
        "optimization_active": True,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
