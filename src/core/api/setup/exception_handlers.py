import logging
import time
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from src.core.exceptions.exceptions import SanskritiError
from src.core.shared.config import get_settings

logger = logging.getLogger(__name__)


def parse_limit_string(limit_str: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Parse rate limit string like '10 per 1 minute' into components."""
    import re

    match = re.match(r"(\d+)\s*(?:per\s+\d+\s+)?(\w+)", str(limit_str))
    if match:
        return {
            "limit": int(match.group(1)),
            "window": match.group(2),
            "window_seconds": 60 if "minute" in match.group(2).lower() else 3600,
        }
    return {"limit": 100, "window": "minute", "window_seconds": 60}


def setup_exception_handlers(app: FastAPI) -> None:
    """
    Registers global exception handlers for the FastAPI application.
    """
    settings = get_settings()

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
        """Handle rate limit exceeded with proper headers."""
        limit_info = parse_limit_string(str(exc.detail))
        reset_time = int(time.time()) + limit_info["window_seconds"]

        logger.warning(f"Rate limit exceeded: {request.url.path}, " f"limit={exc.detail}")

        return JSONResponse(
            status_code=429,
            content={
                "error": "Rate limit exceeded",
                "message": f"Too many requests. Maximum {limit_info['limit']} requests per {limit_info['window']}.",
                "limit": str(exc.detail),
                "retry_after_seconds": limit_info["window_seconds"],
                "documentation_url": "https://docs.sanskritisetu.org/api/rate-limits",
            },
            headers={
                "Retry-After": str(limit_info["window_seconds"]),
                "X-RateLimit-Limit": str(limit_info["limit"]),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(reset_time),
            },
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": True,
                "message": exc.detail,
                "status_code": exc.status_code,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    @app.exception_handler(SanskritiError)
    async def sanskriti_error_handler(request: Request, exc: SanskritiError) -> JSONResponse:
        """Handle all SanskritiError subclasses (including ConflictError)."""
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": True,
                "message": exc.message,
                "error_code": exc.error_code,
                "status_code": exc.status_code,
                "details": exc.details,
                "timestamp": exc.timestamp.isoformat(),
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": True,
                "message": "Internal server error" if not settings.debug else str(exc),
                "status_code": 500,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
        )

    logger.info("Global exception handlers registered.")
