"""
Security Audit Logger Middleware

Logs suspicious requests and potential attack patterns.
Helps detect and respond to security threats in real-time.
"""

import time
from typing import Any, Optional
from collections.abc import Awaitable, Callable

from fastapi import Request
from loguru import logger
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class AuditLoggerMiddleware(BaseHTTPMiddleware):
    """
    Logs security-relevant events and detects attack patterns.

    Detects:
    - SQL injection attempts
    - XSS attempts
    - Command injection attempts
    - Path traversal attempts
    - Suspicious user agents
    - Excessive request rates
    """

    # Paths to exclude from body scanning (to avoid consuming request body)
    EXCLUDED_PATHS = {
        "/api/v1/auth/login",
        "/api/v1/auth/register",
        "/api/v1/auth/token",
        "/health",
        "/docs",
        "/openapi.json",
        "/redoc",
    }

    # Suspicious patterns to detect in requests
    SQL_INJECTION_PATTERNS = [
        "DROP",
        "DELETE",
        "UPDATE",
        "INSERT",
        "UNION",
        "SELECT",
        "EXEC",
        "EXECUTE",
        "--",
        "/*",
        "*/",
        "xp_",
        "sp_",
    ]

    XSS_PATTERNS = [
        "<script",
        "</script",
        "javascript:",
        "onerror=",
        "onload=",
        "<iframe",
        "<object",
        "<embed",
        "eval(",
        "alert(",
    ]

    COMMAND_INJECTION_PATTERNS = [";", "&&", "||", "`", "$", "$(", "${", "|"]

    PATH_TRAVERSAL_PATTERNS = ["..", "/etc/", "/bin/", "/usr/", "C:\\", "D:\\"]

    SUSPICIOUS_USER_AGENTS = [
        "sqlmap",
        "nikto",
        "nmap",
        "masscan",
        "metasploit",
        "burp",
        "zap",
        "acunetix",
        "nessus",
    ]

    def __init__(self, app: Any) -> None:  # TODO(TYPE): replace Any with concrete type
        super().__init__(app)
        self.request_counts: dict[str, list[float]] = {}

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        start_time = time.time()
        suspicious_indicators: set[str] = set()

        # Get client IP
        client_ip = request.client.host if request.client else "unknown"

        # Skip body scanning for excluded paths to avoid consuming request body
        path = str(request.url.path)
        skip_body_scan = path in self.EXCLUDED_PATHS

        # Check user agent
        user_agent = request.headers.get("user-agent", "").lower()
        for suspicious_agent in self.SUSPICIOUS_USER_AGENTS:
            if suspicious_agent in user_agent:
                suspicious_indicators.add(f"suspicious_user_agent:{suspicious_agent}")

        # Check path for traversal attempts
        for pattern in self.PATH_TRAVERSAL_PATTERNS:
            if pattern in path:
                suspicious_indicators.add(f"path_traversal:{pattern}")

        # Check query parameters
        for param_name, param_value in request.query_params.items():
            param_str = str(param_value).upper()

            # SQL injection check
            for pattern in self.SQL_INJECTION_PATTERNS:
                if pattern in param_str:
                    suspicious_indicators.add(f"sql_injection_query:{pattern}")

            # XSS check
            for pattern in self.XSS_PATTERNS:
                if pattern.upper() in param_str:
                    suspicious_indicators.add(f"xss_query:{pattern}")

            # Command injection check
            for pattern in self.COMMAND_INJECTION_PATTERNS:
                if pattern in param_str:
                    suspicious_indicators.add(f"command_injection_query:{pattern}")

        # Check request body (if present and not excluded)
        try:
            if not skip_body_scan and request.method in ["POST", "PUT", "PATCH"]:
                body = await request.body()
                body_str = body.decode("utf-8", errors="ignore").upper()

                # SQL injection check
                for pattern in self.SQL_INJECTION_PATTERNS:
                    if pattern in body_str:
                        suspicious_indicators.add(f"sql_injection_body:{pattern}")

                # XSS check
                for pattern in self.XSS_PATTERNS:
                    if pattern.upper() in body_str:
                        suspicious_indicators.add(f"xss_body:{pattern}")

                # Command injection check
                for pattern in self.COMMAND_INJECTION_PATTERNS:
                    if pattern in body_str:
                        suspicious_indicators.add(f"command_injection_body:{pattern}")

        except Exception as e:
            logger.debug(f"Could not read request body for audit: {e}")

        # Rate limiting check (simple in-memory)
        current_time = time.time()
        if client_ip not in self.request_counts:
            self.request_counts[client_ip] = []

        # Clean old entries (older than 1 minute)
        self.request_counts[client_ip] = [
            t for t in self.request_counts[client_ip] if current_time - t < 60
        ]

        # Add current request
        self.request_counts[client_ip].append(current_time)

        # Check if rate exceeds 200 requests per minute
        if len(self.request_counts[client_ip]) > 200:
            suspicious_indicators.add("rate_limit_exceeded")

        # Log if suspicious
        if suspicious_indicators:
            logger.warning(
                "SECURITY ALERT - Suspicious request detected",
                extra={
                    "ip": client_ip,
                    "path": path,
                    "method": request.method,
                    "user_agent": user_agent,
                    "indicators": list(suspicious_indicators),
                    "query_params": dict(request.query_params),
                },
            )

            # Optional: Block highly suspicious requests
            # Uncomment to enable blocking
            # if len(suspicious_indicators) >= 3:
            #     raise HTTPException(
            #         status_code=status.HTTP_403_FORBIDDEN,
            #         detail="Request blocked for security reasons"
            #     )

        # Process request with proper error handling
        try:
            response = await call_next(request)

            # Calculate request duration
            duration = time.time() - start_time

            # Log all requests (info level for normal, warning for suspicious)
            log_level = "WARNING" if suspicious_indicators else "INFO"
            logger.log(
                log_level,
                f"{request.method} {path} - {response.status_code} - {duration:.3f}s",
                extra={
                    "ip": client_ip,
                    "method": request.method,
                    "path": path,
                    "status_code": response.status_code,
                    "duration_seconds": duration,
                    "suspicious": bool(suspicious_indicators),
                },
            )

            return response

        except Exception as exc:
            # Calculate request duration
            duration = time.time() - start_time

            # Log error
            logger.error(
                f"Request failed: {request.method} {path} from {client_ip} "
                f"after {duration:.3f}s - {type(exc).__name__}: {str(exc)}",
                extra={
                    "ip": client_ip,
                    "method": request.method,
                    "path": path,
                    "duration_seconds": duration,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "suspicious": bool(suspicious_indicators),
                },
            )

            # Re-raise the exception for upstream handling
            raise
