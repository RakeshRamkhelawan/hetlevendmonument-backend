"""Security Headers Middleware - OWASP REST Security Compliance

Adds comprehensive security headers to all HTTP responses per OWASP REST Security Cheat Sheet.

CRITICAL HEADERS FOR GO-LIVE:
- Cache-Control: no-store (prevent sensitive data caching)
- Strict-Transport-Security: Force HTTPS (31536000 = 1 year)
- X-Content-Type-Options: nosniff (prevent MIME sniffing attacks)
- X-Frame-Options: DENY (prevent clickjacking)
- Content-Security-Policy: frame-ancestors 'none' (modern clickjacking protection)
- X-XSS-Protection: 1; mode=block (enable browser XSS filter)
- Referrer-Policy: no-referrer (prevent information leakage)
- Permissions-Policy: Disable unnecessary browser features

OWASP References:
- https://cheatsheetseries.owasp.org/cheatsheets/REST_Security_Cheat_Sheet.html#security-headers
- https://owasp.org/Top10/A05_2021-Security_Misconfiguration/

Target: A+ rating on securityheaders.com and Mozilla Observatory
"""

import os
from typing import Any, Optional

from starlette.requests import Request
from starlette.responses import Response
from starlette.types import Message, Receive, Scope, Send

# Paths that should not have strict caching headers
# (e.g., static assets that can be cached)
CACHEABLE_PATHS = frozenset(
    {
        "/docs",
        "/redoc",
        "/openapi.json",
        "/static",
    }
)

# Paths that are security-sensitive and need strict cache control
SENSITIVE_PATHS = frozenset(
    {
        "/api/auth",
        "/api/admin",
        "/api/v1/auth",
        "/api/v1/admin",
        "/api/security",
    }
)


class SecurityHeadersConfig:
    """Configuration for Content-Security-Policy and HSTS headers.

    TDD GREEN PHASE: Minimal implementation to pass tests.
    Provides environment-aware CSP and HSTS header configuration.
    """

    @staticmethod
    def get_csp_header() -> str:
        """Get Content-Security-Policy header based on environment.

        Production: Strict CSP (no unsafe-eval, frame protection)
        Development: Permissive (allows unsafe-eval for hot reload)

        Returns:
            CSP header string
        """
        env = os.getenv("ENVIRONMENT", "development").lower()

        if env == "production":
            # Strict CSP for production
            return (
                "default-src 'self'; "
                "script-src 'self'; "
                "style-src 'self' 'unsafe-inline'; "  # Allow inline styles for CSS frameworks
                "img-src 'self' data: https:; "
                "font-src 'self' data:; "
                "connect-src 'self'; "
                "frame-ancestors 'none'; "  # Prevent clickjacking
                "base-uri 'self'; "
                "form-action 'self'; "
                "upgrade-insecure-requests"  # Upgrade HTTP -> HTTPS
            )
        else:
            # Permissive CSP for development (hot reload, debugging)
            return (
                "default-src 'self' 'unsafe-inline' 'unsafe-eval'; "
                "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: https:; "
                "font-src 'self' data:; "
                "connect-src 'self' ws://localhost:* ws://127.0.0.1:* http://localhost:* http://127.0.0.1:*; "
                "frame-ancestors 'none'; "
                "base-uri 'self'; "
                "form-action 'self'"
            )

    @staticmethod
    def get_hsts_header() -> str:
        """Get Strict-Transport-Security header.

        Only enabled in production WITH https.
        Enforces HTTPS for 1 year, includes subdomains, allows preloading.

        Returns:
            HSTS header string (empty if not production+HTTPS)
        """
        env = os.getenv("ENVIRONMENT", "development").lower()
        https_enabled = os.getenv("HTTPS_ENABLED", "false").lower() == "true"

        if env == "production" and https_enabled:
            return "max-age=31536000; includeSubDomains; preload"

        return ""

    @staticmethod
    def get_all_headers() -> dict[str, str]:
        """Get all security headers as dictionary.

        Returns: Dict[str, Any] of header names to values  # TODO(TYPE): replace Any with concrete type
        """
        headers = {
            # MIME type sniffing protection
            "X-Content-Type-Options": "nosniff",
            # Clickjacking protection
            "X-Frame-Options": "DENY",
            # XSS protection (legacy but still useful)
            "X-XSS-Protection": "1; mode=block",
            # Referrer policy
            "Referrer-Policy": "strict-origin-when-cross-origin",
            # Feature policy (permissions)
            "Permissions-Policy": ("geolocation=(), microphone=(), camera=()"),
            # Content-Security-Policy
            "Content-Security-Policy": SecurityHeadersConfig.get_csp_header(),
        }

        # Add HSTS if applicable (production + HTTPS only)
        hsts = SecurityHeadersConfig.get_hsts_header()
        if hsts:
            headers["Strict-Transport-Security"] = hsts

        return headers


