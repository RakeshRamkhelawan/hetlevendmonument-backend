"""
SB-6.1: Performance Profiler Middleware
Uses PyInstrument for request-level profiling.

Usage:
    Enable via environment variable: ENABLE_PROFILER=true
    Or per-request via header: X-Profile: true
"""

import logging
import os
import time
from typing import Any, Optional
from collections.abc import Callable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

logger = logging.getLogger(__name__)

# Try to import pyinstrument
try:
    from pyinstrument import Profiler

    PROFILER_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    PROFILER_AVAILABLE = False
    Profiler = None


class PerformanceProfilerMiddleware(BaseHTTPMiddleware):
    """
    SB-6.1: Middleware for performance profiling.

    Profiles requests when:
    - ENABLE_PROFILER=true environment variable is set
    - X-Profile: true header is sent
    - Request takes longer than slow_threshold_ms
    """

    def __init__(
        self,
        app: Any,  # TODO(TYPE): replace Any with concrete type
        slow_threshold_ms: int = 1000,
        output_dir: str = "profiles",
        enabled: bool | None = None,
    ) -> None:
        super().__init__(app)
        self.slow_threshold_ms = slow_threshold_ms
        self.output_dir = output_dir
        self.enabled = (
            enabled
            if enabled is not None
            else os.getenv("ENABLE_PROFILER", "false").lower() == "true"
        )

        if not PROFILER_AVAILABLE:
            logger.warning("pyinstrument not installed. Profiling disabled.")
            self.enabled = False

        # Create output directory
        if self.enabled:
            os.makedirs(output_dir, exist_ok=True)
            logger.info(f"Performance profiler enabled. Output: {output_dir}/")

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Check if profiling is requested for this request
        should_profile = self.enabled or request.headers.get("X-Profile", "").lower() == "true"

        if not should_profile or not PROFILER_AVAILABLE:
            return await call_next(request)

        # Profile the request
        # NOTE: Profiler is guaranteed non-None here because PROFILER_AVAILABLE is True
        assert Profiler is not None  # noqa: S101
        profiler = Profiler()
        profiler.start()

        start_time = time.perf_counter()

        try:
            response = await call_next(request)
            elapsed_ms = (time.perf_counter() - start_time) * 1000

            # Log slow requests
            if elapsed_ms > self.slow_threshold_ms:
                logger.warning(
                    f"Slow request: {request.method} {request.url.path} took {elapsed_ms:.2f}ms"
                )

                # Save profile for slow requests
                timestamp = int(time.time())
                path_safe = request.url.path.replace("/", "_")
                filename = f"{self.output_dir}/profile_{timestamp}_{path_safe}.html"

                try:
                    with open(filename, "w") as f:
                        f.write(profiler.output_html())
                    logger.info(f"Profile saved: {filename}")
                except Exception as e:
                    logger.error(f"Failed to save profile: {e}")

            # Add timing header
            response.headers["X-Response-Time"] = f"{elapsed_ms:.2f}ms"

            return response

        except Exception as e:
            # Calculate elapsed time even on error
            elapsed_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                f"Request failed: {request.method} {request.url.path} "
                f"after {elapsed_ms:.2f}ms - {type(e).__name__}: {str(e)}"
            )
            raise

        finally:
            # Always stop the profiler, even if there was an exception
            profiler.stop()


def get_profiler_stats() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get profiler statistics."""
    return {
        "available": PROFILER_AVAILABLE,
        "enabled": os.getenv("ENABLE_PROFILER", "false").lower() == "true",
    }
