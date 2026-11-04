"""Shared in-memory rate limiter -- no governance deps.

InMemoryRateLimiter, privacy_rate_limit(), and the three decorators
consumed by agent_runtime (audit_endpoints, turn_endpoint, factory)
live here so those callers can import from shared instead of governance.

governance/rate_limiter.py re-exports these and adds governance-specific
decorators (dsar_*, consent_read_limit, etc.) that are not needed by
agent_runtime code.
"""

from __future__ import annotations

import functools
import inspect
import logging
import time
from collections import defaultdict
from typing import Any
from collections.abc import Callable, Mapping

from fastapi import HTTPException, Request

from src.core.shared.limiet_sleutel import (
    client_adres,
    route_sleutel,
    tenant_en_gebruiker,
)

logger = logging.getLogger(__name__)


class InMemoryRateLimiter:
    """Simple in-memory rate limiter for privacy endpoints."""

    def __init__(self) -> None:
        self._requests: defaultdict[str, list[float]] = defaultdict(list)
        self._last_cleanup = time.time()
        self._cleanup_interval = 300

    def _cleanup_old_entries(self) -> None:
        now = time.time()
        if now - self._last_cleanup < self._cleanup_interval:
            return
        cutoff = now - 86400
        keys_to_remove = []
        for key, timestamps in self._requests.items():
            self._requests[key] = [ts for ts in timestamps if ts > cutoff]
            if not self._requests[key]:
                keys_to_remove.append(key)
        for key in keys_to_remove:
            del self._requests[key]
        self._last_cleanup = now
        logger.debug("Rate limiter cleanup: removed %d empty keys", len(keys_to_remove))

    def is_allowed(self, key: str, max_requests: int, window_seconds: int) -> bool:
        self._cleanup_old_entries()
        now = time.time()
        window_start = now - window_seconds
        requests = self._requests[key]
        recent_requests = [ts for ts in requests if ts > window_start]
        self._requests[key] = recent_requests
        if len(recent_requests) >= max_requests:
            return False
        recent_requests.append(now)
        return True

    def get_remaining(self, key: str, max_requests: int, window_seconds: int) -> int:
        now = time.time()
        window_start = now - window_seconds
        requests = self._requests.get(key, [])
        recent_requests = [ts for ts in requests if ts > window_start]
        return max(0, max_requests - len(recent_requests))

    def get_reset_time(self, key: str, window_seconds: int) -> float | None:
        requests = self._requests.get(key, [])
        if not requests:
            return None
        return min(requests) + window_seconds


_rate_limiter = InMemoryRateLimiter()


def _get_user_id_from_request(request: Request) -> str:
    """`{tenant}:{gebruikers-id}` van de aanvrager, of het adres bij een anonieme route.

    Het id is het NUMERIEKE id uit `tenant_en_gebruiker`, nooit de ruwe `sub` (twee vormen). Een
    aanvrager met tenant maar zonder vast te stellen id geeft een 401. Zonder tenant is het een
    anonieme route en telt het echte adres (`client_adres`).
    """
    identiteit = tenant_en_gebruiker(request)
    if identiteit is not None:
        return f"{identiteit[0]}:{identiteit[1]}"
    return client_adres(request) or "unknown"


def _klasse_uit_naam(naam: str, wereld: Mapping[str, object]) -> object | None:
    """Los een string-annotatie (`Request`, `starlette.requests.Request`) op in `wereld`.

    Zonder `eval`: alleen een punt-gescheiden naam, opgezocht in de modulenaamruimte van de functie.
    """
    delen = naam.split(".")
    if not all(deel.isidentifier() for deel in delen):
        return None
    gevonden: object | None = wereld.get(delen[0])
    for deel in delen[1:]:
        gevonden = getattr(gevonden, deel, None)
    return gevonden