class SecurityHeadersMiddleware:
    """Middleware to add OWASP-compliant security headers to all HTTP responses.

    This middleware implements comprehensive security headers for A+ security rating.
    Headers are applied based on environment (production vs development) and
    request path (sensitive vs cacheable).

    Features:
        - Full OWASP A05 compliance for security misconfiguration prevention
        - Environment-aware header configuration
        - Path-based cache control for sensitive endpoints
        - Cross-origin isolation headers for defense in depth
        - Pure ASGI implementation (safe for WebSockets)
    """

    def __init__(
        self,
        app: Any,  # TODO(TYPE): replace Any with concrete type
        hsts_max_age: int = 31536000,
        strict_mode: bool = True,
    ) -> None:
        """Initialize security headers middleware.

        Args:
            app: The ASGI application
            hsts_max_age: Max age for HSTS header (default: 1 year)
            strict_mode: Enable stricter headers for production (default: True)
        """
        self.app = app
        self.hsts_max_age = hsts_max_age
        self.strict_mode = strict_mode
        self._is_production = os.getenv("ENVIRONMENT", "development").lower() == "production"

    def _build_security_headers(self, path: str) -> dict[str, str]:
        """Build response headers for the current request path."""
        security_headers: dict[str, str] = {
            "X-Frame-Options": "DENY",
            "X-Content-Type-Options": "nosniff",
            "Strict-Transport-Security": (
                f"max-age={self.hsts_max_age}; includeSubDomains; preload"
            ),
            "Content-Security-Policy": SecurityHeadersConfig.get_csp_header(),
            "X-XSS-Protection": "1; mode=block",
            "Referrer-Policy": "strict-origin-when-cross-origin",
            "Permissions-Policy": (
                "accelerometer=(), "
                "ambient-light-sensor=(), "
                "autoplay=(), "
                "battery=(), "
                "camera=(), "
                "cross-origin-isolated=(), "
                "display-capture=(), "
                "document-domain=(), "
                "encrypted-media=(), "
                "execution-while-not-rendered=(), "
                "execution-while-out-of-viewport=(), "
                "fullscreen=(), "
                "geolocation=(), "
                "gyroscope=(), "
                "magnetometer=(), "
                "microphone=(), "
                "midi=(), "
                "navigation-override=(), "
                "payment=(), "
                "picture-in-picture=(), "
                "publickey-credentials-get=(), "
                "screen-wake-lock=(), "
                "sync-xhr=(), "
                "usb=(), "
                "web-share=(), "
                "xr-spatial-tracking=()"
            ),
            "X-Permitted-Cross-Domain-Policies": "none",
            "Cross-Origin-Resource-Policy": "same-origin",
            "Cross-Origin-Opener-Policy": "same-origin-allow-popups",
            "Cross-Origin-Embedder-Policy": "credentialless",
        }

        if self._is_sensitive_path(path):
            security_headers["Cache-Control"] = (
                "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0"
            )
            security_headers["Pragma"] = "no-cache"
            security_headers["Expires"] = "0"
        elif not self._is_cacheable_path(path):
            security_headers["Cache-Control"] = "no-store, max-age=0"

        if self._is_production:
            security_headers["Expect-CT"] = "max-age=86400, enforce"

        return security_headers

    def _apply_headers(self, response: Response, path: str) -> Response:
        """Apply security headers to a Starlette response object."""
        for key, value in self._build_security_headers(path).items():
            response.headers[key] = value
        return response

    async def dispatch(
        self, request: Request, call_next: Any  # TODO(TYPE): replace Any with concrete type
    ) -> Response:
        """BaseHTTPMiddleware-compatible entry point used by tests and some apps."""
        response = await call_next(request)
        return self._apply_headers(response, request.url.path)

    def _is_sensitive_path(self, path: str) -> bool:
        """Check if the request path is security-sensitive."""
        return any(path.startswith(sensitive) for sensitive in SENSITIVE_PATHS)

    def _is_cacheable_path(self, path: str) -> bool:
        """Check if the request path can be cached."""
        return any(path.startswith(cacheable) for cacheable in CACHEABLE_PATHS)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """ASGI implementation."""
        # Process only HTTP requests
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "/")

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                security_headers = self._build_security_headers(path)

                # Append headers to the message (replacing any existing duplicates)
                header_names_to_set = {key.lower().encode() for key in security_headers}
                headers = [(k, v) for k, v in headers if k.lower() not in header_names_to_set]
                for key, value in security_headers.items():
                    headers.append((key.encode(), value.encode()))

                message["headers"] = headers

            await send(message)

        await self.app(scope, receive, send_wrapper)


