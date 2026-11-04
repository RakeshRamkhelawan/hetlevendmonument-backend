# dsm:exempt reason: ADR-033 Laag 3 registry -- lazy import van router-modules is by design
"""Realtime / WebSocket domain registry (ADR-033 Laag 2, max 80 regels).

Covers: WebSocket channels, Co-Pilot WS/audit, notifications v1.
"""

from fastapi import FastAPI
from loguru import logger


def register(app: FastAPI) -> int:
    """Register realtime WebSocket and notification routers. Returns count."""
    count = 0

    # Generic WebSocket channel router
    try:
        from src.core.api.v1.websocket.router import router as websocket_router

        app.include_router(websocket_router, prefix="/api/v1")
        count += 1
    except Exception as e:
        logger.warning("Skipping WebSocket router: %s", e)

    # Co-Pilot WebSocket
    from src.core.copilot.api.chat_websocket import router as copilot_ws_router

    app.include_router(copilot_ws_router)
    count += 1

    # Co-Pilot audit (right-to-explanation)
    from src.core.copilot.api.audit_endpoints import router as copilot_audit_router

    app.include_router(
        copilot_audit_router,
        prefix="/api/v1/copilot/audit",
        tags=["Copilot Audit"],
    )
    count += 1

    # Notifications v1
    from src.core.api.v1.notifications.router import router as notifications_router

    app.include_router(notifications_router, prefix="/api/v1")
    count += 1

    # Tool-audit read endpoint (BPA-009 read-pad)
    from src.core.api.v1.tool_audit.router import router as tool_audit_router

    app.include_router(tool_audit_router, prefix="/api/v1")
    count += 1

    logger.debug("realtime routers registered: %s", count)
    return count
