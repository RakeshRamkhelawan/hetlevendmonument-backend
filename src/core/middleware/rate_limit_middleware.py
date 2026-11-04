from __future__ import annotations

"""
SC-6.2: Global API Rate Limiting
Token bucket rate limiter with Redis backend.
"""

import logging
import os
import time
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any, Optional

from fastapi import HTTPException, Request, status
from sqlalchemy import select
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from src.core.database.database import db_manager
from src.core.database.tenant_query_filter import TenantFilterBypass
from src.core.models.rbac_models import Tenant
from src.core.services.subscription_cache import TenantSubscriptionCache
from src.core.shared.redis_client import get_redis

if TYPE_CHECKING:
    import redis.asyncio as redis

logger = logging.getLogger(__name__)


def resolve_rate_limit_for_tier(tier: str | None) -> int:
    """Resolve per-minute rate limit based on subscription tier."""
    if not tier:
        return 60
    tier_lower = tier.lower()
    if tier_lower == "enterprise":
        return 5000
    elif tier_lower == "pro":
        return 360
    elif tier_lower == "starter":
        return 120
    return 60


# SECURITY FIX: Rate limiting fail-closed configuration
# In production, if Redis is unavailable, reject requests instead of allowing them
RATE_LIMIT_FAIL_CLOSED = os.getenv("ENVIRONMENT", "development").lower() == "production"

# Try to import Redis
_redis_module: Any = None
try:
    import redis.asyncio as _redis_module

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


class RateLimitExceeded(HTTPException):
    """Exception raised when rate limit is exceeded."""

    def __init__(self, retry_after: int = 60) -> None:
        super().__init__(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please try again later.",
            headers={"Retry-After": str(retry_after)},
        )