def get_cors_config(
    environment: str | None = None,
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Get environment-specific CORS configuration.

    OWASP A05 recommends:
    - Never use wildcard (*) in production for sensitive APIs
    - Explicitly list allowed origins
    - Limit allowed methods and headers

    Args:
        environment: Override environment detection (for testing)

    Returns: Dict[str, Any]ionary with CORS configuration  # TODO(TYPE): replace Any with concrete type
    """
    env = environment or os.getenv("ENVIRONMENT", "development").lower()

    if env == "production":
        # Allow runtime override via ALLOWED_ORIGINS env var (comma-separated)
        extra_origins_str = os.getenv("ALLOWED_ORIGINS", "")
        extra_origins = [o.strip() for o in extra_origins_str.split(",") if o.strip()]
        default_origins = [
            "https://www.sanskritisetu.org",
            "https://sanskritisetu.org",
            "https://api.sanskritisetu.org",
            "https://portal.sanskritisetu.org",
            "https://www.sanskritisetu.nl",
            "https://sanskritisetu.nl",
            "https://api.sanskritisetu.nl",
            "https://levendmonument.nl",
            "https://www.levendmonument.nl",
            "https://levend-monument.nl",
            "https://www.levend-monument.nl",
        ]
        all_origins = default_origins + extra_origins
        # Filter to HTTPS-only origins in production (security requirement)
        allow_origins = list(dict.fromkeys([o for o in all_origins if o.startswith("https://")]))
        return {
            "allow_origins": allow_origins,
            "allow_credentials": True,
            "allow_methods": ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
            "allow_headers": [
                "Authorization",
                "Content-Type",
                "X-Request-ID",
                "X-Tenant-ID",
                "Accept",
                "Accept-Language",
            ],
            "expose_headers": [
                "X-Request-ID",
                "X-RateLimit-Limit",
                "X-RateLimit-Remaining",
                "X-RateLimit-Reset",
            ],
            "max_age": 600,  # 10 minutes
        }
    elif env == "staging":
        return {
            "allow_origins": [
                "https://staging.sanskritisetu.nl",
                "https://www.staging.sanskritisetu.nl",
                "http://localhost:3000",
                "http://localhost:8080",
            ],
            "allow_credentials": True,
            "allow_methods": ["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"],
            "allow_headers": [
                "Authorization",
                "Content-Type",
                "X-Request-ID",
                "X-Tenant-ID",
                "Accept",
                "Accept-Language",
            ],
            "expose_headers": ["X-Request-ID"],
            "max_age": 300,
        }
    else:  # development
        return {
            # Wildcard * with credentials=True is invalid. Use explicit localhosts.
            "allow_origins": [
                "http://localhost:3000",
                "http://localhost:8000",
                "http://localhost:5173",  # Vite default
                "http://localhost:5174",  # Vite alternative (when 5173 is taken)
                "http://127.0.0.1:3000",
                "http://127.0.0.1:8000",
                "http://127.0.0.1:5173",
                "http://127.0.0.1:5174",
            ],
            "allow_credentials": True,
            "allow_methods": ["*"],
            "allow_headers": ["*"],
            "expose_headers": ["*"],
            "max_age": 3600,
        }


def validate_cors_origins(origins: list[str], environment: str) -> list[str]:
    """Validate CORS origins for security compliance.

    Args:
        origins: List[Any] of allowed origins  # TODO(TYPE): replace Any with concrete type
        environment: Current environment

    Returns:
        Validated list of origins

    Raises:
        ValueError: If wildcard used in production
    """
    if environment == "production":
        if "*" in origins or any("*" in o for o in origins):
            raise ValueError(
                "Wildcard CORS origins are not allowed in production. "
                "Please specify explicit origins for security."
            )

        # Ensure HTTPS for production origins
        for origin in origins:
            if origin.startswith("http://") and "localhost" not in origin:
                raise ValueError(f"Non-HTTPS origin '{origin}' is not allowed in production.")

    return origins


def validate_cors_config(
    config: dict[str, Any], environment: str  # TODO(TYPE): replace Any with concrete type
) -> None:
    """Valideer CORS-configuratie op ongeldige combinaties (SEC-001, ADR-035 D4).

    Raises:
        ValueError: als allow_headers=['*'] gecombineerd wordt met allow_credentials=True
        ValueError: als allow_origins=['*'] in productie
    """
    allow_headers = config.get("allow_headers", [])
    allow_credentials = config.get("allow_credentials", False)
    allow_origins = config.get("allow_origins", [])

    if environment in ("production", "staging"):
        if allow_credentials and "*" in allow_headers:
            raise ValueError(
                "allow_headers=['*'] gecombineerd met allow_credentials=True is een ongeldige "
                "CORS-configuratie (Fetch spec). Gebruik expliciete header-namen. (SEC-001, ADR-035 D4)"
            )

    if environment == "production":
        if "*" in allow_origins or any("*" in o for o in allow_origins):
            raise ValueError(
                "Wildcard CORS origins zijn niet toegestaan in productie. "
                "Specificeer expliciete origins. (SEC-001)"
            )
