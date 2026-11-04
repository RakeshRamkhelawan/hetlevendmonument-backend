"""
TwinHealthCheck -- ADR-025/026 subsystem health probe.

Checks:
    db      -- user_twin_consent table reachable
    redis   -- ping (optional; not_configured when client is None)
    llm     -- at least one provider key present
    bus     -- TwinEventBus singleton initialised

Each check runs with its own asyncio timeout so a single slow check
cannot stall the rest.  The outer caller sees the results dict immediately.
"""

import asyncio
import os
import time
from typing import Any

from loguru import logger


# Per-check wall-clock timeout (seconds)
_CHECK_TIMEOUT = 1.0


async def _check_db(db: Any) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    start = time.monotonic()
    try:
        from sqlalchemy import text

        await asyncio.wait_for(
            db.execute(text("SELECT 1 FROM user_twin_consent LIMIT 1")),
            timeout=_CHECK_TIMEOUT,
        )
        return {
            "status": "ok",
            "latency_ms": round((time.monotonic() - start) * 1000, 1),
        }
    except TimeoutError:
        return {"status": "timeout", "latency_ms": round(_CHECK_TIMEOUT * 1000)}
    except Exception as exc:
        return {
            "status": "error",
            "error": type(exc).__name__,
            "latency_ms": round((time.monotonic() - start) * 1000, 1),
        }


async def _check_redis(redis_client: Any) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    if redis_client is None:
        return {"status": "not_configured"}
    start = time.monotonic()
    try:
        await asyncio.wait_for(redis_client.ping(), timeout=_CHECK_TIMEOUT)
        return {
            "status": "ok",
            "latency_ms": round((time.monotonic() - start) * 1000, 1),
        }
    except TimeoutError:
        return {"status": "timeout", "latency_ms": round(_CHECK_TIMEOUT * 1000)}
    except Exception as exc:
        return {
            "status": "error",
            "error": type(exc).__name__,
            "latency_ms": round((time.monotonic() - start) * 1000, 1),
        }


def _check_llm() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Check that at least one LLM provider key is present."""
    providers = {
        "anthropic": bool(os.getenv("ANTHROPIC_API_KEY")),
        "google": bool(os.getenv("GOOGLE_API_KEY")),
        "ollama": bool(os.getenv("OLLAMA_BASE_URL")),
    }
    has_any = any(providers.values())
    return {
        "status": "configured" if has_any else "not_configured",
        "providers": providers,
    }


def _check_bus() -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Check that the TwinEventBus singleton is alive."""
    try:
        from src.core.learning.events.event_bus import _twin_event_bus_instance

        if _twin_event_bus_instance is None:
            return {"status": "not_initialised"}
        subscribers = _twin_event_bus_instance.subscriber_count("twin.intervention.suggested")
        return {"status": "ok", "subscribers_intervention": subscribers}
    except Exception as exc:
        return {"status": "error", "error": type(exc).__name__}


async def run_twin_health(
    db: Any,  # TODO(TYPE): replace Any with concrete type
    redis_client: Any | None = None,  # TODO(TYPE): replace Any with concrete type
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """
    Run all four twin sub-system checks concurrently.

    Args:
        db: SQLAlchemy AsyncSession
        redis_client: Optional Redis client (None -> "not_configured")

    Returns:
        Dict with keys db / redis / llm / bus and an overall "status"
        field: "ok" | "degraded" | "error".
    """
    db_result, redis_result = await asyncio.gather(
        _check_db(db),
        _check_redis(redis_client),
        return_exceptions=False,
    )
    llm_result = _check_llm()
    bus_result = _check_bus()

    checks = {
        "db": db_result,
        "redis": redis_result,
        "llm": llm_result,
        "bus": bus_result,
    }

    # Determine aggregate status
    error_statuses = {"error", "timeout"}
    if db_result["status"] in error_statuses:
        overall = "error"
    elif any(v.get("status") in error_statuses for v in [redis_result, llm_result, bus_result]):
        overall = "degraded"
    else:
        overall = "ok"

    logger.debug("twin_health_check", overall=overall, checks=checks)
    return {"status": overall, "checks": checks}
