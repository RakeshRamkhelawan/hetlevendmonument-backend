"""Scheduling REST routers registry -- all non-WebSocket scheduling routes (ADR-033 Laag 2, max 80 regels)."""

from fastapi import FastAPI
from loguru import logger

_ROUTES = [
    ("src.core.scheduling.api.routes", "scheduling_router", "/api/v1", ["Scheduling"]),
    (
        "src.core.scheduling.api.integration_routes",
        "integ_router",
        "/api/v1",
        ["Scheduling Integrations"],
    ),
    ("src.core.scheduling.api.smart_routes", "smart_router", "/api/v1", ["Smart Scheduling"]),
    (
        "src.core.scheduling.api.webhook_routes",
        "webhook_router",
        "/api/v1/scheduling",
        ["Calendar Webhooks"],
    ),
    (
        "src.core.scheduling.api.conflict_routes",
        "conflict_router",
        "/api/v1",
        ["Conflict Resolution"],
    ),
    ("src.core.scheduling.api.partner_routes", "partner_router", "/api/v1", ["Design Partners"]),
    ("src.core.scheduling.api.mobile_routes", "mobile_router", "/api/v1", ["Mobile Scheduling"]),
    ("src.core.scheduling.api.voice_routes", "voice_router", "/api/v1", ["Voice Scheduling"]),
]


def register(app: FastAPI) -> int:
    """Register scheduling REST routers. Returns count."""
    import importlib

    count: int = 0
    for module_path, _, prefix, tags in _ROUTES:
        try:
            mod = importlib.import_module(module_path)
            router = mod.router
            app.include_router(router, prefix=prefix, tags=tags)  # type: ignore[arg-type]
            count += 1
        except Exception as e:
            logger.warning("Skipping %s router: %s", module_path, e)
    return count
