"""Optional routers registry -- miscellaneous routers with optional dependencies (ADR-033 Laag 2, max 80 regels)."""

from fastapi import FastAPI
from loguru import logger


def register(app: FastAPI) -> int:
    """Register optional routers with error handling. Returns count."""
    count: int = 0

    try:
        # HITL is een APART bestand, niet `tool_broker/router.py` -- ADR-036 OP-37/OP-61.
        from src.core.api.v1.tool_broker import domain_router as tool_broker_domain_router
        from src.core.api.v1.tool_broker.hitl_router import router as tool_broker_hitl_router

        app.include_router(tool_broker_domain_router)
        app.include_router(tool_broker_hitl_router)
        count += 2
    except Exception as e:  # ERROR i.p.v. WARNING: zonder deze routers is HITL-goedkeuring weg (OP-74)
        logger.error("HITL-goedkeuring onbereikbaar: %s: %s", type(e).__name__, e)

    try:
        from src.core.api.v1.websocket_hitl import router as hitl_ws_router

        app.include_router(hitl_ws_router, tags=["HITL WebSocket"])
        count += 1
    except Exception as e:
        logger.warning("Skipping HITL WebSocket router: %s", e)

    try:
        from src.core.api.v1.autonomous import domain_router as autonomous_domain_router

        app.include_router(autonomous_domain_router)
        count += 1
    except Exception as e:
        logger.warning("Skipping Autonomous router: %s", e)

    try:
        from src.core.api.v1.learning.router import router as learning

        app.include_router(learning, prefix="/api/v1", tags=["Learning"])
        count += 1
    except Exception as e:
        logger.warning("Skipping Learning router: %s", e)

    try:
        from src.core.api.monitoring_dashboard_endpoints import router as dashboard

        app.include_router(dashboard, prefix="/api", tags=["Dashboard"])
        count += 1
    except Exception as e:
        logger.warning("Skipping Dashboard router: %s", e)

    try:
        from src.core.api.v1.dashboard.router import router as dashboard_v1

        app.include_router(dashboard_v1, prefix="/api/v1", tags=["Dashboard"])
        count += 1
    except Exception as e:
        logger.warning("Skipping Dashboard v1 router: %s", e)

    try:
        from src.api.v1.endpoints.performance import router as perf

        app.include_router(perf, prefix="/api/v1", tags=["Performance"])
        count += 1
    except Exception as e:
        logger.warning("Skipping Performance router: %s", e)

    try:
        from src.api.v1.endpoints.digital_twin import router as digital_twin_router

        app.include_router(digital_twin_router, prefix="/api/v1", tags=["Digital Twin"])
        count += 1
        logger.info("Digital Twin router registered at /api/v1/learning")
    except Exception as e:
        logger.warning("Skipping Digital Twin router: %s", e)

    logger.debug("optional routers registered: %s", count)
    return count
