"""Rate limiting middleware for API protection.

Implements distributed rate limiting to prevent abuse and DOS attacks:
- Per-tenant rate limiting for multi-tenant SaaS (production)
- Per-IP fallback for unauthenticated requests
- Redis-backed storage for distributed deployments
- In-memory fallback for development
- Configurable limits per endpoint
- X-RateLimit-* headers for client-side throttling
"""

import os
import re
import time
from typing import Any, cast
from urllib.parse import urlparse, urlunparse

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from loguru import logger
from prometheus_client import Counter
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

# Cache limiter instances by service name to avoid repeated creation cost
# during router registration at startup.
_limiter_cache: dict[str, Limiter] = {}

# Prometheus metrics for rate limit monitoring
rate_limit_violations = Counter(
    "rate_limit_violations_total",
    "Total rate limit violations",
    ["endpoint", "tenant_id", "limit_type"],
)


def get_tenant_identifier(request: Request) -> str:
    """Extract tenant ID for per-tenant rate limiting.

    Multi-tenant SaaS pattern: Rate limits apply per tenant, not per IP.
    This prevents shared office/VPN users from affecting each other.

    Only uses tenant_id from request.state (set by TenantMiddleware from JWT).
    Falls back to IP address for unauthenticated requests.
    NOTE: X-Tenant-ID header is intentionally NOT used -- it is user-controlled
    and would allow attackers to spoof other tenants' rate limit buckets.
    """
    try:
        # Only accept tenant_id from request state (set by JWT middleware -- ADR-003)
        if hasattr(request.state, "tenant_id") and request.state.tenant_id:
            return f"tenant:{request.state.tenant_id}"
    except Exception:
        pass

    # Fallback to IP address for unauthenticated requests
    return get_remote_address(request)


def get_redis_storage_url(base_url: str, db_index: int = 2) -> str:
    """Safely construct Redis URL with specific DB index."""
    try:
        # Parse the URL
        parsed = urlparse(base_url)
        # Reconstruct path as /<db_index>
        new_path = f"/{db_index}"

        # Build new URL safely
        return urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                new_path,
                parsed.params,
                parsed.query,
                parsed.fragment,
            )
        )
    except Exception as e:
        logger.warning(
            f"Failed to parse Redis URL for rate limiting: {e}. Falling back to clean URL."
        )
        # Fallback for simple cases
        return f"redis://redis:6379/{db_index}"


def get_limiter(service_name: str = "main") -> Limiter:
    """Create and configure the rate limiter.

    In production (ENVIRONMENT=production):
    - Uses per-tenant rate limiting for multi-tenant SaaS
    - Uses Redis-backed storage for distributed rate limiting
    - Uses service-specific key prefix for namespace isolation
    - Ensures consistent limits across all worker processes

    Args:
        service_name: Service identifier for Redis key namespacing.
                     E.g., "main", "focusbuilder". Default: "main".

    Returns:
        Configured Limiter instance
    """
    if service_name in _limiter_cache:
        return _limiter_cache[service_name]

    environment = os.getenv("ENVIRONMENT", "development").lower()
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")

    # Create key function with service prefix for namespace isolation
    def prefixed_key_func(request: Request) -> str:
        """Generate rate limit key with service prefix."""
        base_key = get_tenant_identifier(request)
        return f"{service_name}:{base_key}"

    # Production: Use Redis for distributed rate limiting
    if environment == "production":
        # Use DB 2 for rate limiting to distinguish from cache/session
        storage_uri = get_redis_storage_url(redis_url, db_index=2)
        strategy = "moving-window"
        key_func = prefixed_key_func  # Per-tenant with service prefix
        logger.info(
            f"Rate limiter initialized: service={service_name}, storage=Redis DB 2, per-tenant"
        )
    else:
        # Development: Use in-memory storage (no prefix needed)
        storage_uri = "memory://"
        strategy = "fixed-window"
        key_func = get_remote_address  # Per-IP in development

    limiter = Limiter(
        key_func=key_func,
        default_limits=["100/minute"],
        storage_uri=storage_uri,
        strategy=strategy,
        headers_enabled=True,
    )
    _limiter_cache[service_name] = limiter
    return limiter


def parse_limit_string(limit_str: str) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Parse rate limit string like '10 per 1 minute' into components.

    Returns: Dict[str, Any] with 'limit' (int) and 'window' (str) keys  # TODO(TYPE): replace Any with concrete type
    """
    # Match patterns like "10 per 1 minute" or "100/minute"
    match = re.match(r"(\d+)\s*(?:per\s+\d+\s+)?(\w+)", str(limit_str))
    if match:
        return {
            "limit": int(match.group(1)),
            "window": match.group(2),
            "window_seconds": 60 if "minute" in match.group(2).lower() else 3600,
        }
    return {"limit": 100, "window": "minute", "window_seconds": 60}


async def rate_limit_exceeded_handler(request: Request, exc: Exception) -> Response:
    """Handle rate limit exceeded errors with standardized response.

    Implements REST API best practices with X-RateLimit-* headers
    for client-side throttling and proactive rate limit management.
    """
    # Extract request context for logging and metrics
    client_ip = "unknown"
    tenant_id = "unknown"
    endpoint = request.url.path

    try:
        client_ip = request.client.host if request.client else "unknown"
        # Only read tenant_id from state (set by TenantMiddleware from JWT -- ADR-003)
        if hasattr(request.state, "tenant_id"):
            tenant_id = str(request.state.tenant_id)
    except Exception:
        pass

    # Parse limit details
    rate_exc = cast(RateLimitExceeded, exc)
    limit_info = parse_limit_string(str(rate_exc.detail))
    reset_time = int(time.time()) + limit_info["window_seconds"]

    # Record metric for capacity planning
    rate_limit_violations.labels(
        endpoint=endpoint,
        tenant_id=tenant_id,
        limit_type="per_tenant" if tenant_id != "unknown" else "per_ip",
    ).inc()

    # Log for abuse tracking
    logger.warning(
        f"Rate limit exceeded: endpoint={endpoint}, tenant={tenant_id}, "
        f"ip={client_ip}, limit={rate_exc.detail}"
    )

    return JSONResponse(
        status_code=429,
        content={
            "error": "Rate limit exceeded",
            "detail": f"Maximum {limit_info['limit']} requests per {limit_info['window']}",
            "limit": str(rate_exc.detail),
            "retry_after_seconds": limit_info["window_seconds"],
            "documentation": "https://docs.sanskritisetu.org/api/rate-limits",
        },
        headers={
            "Retry-After": str(limit_info["window_seconds"]),
            "X-RateLimit-Limit": str(limit_info["limit"]),
            "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": str(reset_time),
            "X-RateLimit-Window": str(limit_info["window_seconds"]),
        },
    )
