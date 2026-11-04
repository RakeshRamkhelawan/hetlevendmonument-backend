"""
Security Middleware for Tool Broker Service

Provides:
- Request/response logging with tracing
- Security validation
- CORS handling
- Rate limit preparation
"""

import logging
import time
import uuid
from typing import Any, Optional
from collections.abc import Callable

from starlette.datastructures import Headers
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send


logger = logging.getLogger(__name__)


class SecurityMiddleware:
    """
    Middleware for security-related request/response processing (Pure ASGI)

    Features:
    - Request ID generation for tracing
    - Detailed request/response logging
    - Security header validation
    - Execution time tracking
    """

    # Paths that don't require extensive logging
    EXCLUDED_PATHS: set[str] = {
        "/health",
        "/status",
        "/metrics",
        "/docs",
        "/redoc",
        "/openapi.json",
    }

    def __init__(self, app: ASGIApp, enable_security: bool = True) -> None:
        self.app = app
        self.enable_security = enable_security

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Process request with security middleware"""

        # Pass through for non-HTTP/WebSocket scopes
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        # Generate or extract request ID
        headers = Headers(scope=scope)
        request_id = headers.get("X-Request-ID") or str(uuid.uuid4())

        # Store metadata in scope state (shared with other middleware/endpoints)
        if "state" not in scope:
            scope["state"] = {}

        scope["state"]["request_id"] = request_id
        scope["state"]["has_auth"] = False

        # Extract basic auth state
        auth_header = headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            scope["state"]["has_auth"] = True

        path = scope.get("path", "")
        method = scope.get(
            "method", "WS"
        )  # WebSocket doesn't strictly have a method in the same way, but often GET

        # For WebSockets, we just pass through but still attach request_id
        if scope["type"] == "websocket":
            # Optional: Add logging for WS connect?
            await self.app(scope, receive, send)
            return

        # --- HTTP Request Processing ---

        start_time = time.time()
        status_code = 500  # Default if something crashes before response start

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]

                # Add security headers
                # We need to modify the headers list in the message
                headers_list = list(message.get("headers", []))
                headers_list.append((b"X-Request-ID", request_id.encode()))
                headers_list.append((b"X-Content-Type-Options", b"nosniff"))
                headers_list.append((b"X-Frame-Options", b"DENY"))
                headers_list.append((b"X-XSS-Protection", b"1; mode=block"))
                message["headers"] = headers_list

            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)

            # Post-request logging
            duration_ms = (time.time() - start_time) * 1000

            if path not in self.EXCLUDED_PATHS:
                self._log_request(
                    method=method,
                    path=path,
                    status_code=status_code,
                    duration_ms=duration_ms,
                    request_id=request_id,
                    has_auth=scope["state"]["has_auth"],
                )

        except Exception as e:
            # We re-raise the exception for the standard exception handler to catch,
            # but we log it here too with our context.
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                f"Request processing error: {str(e)}",
                extra={
                    "request_id": request_id,
                    "method": method,
                    "path": path,
                    "duration_ms": duration_ms,
                    "error_type": type(e).__name__,
                },
                exc_info=True,
            )
            raise

    def _log_request(
        self,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
        request_id: str,
        has_auth: bool,
    ) -> None:
        """Log request details with security context"""

        # Determine log level based on status code
        if status_code >= 500:
            log_level = logging.ERROR
        elif status_code >= 400:
            log_level = logging.WARNING
        else:
            log_level = logging.INFO

        logger.log(
            log_level,
            f"{method} {path} -> {status_code}",
            extra={
                "request_id": request_id,
                "method": method,
                "path": path,
                "status_code": status_code,
                "duration_ms": round(duration_ms, 2),
                "authenticated": has_auth,
            },
        )


class RateLimitMiddleware:
    """
    Rate limiting middleware (Pure ASGI)

    Foundation for implementation.
    Full implementation with Redis backing is in PHASE 2.3.
    """

    def __init__(self, app: ASGIApp, requests_per_minute: int = 1000) -> None:
        self.app = app
        self.requests_per_minute = requests_per_minute
        self.request_counts: dict[str, dict[str, Any]] = {}  # TODO(TYPE): replace Any with concrete type

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        # Simple in-memory tracking (Not production ready for distributed env, but matches existing logic)
        client = scope.get("client")
        client_ip = client[0] if client else "unknown"

        # Track request
        if client_ip not in self.request_counts:
            self.request_counts[client_ip] = {
                "count": 0,
                "reset_time": time.time() + 60,
            }

        current_time = time.time()
        if current_time > self.request_counts[client_ip]["reset_time"]:
            self.request_counts[client_ip] = {
                "count": 0,
                "reset_time": current_time + 60,
            }

        self.request_counts[client_ip]["count"] += 1

        if self.request_counts[client_ip]["count"] > self.requests_per_minute:
            retry_after = max(
                0,
                int(self.request_counts[client_ip]["reset_time"] - time.time()),
            )
            response = Response(
                content="Rate limit exceeded",
                status_code=429,
                headers={"Retry-After": str(retry_after)},
            )
            await response(scope, receive, send)
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                # Add headers
                headers_list = list(message.get("headers", []))
                remaining = max(
                    0,
                    self.requests_per_minute - self.request_counts[client_ip]["count"],
                )
                reset_time = int(self.request_counts[client_ip]["reset_time"])

                headers_list.append((b"X-RateLimit-Limit", str(self.requests_per_minute).encode()))
                headers_list.append((b"X-RateLimit-Remaining", str(remaining).encode()))
                headers_list.append((b"X-RateLimit-Reset", str(reset_time).encode()))
                message["headers"] = headers_list

            await send(message)

        await self.app(scope, receive, send_wrapper)


# Note: CORSMiddleware is usually imported from starlette.middleware.cors or fastapi.middleware.cors
# If we need to modify it, we should do so cautiously.
# The previous file had a custom CORSMiddleware inheriting from BaseHTTPMiddleware.
# Ideally, we should switch to the standard one in src/main.py or src/core/api/setup/middleware_config.py
# But for now, let's provide a pure ASGI version as requested to avoid changing imports elsewhere if possible.


class CORSMiddleware:
    """
    CORS middleware for Tool Broker Service (Pure ASGI wrapper logic)

    This is a simplified pure ASGI implementation or we can just rely on Starlette's.
    However, to keep `src/core/middleware/security_middleware.py` self-contained as before:
    """

    def __init__(
        self,
        app: ASGIApp,
        allow_origins: list[str] | None = None,
        allow_methods: list[str] | None = None,
        allow_headers: list[str] | None = None,
        expose_headers: list[str] | None = None,
        max_age: int = 3600,
        allow_credentials: bool = True,
    ) -> None:
        self.app = app
        self.allow_origins = allow_origins or ["*"]
        self.allow_methods = allow_methods or ["*"]
        self.allow_headers = allow_headers or ["*"]
        self.expose_headers = expose_headers or []
        self.allow_credentials = allow_credentials
        self.max_age = max_age

    def _cors_headers(self) -> list[tuple[bytes, bytes]]:
        """Build the static CORS headers expected by the current test contract."""
        headers = [
            (
                b"Access-Control-Allow-Origin",
                ", ".join(self.allow_origins).encode(),
            ),
            (
                b"Access-Control-Allow-Methods",
                ", ".join(self.allow_methods).encode(),
            ),
            (
                b"Access-Control-Allow-Headers",
                ", ".join(self.allow_headers).encode(),
            ),
            (b"Access-Control-Max-Age", str(self.max_age).encode()),
        ]

        if self.allow_credentials:
            headers.append((b"Access-Control-Allow-Credentials", b"true"))
        if self.expose_headers:
            headers.append(
                (
                    b"Access-Control-Expose-Headers",
                    ", ".join(self.expose_headers).encode(),
                )
            )

        return headers

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if scope.get("method") == "OPTIONS":
            headers = [(b"content-length", b"0")]
            headers.extend(self._cors_headers())
            await send({"type": "http.response.start", "status": 200, "headers": headers})
            await send({"type": "http.response.body", "body": b""})
            return

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                existing = {key.lower() for key, _ in headers}
                for key, value in self._cors_headers():
                    if key.lower() not in existing:
                        headers.append((key, value))
                message["headers"] = headers

            await send(message)

        await self.app(scope, receive, send_wrapper)