class TokenBucketRateLimiter:
    """
    SC-6.2: Token bucket rate limiter with Redis backend.

    Provides global and per-user rate limiting.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        requests_per_minute: int = 60,
        requests_per_hour: int = 1000,
        burst_size: int = 10,
    ) -> None:
        self.redis_url = redis_url
        self.requests_per_minute = requests_per_minute
        self.requests_per_hour = requests_per_hour
        self.burst_size = burst_size
        self._redis: redis.Redis | None = None  # type: ignore[type-arg]
        self._connected = False

    async def connect(self) -> bool:
        """Connect to Redis."""
        if not REDIS_AVAILABLE or _redis_module is None:
            logger.warning("Redis not available. Rate limiting disabled.")
            return False

        try:
            redis_client = _redis_module.from_url(self.redis_url)
            await redis_client.ping()
            self._redis = redis_client
            self._connected = True
            logger.info("Rate limiter connected to Redis")
            return True
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self._connected = False
            return False

    async def is_allowed(
        self, key: str, limit: int | None = None, window_seconds: int = 60
    ) -> tuple[bool, int, int]:
        """
        Check if request is allowed under rate limit.

        Args:
            key: Unique identifier (IP, user ID, API key)
            limit: Max requests in window
            window_seconds: Time window in seconds

        Returns: Tuple of (allowed, remaining, reset_time)
        """
        limit = limit or self.requests_per_minute

        if not self._connected:
            # SECURITY FIX: Fail closed in production, fail open in development
            if RATE_LIMIT_FAIL_CLOSED:
                logger.error(
                    "Rate limiter not connected to Redis - rejecting request (fail-closed)"
                )
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Service temporarily unavailable. Please try again later.",
                )
            # Development: fail open with warning
            logger.warning("Rate limiter not connected - allowing request (fail-open for dev)")
            return True, limit, 0

        try:
            now = int(time.time())
            window_key = f"ratelimit:{key}:{now // window_seconds}"

            assert self._redis is not None
            # Increment counter
            current = await self._redis.incr(window_key)

            # Set expiry on first request
            if current == 1:
                await self._redis.expire(window_key, window_seconds)

            remaining = max(0, limit - current)
            reset_time = (now // window_seconds + 1) * window_seconds

            if current > limit:
                return False, 0, reset_time

            return True, remaining, reset_time

        except Exception as e:
            logger.error("Rate limit check failed: %s", e)
            # SECURITY FIX: Fail closed in production, fail open in development
            if RATE_LIMIT_FAIL_CLOSED:
                logger.error("Rate limit check error - rejecting request (fail-closed)")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Service temporarily unavailable. Please try again later.",
                )
            # Development: fail open with warning
            logger.warning("Rate limit check error - allowing request (fail-open for dev)")
            return True, limit, 0

    async def get_usage(
        self, key: str
    ) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
        """Get current rate limit usage for a key."""
        if not self._connected:
            return {"error": "Rate limiter not connected"}

        now = int(time.time())
        minute_key = f"ratelimit:{key}:{now // 60}"
        hour_key = f"ratelimit:{key}:{now // 3600}"

        try:
            assert self._redis is not None
            minute_count = int(await self._redis.get(minute_key) or 0)
            hour_count = int(await self._redis.get(hour_key) or 0)

            return {
                "minute": {
                    "used": minute_count,
                    "limit": self.requests_per_minute,
                    "remaining": max(0, self.requests_per_minute - minute_count),
                },
                "hour": {
                    "used": hour_count,
                    "limit": self.requests_per_hour,
                    "remaining": max(0, self.requests_per_hour - hour_count),
                },
            }
        except Exception as e:
            return {"error": str(e)}


class RateLimitMiddleware:
    """
    SC-6.2: FastAPI middleware for rate limiting (pure ASGI).

    CRITICAL FIX: Replaced BaseHTTPMiddleware with pure ASGI pattern
    to fix MissingGreenlet errors caused by anyio task groups not
    propagating greenlet context (Starlette 0.49.3+).
    """

    EXCLUDED_PATHS = {
        "/health",
        "/ready",
        "/metrics",
        "/docs",
        "/openapi.json",
    }
    EXCLUDED_PREFIXES = ("/health/", "/docs/")

    def __init__(
        self,
        app: ASGIApp,
        rate_limiter: TokenBucketRateLimiter,
        requests_per_minute: int = 60,
    ) -> None:
        self.app = app
        self.rate_limiter = rate_limiter
        self.requests_per_minute = requests_per_minute

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        # Pass through non-HTTP requests unchanged.
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive)
        path = request.url.path

        # Skip excluded paths (exact match or prefix match)
        if path in self.EXCLUDED_PATHS or any(path.startswith(p) for p in self.EXCLUDED_PREFIXES):
            await self.app(scope, receive, send)
            return

        # Determine rate limit key and tenant context
        key = self._resolve_rate_limit_key(request)
        tenant_id = self._extract_tenant_id_from_request(request)
        limit = self.requests_per_minute

        if tenant_id:
            try:
                cache = TenantSubscriptionCache(tenant_id=tenant_id)
                sub = await cache.get()

                if sub:
                    limit = resolve_rate_limit_for_tier(sub.get("tier"))
                else:
                    # Fallback to DB
                    async with db_manager.get_session() as db:
                        with TenantFilterBypass():
                            result = await db.execute(select(Tenant).where(Tenant.id == tenant_id))
                            tenant = result.scalar_one_or_none()
                            if tenant:
                                tier = tenant.subscription_tier or "free"
                                status_str = tenant.subscription_status or "active"
                                await cache.set(tier=tier, status=status_str)
                                limit = resolve_rate_limit_for_tier(tier)
            except Exception:
                logger.error(
                    "Failed to resolve dynamic rate limit, using safe default",
                    exc_info=True,
                )
                limit = self.requests_per_minute

        # Check rate limit
        allowed, remaining, reset_time = await self.rate_limiter.is_allowed(key, limit)

        if not allowed:
            retry_after = max(1, reset_time - int(time.time()))
            response = JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "Rate limit exceeded. Please try again later."},
                headers={"Retry-After": str(retry_after)},
            )
            await response(scope, receive, send)
            return

        # Wrap send to add rate limit headers
        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-ratelimit-limit", str(limit).encode()))
                headers.append((b"x-ratelimit-remaining", str(remaining).encode()))
                headers.append((b"x-ratelimit-reset", str(reset_time).encode()))
                message["headers"] = headers
            await send(message)

        # Process request
        await self.app(scope, receive, send_wrapper)

    def _resolve_rate_limit_key(self, request: Request) -> str:
        """Build a rate-limit key from user ID (JWT) or client IP."""
        tenant_id = self._extract_tenant_id_from_request(request)
        if tenant_id:
            return f"user:{tenant_id}"

        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            # Use the rightmost IP if the request came through a trusted proxy.
            # In production with Traefik, the last IP is the one added by Traefik.
            client_ip = forwarded.split(",")[-1].strip()
        else:
            client_ip = request.client.host if request.client else "unknown"
        return f"ip:{client_ip}"

    def _extract_tenant_id_from_request(self, request: Request) -> int | None:
        """Extract tenant_id from the JWT Authorization header.

        This allows dynamic rate limiting based on subscription tier even
        though FastAPI dependencies run after middleware.
        """
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return None
        token = auth_header[7:]
        if not token:
            return None
        try:
            from src.core.auth.jwt_handler import jwt_handler

            payload = jwt_handler.verify_token(token)
            if payload and "tenant_id" in payload:
                return int(payload["tenant_id"])
        except Exception:
            # Invalid token -> fall back to IP-based limiting
            pass
        return None


# Singleton instance
rate_limiter = TokenBucketRateLimiter()
