"""
IP Whitelist Middleware for SanskritiSetu

Middleware that enforces IP-based access control on incoming requests.
Integrates with the IPWhitelistService for whitelist checking.
"""

import logging
from typing import Optional
from collections.abc import Awaitable, Callable

from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Receive, Scope, Send

from src.core.security.ip_whitelist import IPWhitelistResult, IPWhitelistService

logger = logging.getLogger(__name__)


class IPWhitelistMiddleware:
    """
    ASGI middleware for IP whitelisting.

    Features:
    - Blocks requests from non-whitelisted IPs (403 Forbidden)
    - Supports path-based bypass (e.g., health checks)
    - Handles proxy headers (X-Forwarded-For, X-Real-IP)
    - Integrates with IPWhitelistService
    """

    def __init__(
        self,
        app: ASGIApp,
        whitelist_service: IPWhitelistService | None = None,
    ) -> None:
        self.app = app
        self.whitelist_service = whitelist_service or IPWhitelistService()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Process request through IP whitelist check"""
        # Only process HTTP requests
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")

        # Get client IP from scope
        client = scope.get("client")
        client_ip = client[0] if client else "unknown"

        # Extract headers for proxy IP extraction
        headers = Headers(scope=scope)
        header_dict = {
            "x-forwarded-for": headers.get("x-forwarded-for", ""),
            "x-real-ip": headers.get("x-real-ip", ""),
        }

        # Check IP access
        result, reason = self.whitelist_service.check_ip_access(
            client_ip=client_ip,
            path=path,
            headers=header_dict,
        )

        if result == IPWhitelistResult.DENIED:
            real_ip = self.whitelist_service.extract_client_ip(client_ip, header_dict)
            logger.warning(f"IP whitelist denied access: {real_ip} for path {path}")

            # Return 403 Forbidden
            await send(
                {
                    "type": "http.response.start",
                    "status": 403,
                    "headers": [
                        (b"content-type", b"application/json"),
                        (b"x-ip-whitelist", b"denied"),
                    ],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": (
                        b'{"error": "Forbidden", '
                        b'"message": "IP address not whitelisted", '
                        b'"detail": "' + real_ip.encode() + b'"}'
                    ),
                }
            )
            return

        # Allow the request to proceed
        await self.app(scope, receive, send)


async def ip_whitelist_middleware(request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
    """
    FastAPI-style middleware function for IP whitelisting.

    Can be used with app.middleware("http") decorator.

    Args:
        request: FastAPI Request object
        call_next: Next middleware/handler in chain

    Returns:
        Response object
    """
    from fastapi.responses import JSONResponse

    service = IPWhitelistService()

    # Get client IP
    client_ip = request.client.host if request.client else "unknown"

    # Build headers dict for proxy extraction
    headers = {
        "x-forwarded-for": request.headers.get("x-forwarded-for", ""),
        "x-real-ip": request.headers.get("x-real-ip", ""),
    }

    # Check access
    result, reason = service.check_ip_access(
        client_ip=client_ip,
        path=request.url.path,
        headers=headers,
    )

    if result == IPWhitelistResult.DENIED:
        real_ip = service.extract_client_ip(client_ip, headers)
        logger.warning(f"IP whitelist denied access: {real_ip} for path {request.url.path}")
        return JSONResponse(
            status_code=403,
            content={
                "error": "Forbidden",
                "message": "IP address not whitelisted",
                "detail": real_ip,
            },
            headers={"X-IP-Whitelist": "denied"},
        )

    # Continue to next middleware/handler
    return await call_next(request)
