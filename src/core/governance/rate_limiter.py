"""
GDPR Privacy Endpoint Rate Limiter

Lightweight rate limiting for privacy endpoints to prevent abuse.
InMemoryRateLimiter and the three agent_runtime decorators now live in
src.core.shared.rate_limiter (SP-DSM-006, Group B).
This module re-exports those symbols for backward compatibility and
defines governance-specific decorators on top.

Usage:
    from src.core.governance.rate_limiter import privacy_rate_limit

    @router.get("/export")
    @privacy_rate_limit(max_requests=3, window_seconds=3600)  # 3 per hour
    async def export_data(...)
"""

import asyncio
import functools
import logging
import time
from typing import Any, cast
from collections.abc import Callable

from fastapi import HTTPException, Request

# Re-exports from shared -- all callers can use either module path
from src.core.shared.rate_limiter import (
    InMemoryRateLimiter as InMemoryRateLimiter,
    _rate_limiter as _rate_limiter,
    _get_user_id_from_request as _get_user_id_from_request,
    privacy_rate_limit as privacy_rate_limit,
    vereis_request_parameter as vereis_request_parameter,
    geen_request_fout as geen_request_fout,
    consent_update_limit as consent_update_limit,
    ai_transparency_limit as ai_transparency_limit,
    reset_snapshot_rate_limits as _reset_shared_rate_limits,
)
from src.core.shared.limiet_sleutel import (
    client_adres,
    route_sleutel,
    tenant_en_gebruiker,
)

logger = logging.getLogger(__name__)

# Redis-backed rate limiter -- lazy-initialised on first CVA/copilot request.
# Lives in governance (not shared) to preserve DSM fan-out=0 invariant for shared.
# SEC-001/005: prevents multi-worker bypass (N Gunicorn workers sharing InMemory = N*limit).
#
# Loop-gebonden, zelfde patroon en zelfde gevolgen als src/core/database/redis.py's
# connectiepool (ADR-036 OP-156): zowel de gecachete RedisRateLimiter (die een client uit
# een specifieke loop vasthoudt) als het slot zelf overleven een nieuwe event loop niet.
_redis_rate_limiter: Any = None  # RedisRateLimiter | None
_redis_limiter_lock = asyncio.Lock()
_redis_limiter_loop: asyncio.AbstractEventLoop | None = None


def _vervang_de_limiter_bij_een_nieuwe_loop() -> None:
    """Gooi de gecachete limiter en het slot weg zodra we in een ANDERE event loop draaien.

    Zelfde reden als redis.py::_vervang_de_pool_bij_een_nieuwe_loop: de controle staat VOOR
    het verwerven van het slot, want dat slot is zelf het object dat vervangen moet worden.
    """
    global _redis_rate_limiter, _redis_limiter_lock, _redis_limiter_loop

    huidige = asyncio.get_running_loop()
    if _redis_rate_limiter is not None and _redis_limiter_loop is not huidige:
        logger.debug("Nieuwe event loop gedetecteerd: Redis-rate-limiter en slot worden vervangen")
        _redis_rate_limiter = None
        _redis_limiter_loop = None
        _redis_limiter_lock = asyncio.Lock()


async def _get_redis_limiter() -> Any:  # TODO(TYPE): replace Any with concrete type
    """Return a RedisRateLimiter if Redis is available, else None (triggers InMemory fallback)."""
    global _redis_rate_limiter, _redis_limiter_loop

    _vervang_de_limiter_bij_een_nieuwe_loop()

    if _redis_rate_limiter is not None:
        return _redis_rate_limiter
    async with _redis_limiter_lock:
        if _redis_rate_limiter is not None:  # double-checked locking
            return _redis_rate_limiter
        try:
            from src.core.database.redis import get_redis_client
            from src.core.security.rate_limiter import RedisRateLimiter

            client = await get_redis_client()
            _redis_rate_limiter = RedisRateLimiter(client)
            _redis_limiter_loop = asyncio.get_running_loop()
            logger.info("rate_limiter: Redis backend initialised for governance")
        except Exception as exc:
            logger.warning("rate_limiter: Redis unavailable, using InMemory fallback: %s", exc)
    return _redis_rate_limiter