def vereis_request_parameter(func: Callable[..., Any], decorator_naam: str) -> None:
    """Faal bij het DECOREREN als `func` geen parameter heeft die echt een `Request` is.

    De limietdecorators zoeken de `Request` tussen de argumenten en voerden de route zonder limiet
    uit als ze er geen vonden: een route zonder `Request` kreeg dus stilletjes geen limiet (38 van
    109 routes, gemeten 2026-10-25). Een fout bij het importeren van de module is luid; een
    limiet die niets doet is dat niet.

    Het gaat om de KLASSE, niet om de naam: een eigen klasse die `Request` heet voldoet niet. Een
    string-annotatie (`from __future__ import annotations`) wordt opgelost in de modulenaamruimte
    van de functie; wijst hij nergens heen, dan telt hij niet (FastAPI zou er ook geen `Request`
    van maken).
    """
    wereld = getattr(inspect.unwrap(func), "__globals__", {})
    for parameter in inspect.signature(func).parameters.values():
        annotatie: object = parameter.annotation
        if isinstance(annotatie, str):
            annotatie = _klasse_uit_naam(annotatie, wereld)
        if isinstance(annotatie, type) and issubclass(annotatie, Request):
            return
    raise TypeError(
        f"{decorator_naam} op {func.__module__}.{func.__qualname__}: de functie heeft geen "
        "parameter die echt een starlette Request is, dus de limiet zou stilletjes niets doen. "
        "Voeg `request: Request` toe (de klasse uit fastapi of starlette.requests)."
    )


def geen_request_fout(decorator_naam: str, func: Callable[..., Any]) -> RuntimeError:
    """De fout voor een gedecoreerde functie die zonder `Request` wordt aangeroepen.

    Dat is een programmeerfout (FastAPI geeft altijd een `Request` mee, en bij het decoreren is
    gecontroleerd dat de parameter bestaat): een duidelijke fout, geen ongelimiteerde doorgang.
    """
    return RuntimeError(
        f"{decorator_naam} op {func.__module__}.{func.__qualname__} is aangeroepen zonder Request: "
        "de limiet zou niet gelden en de functie is niet uitgevoerd."
    )


def privacy_rate_limit(
    max_requests: int = 10,
    window_seconds: int = 60,
    key_func: Callable[[Request], str] | None = None,
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator to apply rate limiting to privacy endpoints."""

    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        vereis_request_parameter(func, "privacy_rate_limit")

        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            request: Request | None = None
            if kwargs:
                for arg in kwargs.values():
                    if isinstance(arg, Request):
                        request = arg
                        break
            if request is None and args:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break
            if request is None:
                raise geen_request_fout("privacy_rate_limit", func)
            if key_func:
                key = key_func(request)
            else:
                user_key = _get_user_id_from_request(request)
                key = f"{user_key}:{route_sleutel(request)}"

            if not _rate_limiter.is_allowed(key, max_requests, window_seconds):
                remaining = _rate_limiter.get_remaining(key, max_requests, window_seconds)
                reset_time = _rate_limiter.get_reset_time(key, window_seconds)
                logger.warning("Rate limit exceeded for %s", key)
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

        # Preserve signature for FastAPI dependency introspection.
        wrapper.__signature__ = inspect.signature(func)  # type: ignore[attr-defined]
        return wrapper

    return decorator


def consent_update_limit(
    func: Callable[..., Any],
) -> Callable[..., Any]:
    """Rate limit for consent updates: 10 per minute."""
    return privacy_rate_limit(max_requests=10, window_seconds=60)(func)


def ai_transparency_limit(
    func: Callable[..., Any],
) -> Callable[..., Any]:
    """Rate limit for AI transparency endpoints: 30 per minute."""
    return privacy_rate_limit(max_requests=30, window_seconds=60)(func)


def copilot_turn_limit(
    max_requests: int = 30, window_seconds: int = 60
) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Tenant-keyed rate-limit for /api/v1/copilot/turn (M-3 fix)."""

    def key_func(request: Request) -> str:
        identiteit = tenant_en_gebruiker(request)
        if identiteit is None:
            raise HTTPException(
                status_code=401,
                detail="Tenant context missing for rate-limit key",
            )
        return f"copilot_turn:{identiteit[0]}:{identiteit[1]}"

    return privacy_rate_limit(max_requests, window_seconds, key_func)


def reset_snapshot_rate_limits() -> None:
    """Reset snapshot rate limiter state (for testing only)."""
    _rate_limiter._requests.clear()
    _rate_limiter._last_cleanup = 0.0
