"""
WebSocket CORS Middleware

Starlette's built-in CORSMiddleware adds CORS headers to HTTP responses but does NOT
add them to WebSocket upgrade rejection responses (400/403). This middleware fills that
gap by intercepting WebSocket upgrade requests and injecting the correct
Access-Control-Allow-Origin header into any non-101 response.

Without this middleware, browsers report a generic CORS error when a WebSocket
connection is rejected, even though the actual issue may be authentication or routing.
"""

from typing import Any
from collections.abc import Awaitable, Callable

from starlette.types import ASGIApp, Message, Receive, Scope, Send


class WebSocketCORSMiddleware:
    """ASGI middleware that adds CORS headers to WebSocket rejection responses.

    Starlette's CORSMiddleware handles HTTP CORS correctly but skips adding
    Access-Control-Allow-Origin to non-101 WebSocket upgrade responses.
    This causes browsers to report misleading 'CORS error' messages when a
    WebSocket connection is rejected for any reason (auth failure, bad URL, etc.).
    """

    def __init__(self, app: ASGIApp, allowed_origins: list[str]) -> None:
        self.app = app
        self.allowed_origins = set(allowed_origins)

    async def __call__(
        self,
        scope: Scope,
        receive: Receive,
        send: Send,
    ) -> None:
        if scope["type"] != "websocket":
            await self.app(scope, receive, send)
            return

        # Extract the Origin header from the WebSocket upgrade request
        headers = dict(scope.get("headers", []))
        origin = headers.get(b"origin", b"").decode("utf-8", errors="ignore")

        if not origin or origin not in self.allowed_origins:
            # Origin not allowed or not present -- let the app handle it,
            # but wrap send() to inject CORS headers into the rejection response.
            await self.app(scope, receive, self._send_with_cors(send, origin))
            return

        # Origin is allowed -- inject CORS header into all responses (101 or rejection)
        await self.app(scope, receive, self._send_with_cors(send, origin))

    def _send_with_cors(
        self,
        send: Send,
        origin: str,
    ) -> Callable[[Message], Awaitable[None]]:
        """Wrap the ASGI send callable to inject CORS headers."""
        allowed = origin in self.allowed_origins

        async def send_wrapper(event: Message) -> None:
            if event["type"] == "http.response.start" and allowed:
                # Inject Access-Control-Allow-Origin into HTTP-level rejection responses
                headers = list(event.get("headers", []))
                existing_names = {h[0].lower() for h in headers}
                if b"access-control-allow-origin" not in existing_names:
                    headers.append((b"access-control-allow-origin", origin.encode("utf-8")))
                if b"access-control-allow-credentials" not in existing_names:
                    headers.append((b"access-control-allow-credentials", b"true"))
                event = {**event, "headers": headers}
            await send(event)

        return send_wrapper