def reset_snapshot_rate_limits() -> None:
    """Reset all rate limiter state (for testing only)."""
    global _redis_rate_limiter
    _reset_shared_rate_limits()
    _redis_rate_limiter = None


# Convenience decorators for common privacy endpoint patterns


def dsar_export_limit(
    func: Callable[..., Any],
) -> Callable[..., Any]:
    """Rate limit for DSAR export endpoint: 3 per hour."""
    return privacy_rate_limit(max_requests=3, window_seconds=3600)(func)


def dsar_delete_limit(
    func: Callable[..., Any],
) -> Callable[..., Any]:
    """Rate limit for DSAR delete endpoint: 1 per day."""
    return privacy_rate_limit(max_requests=1, window_seconds=86400)(func)


def consent_read_limit(
    func: Callable[..., Any],
) -> Callable[..., Any]:
    """Rate limit for consent status reads: 60 per minute."""
    return privacy_rate_limit(max_requests=60, window_seconds=60)(func)


def cva_chat_limit(
    func: Callable[..., Any],
) -> Callable[..., Any]:
    """Rate limit for CVA chat endpoints: 30 req/min, Redis-backed (SEC-001/005).

    Uses RedisRateLimiter (sliding window Lua script, atomic, cross-worker) when Redis is
    reachable. Falls back to InMemoryRateLimiter on any Redis failure so dev/test environments
    without Redis continue working. InMemory fallback is per-process (N-worker bypass), which
    is acceptable only in those environments.

    The key includes tenant_id via the request path; user identity is derived from
    request.state.user (JWT-set). X-User-ID header fallback removed (SEC-001, a4f25701).
    """
    vereis_request_parameter(func, "cva_chat_limit")
    _max_requests = 30
    _window_seconds = 60

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        global _redis_rate_limiter

        request: Request | None = None
        for v in (*args, *kwargs.values()):
            if isinstance(v, Request):
                request = v
                break
        if request is None:
            raise geen_request_fout("cva_chat_limit", func)

        user_id = _get_user_id_from_request(request)
        key = f"cva_chat:{user_id}:{route_sleutel(request)}"

        redis_limiter = await _get_redis_limiter()
        if redis_limiter is not None:
            try:
                allowed = await redis_limiter.check_limit(key, _max_requests, _window_seconds)
                if not allowed:
                    logger.warning("rate_limit: Redis denied %s", key)
                    raise HTTPException(
                        status_code=429,
                        detail={
                            "error": "Rate limit exceeded",
                            "message": (
                                f"Maximum {_max_requests} requests per "
                                f"{_window_seconds // 60} minutes allowed"
                            ),
                            "retry_after": _window_seconds,
                        },
                        headers={
                            "X-RateLimit-Limit": str(_max_requests),
                            "X-RateLimit-Remaining": "0",
                            "Retry-After": str(_window_seconds),
                        },
                    )
                return await func(*args, **kwargs)
            except HTTPException:
                raise
            except Exception as exc:
                _redis_rate_limiter = None
                logger.warning(
                    "rate_limiter: Redis check failed, falling back to InMemory: %s", exc
                )

        # InMemory fallback
        if not _rate_limiter.is_allowed(key, _max_requests, _window_seconds):
            remaining = _rate_limiter.get_remaining(key, _max_requests, _window_seconds)
            reset_time = _rate_limiter.get_reset_time(key, _window_seconds)
            logger.warning("rate_limit: InMemory denied %s", key)
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "Rate limit exceeded",
                    "message": (
                        f"Maximum {_max_requests} requests per "
                        f"{_window_seconds // 60} minutes allowed"
                    ),
                    "retry_after": (
                        int(reset_time - time.time()) if reset_time else _window_seconds
                    ),
                },
                headers={
                    "X-RateLimit-Limit": str(_max_requests),
                    "X-RateLimit-Remaining": str(remaining),
                    "Retry-After": str(
                        int(reset_time - time.time()) if reset_time else _window_seconds
                    ),
                },
            )
        return await func(*args, **kwargs)

    return wrapper


