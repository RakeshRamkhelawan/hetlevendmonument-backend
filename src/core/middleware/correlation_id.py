"""
Middleware for adding a correlation ID to each request.
"""

import uuid
from typing import Any
from collections.abc import Callable, Awaitable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class CorrelationIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        correlation_id = request.headers.get("X-Correlation-ID")
        if not correlation_id:
            correlation_id = str(uuid.uuid4())

        # Store correlation_id in request state for upstream error handlers
        request.state.correlation_id = correlation_id

        try:
            response = await call_next(request)
            response.headers["X-Correlation-ID"] = correlation_id
            return response

        except Exception:
            # Correlation ID is already on request.state for upstream logging
            # Re-raise the exception
            raise
