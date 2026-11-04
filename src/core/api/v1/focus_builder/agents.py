"""
# orphan:exempt reason: Laag 1 sub-router, registered transitively via composite router.py (ADR-033)
GET /api/v1/focus-builder/agents

Returns three tiers of agents for the current tenant:
- live: Activepieces apps with existing credentials (LIVE badge)
- internal: SanskritiSetu internal agents (workflow generator, etc.)
- available: All known AP pieces without credentials ("connect first")

Redis cache: focus_builder:agents:tenant_{tenant_id}  (TTL 5 min)
AP timeout: 3s -- on timeout returns live=[], ap_unavailable=True
No AP connection for the tenant: live=[], ap_unavailable=True, ap_niet_ingesteld=True
"""

import asyncio
import json
from typing import Any, cast

from fastapi import APIRouter, Depends
from loguru import logger

from src.core.activepieces.tenant_utils import fetch_live_connections
from src.core.activepieces.verbinding import ApVerbindingOntbreektError
from src.core.auth.api_deps import get_current_user_dependency
from src.core.middleware.tenant_context import get_current_tenant_id

agents_router = APIRouter()


# Capability category tags per AP piece name fragment
_CATEGORY_MAP: dict[str, str] = {
    "teams": "notification",
    "slack": "notification",
    "discord": "notification",
    "gmail": "email",
    "outlook": "email",
    "smtp": "email",
    "google-calendar": "scheduler",
    "outlook-calendar": "scheduler",
    "sharepoint": "storage",
    "google-drive": "storage",
    "dropbox": "storage",
    "asana": "crm",
    "jira": "crm",
    "hubspot": "crm",
    "salesforce": "crm",
    "github": "social",
    "twitter": "social",
    "instagram": "social",
}

AP_TIMEOUT = 3.0
CACHE_TTL = 300  # 5 minutes


def _get_category(piece_id: str) -> str:
    for fragment, category in _CATEGORY_MAP.items():
        if fragment in piece_id.lower():
            return category
    return "other"


async def _get_redis_cache(key: str) -> Any:  # TODO(TYPE): replace Any with concrete type
    """Attempt to read from Redis; return None on any error."""
    try:
        from src.core.shared.redis_client import get_redis

        r = await get_redis()
        val = await r.get(key)
        return json.loads(val) if val else None
    except Exception:
        return None


async def _set_redis_cache(
    key: str, value: Any, ttl: int = CACHE_TTL  # TODO(TYPE): replace Any with concrete type
) -> None:  # TODO(TYPE): replace Any with concrete type
    try:
        from src.core.shared.redis_client import get_redis

        r = await get_redis()
        await r.set(key, json.dumps(value), ex=ttl)
    except Exception:
        pass


@agents_router.get("/agents")
async def get_agents(
    tenant_id: int = Depends(get_current_tenant_id),
    current_user: Any = Depends(  # TODO(TYPE): replace Any with concrete type
        get_current_user_dependency
    ),  # TODO(TYPE): replace Any with concrete type
) -> dict[str, Any]:  # TODO(TYPE): replace Any with concrete type
    """Return agent tiers for the current tenant."""
    # Handle None tenant_id gracefully (e.g. missing context in tests)
    effective_tenant_id = tenant_id if tenant_id is not None else 0

    cache_key = f"focus_builder:agents:tenant_{effective_tenant_id}"

    # Cache hit
    cached = await _get_redis_cache(cache_key)
    if cached:
        return cast(dict[str, Any], cached)  # TODO(TYPE): replace Any with concrete type

    # Fetch live connections from AP, through the one door (ActivePiecesClient) with the connection
    # of THIS tenant. No fallback project: a tenant without a connection is reported as such.
    ap_unavailable = False
    ap_niet_ingesteld = False
    live_raw: list[dict[str, Any]] = []  # TODO(TYPE): replace Any with concrete type
    try:
        live_raw = cast(
            list[dict[str, Any]],  # TODO(TYPE): replace Any with concrete type
            await asyncio.wait_for(fetch_live_connections(effective_tenant_id), timeout=AP_TIMEOUT),
        )
    except ApVerbindingOntbreektError:
        ap_unavailable = True
        ap_niet_ingesteld = True
    except Exception as exc:
        logger.warning(
            "agents_ap_fetch_failed tenant=%s: %s: %s",
            effective_tenant_id,
            type(exc).__name__,
            exc,
            exc_info=True,
        )
        ap_unavailable = True

    # Build live tier
    live_ids = {conn.get("appName", "").lower() for conn in live_raw}
    live = [
        {
            "id": conn.get("appName", "").lower(),
            "name": conn.get("appName", ""),
            "category": _get_category(conn.get("appName", "")),
            "icon": "plug",
            "source": "activepieces",
            "is_connected": True,
        }
        for conn in live_raw
        if conn.get("appName")
    ]

    # Build available tier (known pieces not in live)
    known_pieces = list(_CATEGORY_MAP.keys())
    available = [
        {
            "id": piece,
            "name": piece.replace("-", " ").title(),
            "category": _get_category(piece),
            "icon": "link",
            "source": "activepieces",
            "is_connected": False,
        }
        for piece in known_pieces
        if piece not in live_ids
    ]

    from src.core.api.v1.focus_builder.dependencies import (
        _get_internal_agents,
    )  # own-domain -- ADR-033

    result: dict[str, Any] = {  # TODO(TYPE): replace Any with concrete type
        "live": live,
        "internal": _get_internal_agents(),
        "available": available,
        "ap_unavailable": ap_unavailable,
        "ap_niet_ingesteld": ap_niet_ingesteld,
    }

    await _set_redis_cache(cache_key, result)
    return result