def copilot_turn_limit(
    max_requests: int = 30, window_seconds: int = 60
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Rate limit for /api/v1/copilot/turn: parametrized req/min, Redis-backed (SP-SEC-RL-001).

    Uses RedisRateLimiter (sliding window Lua, atomic, cross-worker) when Redis is reachable.
    Falls back to InMemoryRateLimiter if Redis is unavailable (dev/test without Redis).
    Key: copilot_turn:{tenant_id}:{user_id} -- derived from JWT/request.state, not headers.
    """

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        vereis_request_parameter(func, "copilot_turn_limit")

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            global _redis_rate_limiter

            request: Request | None = None
            for v in (*args, *kwargs.values()):
                if isinstance(v, Request):
                    request = v
                    break
            if request is None:
                raise geen_request_fout("copilot_turn_limit", func)

            identiteit = tenant_en_gebruiker(request)
            if identiteit is None:
                raise HTTPException(
                    status_code=401,
                    detail="Tenant context missing for rate-limit key",
                )
            key = f"copilot_turn:{identiteit[0]}:{identiteit[1]}"

            redis_limiter = await _get_redis_limiter()
            if redis_limiter is not None:
                try:
                    allowed = await redis_limiter.check_limit(key, max_requests, window_seconds)
                    if not allowed:
                        logger.warning("rate_limit: Redis denied %s", key)
                        raise HTTPException(
                            status_code=429,
                            detail={
                                "error": "Rate limit exceeded",
                                "message": (
                                    f"Maximum {max_requests} requests per "
                                    f"{window_seconds // 60} minutes allowed"
                                ),
                                "retry_after": window_seconds,
                            },
                            headers={
                                "X-RateLimit-Limit": str(max_requests),
                                "X-RateLimit-Remaining": "0",
                                "Retry-After": str(window_seconds),
                            },
                        )
                    return await func(*args, **kwargs)
                except HTTPException:
                    raise
                except Exception as exc:
                    _redis_rate_limiter = None
                    logger.warning(
                        "rate_limiter: Redis check failed, falling back to InMemory: %s", exc
                    )

            # InMemory fallback (per-process only -- acceptable for dev/test)
            if not _rate_limiter.is_allowed(key, max_requests, window_seconds):
                remaining = _rate_limiter.get_remaining(key, max_requests, window_seconds)
                reset_time = _rate_limiter.get_reset_time(key, window_seconds)
                logger.warning("rate_limit: InMemory denied %s", key)
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "Rate limit exceeded",
                        "message": (
                            f"Maximum {max_requests} requests per "
                            f"{window_seconds // 60} minutes allowed"
                        ),
                        "retry_after": (
                            int(reset_time - time.time()) if reset_time else window_seconds
                        ),
                    },
                    headers={
                        "X-RateLimit-Limit": str(max_requests),
                        "X-RateLimit-Remaining": str(remaining),
                        "Retry-After": str(
                            int(reset_time - time.time()) if reset_time else window_seconds
                        ),
                    },
                )
            return await func(*args, **kwargs)

        return wrapper

    return decorator


def human_review_limit(
    func: Callable[..., Any],
) -> Callable[..., Any]:
    """Rate limit for human review requests: 5 per day."""
    return privacy_rate_limit(max_requests=5, window_seconds=86400)(func)


def integration_read_limit(
    func: Callable[..., Any],
) -> Callable[..., Any]:
    """Rate limit for integration read endpoints: 60 per minute."""
    return privacy_rate_limit(max_requests=60, window_seconds=60)(func)


def integration_write_limit(
    func: Callable[..., Any],
) -> Callable[..., Any]:
    """Rate limit for integration write endpoints: 10 per minute."""
    return privacy_rate_limit(max_requests=10, window_seconds=60)(func)


def governance_read_limit(
    func: Callable[..., Any],
) -> Callable[..., Any]:
    """Rate limit for governance read endpoints: 60 per minute."""
    return privacy_rate_limit(max_requests=60, window_seconds=60)(func)


def governance_write_limit(
    func: Callable[..., Any],
) -> Callable[..., Any]:
    """Rate limit for governance write endpoints: 10 per minute."""
    return privacy_rate_limit(max_requests=10, window_seconds=60)(func)


def hr_import_read_limit(
    func: Callable[..., Any],
) -> Callable[..., Any]:
    """Rate limit for HR import read endpoints (BE-AGT-060): 60 per minute."""
    return privacy_rate_limit(max_requests=60, window_seconds=60)(func)


def hr_import_write_limit(
    func: Callable[..., Any],
) -> Callable[..., Any]:
    """Rate limit for HR import write endpoints (BE-AGT-060): 10 per minute."""
    return privacy_rate_limit(max_requests=10, window_seconds=60)(func)


def pack_activation_read_limit(
    func: Callable[..., Any],
) -> Callable[..., Any]:
    """Rate limit for the pack activation list (pakket aanzetten): 60 per minute."""
    return privacy_rate_limit(max_requests=60, window_seconds=60)(func)


def pack_activation_write_limit(
    func: Callable[..., Any],
) -> Callable[..., Any]:
    """Rate limit for switching a pack on or off (pakket aanzetten): 10 per minute."""
    return privacy_rate_limit(max_requests=10, window_seconds=60)(func)


def noodstop_read_limit(
    func: Callable[..., Any],
) -> Callable[..., Any]:
    """Rate limit for reading the emergency-stop state (noodstop per klant): 60 per minute."""
    return privacy_rate_limit(max_requests=60, window_seconds=60)(func)


def noodstop_write_limit(
    func: Callable[..., Any],
) -> Callable[..., Any]:
    """Rate limit for switching the emergency stop on or off (noodstop per klant): 10 per minute."""
    return privacy_rate_limit(max_requests=10, window_seconds=60)(func)


# ============================================================================
# Foundation Portal rate limiters (ADR-029)
# ============================================================================


def _ip_key(request: Request) -> str:
    """Rate-limit key based on the real client IP (`client_adres`).

    X-Forwarded-For is read from the RIGHT, skipping trusted proxies: the client sends its own
    values on the LEFT, so the first value picks its own bucket (gemeten 2026-10-27). It only
    counts when request.client.host is itself a private/trusted proxy (GHSA-c2r5-cfqr-c553).
    NEVER uses a client-controlled tenant-header. Zie `limiet_sleutel.client_adres` voor wat er
    over de proxy-stappen op staging NIET gemeten is.
    """
    adres = client_adres(request)
    return f"ip:{adres}" if adres else "ip:unknown"


def _email_key(request: Request) -> str:
    """Rate-limit key based on server-side parsed email.

    Endpoint MUST set request.state.parsed_email after Pydantic
    validation of the body.
    """
    email = getattr(request.state, "parsed_email", None)
    if not isinstance(email, str) or not email:
        return f"email:unknown:{_ip_key(request)}"
    return f"email:{email.strip().lower()}"


def portal_public_read_limit(
    func: Callable[..., Any],
) -> Callable[..., Any]:
    """Public read endpoints: 60 per minute, IP-keyed."""
    return privacy_rate_limit(max_requests=60, window_seconds=60, key_func=_ip_key)(func)


def portal_public_write_limit(
    func: Callable[..., Any],
) -> Callable[..., Any]:
    """Authenticated upload endpoints: 10 per minute, IP-keyed."""
    return privacy_rate_limit(max_requests=10, window_seconds=60, key_func=_ip_key)(func)


def portal_auth_limit(
    func: Callable[..., Any],
) -> Callable[..., Any]:
    """Magic-link request + verify: 5 per minute, IP-keyed (anti-brute-force)."""
    return privacy_rate_limit(max_requests=5, window_seconds=60, key_func=_ip_key)(func)


def portal_magic_link_email_limit(
    func: Callable[..., Any],
) -> Callable[..., Any]:
    """Anti-spam per e-mail: 3 per hour, email-keyed."""
    return privacy_rate_limit(max_requests=3, window_seconds=3600, key_func=_email_key)(func)


def portal_takedown_limit(
    func: Callable[..., Any],
) -> Callable[..., Any]:
    """Takedown requests: 5 per hour, IP-keyed."""
    return privacy_rate_limit(max_requests=5, window_seconds=3600, key_func=_ip_key)(func)


def portal_newsletter_limit(
    func: Callable[..., Any],
) -> Callable[..., Any]:
    """Newsletter subscribe: 3 per hour, IP-keyed."""
    return privacy_rate_limit(max_requests=3, window_seconds=3600, key_func=_ip_key)(func)


# ============================================================================
# Foundation Portal rate limiter DEPENDENCIES (FastAPI-native, ADR-029)
# Use these instead of decorators on routes to guarantee correct invocation.
# ============================================================================


async def _check_portal_limit(
    key: str, max_requests: int, window_seconds: int, message: str
) -> None:
    """Foundation Portal rate-limit check with Redis-first + InMemory fallback.

    Mirrors ``check_agent_execute_limit``: RedisRateLimiter when available,
    InMemoryRateLimiter fallback on any Redis failure. Prevents multi-worker
    bypass in production (SEC-001/005).
    """
    redis_limiter = await _get_redis_limiter()
    if redis_limiter is not None:
        try:
            allowed = await redis_limiter.check_limit(key, max_requests, window_seconds)
            if not allowed:
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "Rate limit exceeded",
                        "message": message,
                        "retry_after": window_seconds,
                    },
                    headers={
                        "X-RateLimit-Limit": str(max_requests),
                        "X-RateLimit-Remaining": "0",
                        "Retry-After": str(window_seconds),
                    },
                )
            return
        except HTTPException:
            raise
        except Exception as exc:
            _redis_rate_limiter = None
            logger.warning(
                "rate_limiter: Redis check failed for portal, falling back: %s: %s",
                type(exc).__name__,
                exc,
            )
    # InMemory fallback (per-process only -- acceptable for dev/test)
    if not _rate_limiter.is_allowed(key, max_requests, window_seconds):
        reset_time = _rate_limiter.get_reset_time(key, window_seconds)
        raise HTTPException(
            status_code=429,
            detail={
                "error": "Rate limit exceeded",
                "message": message,
                "retry_after": int(reset_time - time.time()) if reset_time else window_seconds,
            },
            headers={
                "X-RateLimit-Limit": str(max_requests),
                "X-RateLimit-Remaining": "0",
                "Retry-After": str(int(reset_time - time.time()) if reset_time else window_seconds),
            },
        )


async def require_portal_auth_rate_limit(request: Request) -> None:
    """Dependency: magic-link request + verify: 5 per minute, IP-keyed.

    Raises HTTPException(429) when the limit is exceeded.
    """
    await _check_portal_limit(
        f"portal_auth:{_ip_key(request)}", 5, 60, "Maximum 5 requests per minute allowed"
    )


async def require_portal_magic_link_email_rate_limit(request: Request) -> None:
    """Dependency: anti-spam per e-mail: 3 per hour, email-keyed.

    Raises HTTPException(429) when the limit is exceeded.
    """
    from src.core.shared.config import get_settings
    settings = get_settings()
    if settings.environment != "production":
        email = getattr(request.state, "parsed_email", "")
        if email and email.endswith("@levendmonument.nl"):
            return

    await _check_portal_limit(
        _email_key(request), 3, 3600, "Maximum 3 requests per hour allowed for this email"
    )


async def require_portal_takedown_rate_limit(request: Request) -> None:
    """Dependency: takedown requests: 5 per hour, IP-keyed.

    Raises HTTPException(429) when the limit is exceeded.
    """
    await _check_portal_limit(
        f"portal_takedown:{_ip_key(request)}", 5, 3600, "Maximum 5 takedown requests per hour allowed"
    )


async def require_portal_newsletter_rate_limit(request: Request) -> None:
    """Dependency: newsletter subscribe: 3 per hour, IP-keyed.

    Raises HTTPException(429) when the limit is exceeded.
    """
    await _check_portal_limit(
        f"portal_newsletter:{_ip_key(request)}",
        3,
        3600,
        "Maximum 3 newsletter subscriptions per hour allowed",
    )


def _snapshot_key(request: Request) -> str:
    """Tenant-scoped rate-limit key for snapshot endpoints.

    Prevents cross-tenant rate-limit collisions (User #1 in Tenant A
    cannot exhaust the bucket of User #1 in Tenant B).
    """
    return f"snapshot:{_get_user_id_from_request(request)}:{route_sleutel(request)}"


def snapshot_read_limit(
    func: Callable[..., Any],
) -> Callable[..., Any]:
    """Rate limit for sync snapshot read endpoints: 120 per minute."""
    return privacy_rate_limit(max_requests=120, window_seconds=60, key_func=_snapshot_key)(func)


def snapshot_write_limit(
    func: Callable[..., Any],
) -> Callable[..., Any]:
    """Rate limit for sync snapshot write endpoints: 20 per minute."""
    return privacy_rate_limit(max_requests=20, window_seconds=60, key_func=_snapshot_key)(func)


_AGENT_EXECUTE_MAX = 10
_AGENT_EXECUTE_WINDOW = 60


async def check_copilot_turn_limit(
    tenant_id: int | None,
    user_id: int | str | None,
    max_requests: int = 30,
    window_seconds: int = 60,
) -> bool:
    """Directly-callable copilot-turn rate check for the WebSocket path (SEC-AGT-003).

    Mirrors the ``copilot_turn_limit`` decorator (same key + backends) but returns a
    bool instead of raising, so the WS handler can emit an error frame rather than an
    HTTP 429. Key: copilot_turn:{tenant_id}:{user_id} -- derived from JWT, never a header.
    Returns True when the request is allowed, False when the limit is exceeded.
    """
    key = f"copilot_turn:{tenant_id}:{user_id}"
    redis_limiter = await _get_redis_limiter()
    if redis_limiter is not None:
        try:
            return cast(bool, await redis_limiter.check_limit(key, max_requests, window_seconds))
        except Exception as exc:
            logger.warning(
                "rate_limiter: Redis check failed for copilot_turn (WS), falling back: %s: %s",
                type(exc).__name__,
                exc,
            )
    return _rate_limiter.is_allowed(key, max_requests, window_seconds)


async def check_agent_execute_limit(tenant_id: int | str | None, user_id: int | str | None) -> None:
    """Enforce agent execute rate limit: 10/min per tenant+user (RC-009a)."""
    key = f"agent_execute:{tenant_id}:{user_id}"
    redis_limiter = await _get_redis_limiter()
    if redis_limiter is not None:
        try:
            allowed = await redis_limiter.check_limit(
                key, _AGENT_EXECUTE_MAX, _AGENT_EXECUTE_WINDOW
            )
            if not allowed:
                raise HTTPException(
                    status_code=429,
                    detail={
                        "code": "RATE_LIMIT_EXCEEDED",
                        "message": "Agent execute rate limit exceeded. Max 10 per minute.",
                    },
                    headers={"Retry-After": str(_AGENT_EXECUTE_WINDOW)},
                )
            return
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning(
                "rate_limiter: Redis check failed for agent_execute, falling back: %s: %s",
                type(exc).__name__,
                exc,
            )
    if not _rate_limiter.is_allowed(key, _AGENT_EXECUTE_MAX, _AGENT_EXECUTE_WINDOW):
        raise HTTPException(
            status_code=429,
            detail={
                "code": "RATE_LIMIT_EXCEEDED",
                "message": "Agent execute rate limit exceeded. Max 10 per minute.",
            },
            headers={"Retry-After": str(_AGENT_EXECUTE_WINDOW)},
        )


def agent_execute_limit(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator: 10 agent-executes/min per tenant+user, finds Request via isinstance (RC-009a)."""
    vereis_request_parameter(func, "agent_execute_limit")

    @functools.wraps(func)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        request = None
        for v in (*args, *kwargs.values()):
            if isinstance(v, Request):
                request = v
                break
        if request is None:
            raise geen_request_fout("agent_execute_limit", func)
        identiteit = tenant_en_gebruiker(request)
        if identiteit is None:
            raise HTTPException(
                status_code=401,
                detail="Tenant context missing for rate-limit key",
            )
        await check_agent_execute_limit(identiteit[0], identiteit[1])
        return await func(*args, **kwargs)

    return wrapper
