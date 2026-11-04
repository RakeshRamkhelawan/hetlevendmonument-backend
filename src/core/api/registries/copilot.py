# dsm:exempt reason: ADR-033 Laag 3 registry -- lazy import van router-modules is by design
"""Copilot + AI Act + Enterprise OS registry (ADR-033 Laag 2, max 80 regels)."""

from fastapi import FastAPI
from loguru import logger


def register(app: FastAPI) -> int:
    """Register copilot turn, AI Act incidents and Enterprise OS routers. Returns count."""
    count = 0

    # Co-Pilot turn endpoint (ADR-027 bounded context)
    from src.core.copilot.api.turn_endpoint import router as copilot_turn_router

    app.include_router(copilot_turn_router, prefix="/api/v1/copilot", tags=["Copilot Turn"])
    count += 1

    # EU AI Act Article 62 incident reporting (ADR-031)
    from src.core.api.v1.ai_act.incident_router import router as ai_act_incident_router

    app.include_router(ai_act_incident_router, tags=["AI Act Compliance"])
    count += 1

    # Enterprise OS governance: Prana economy + A2A contracts
    for mod, tag in [
        ("src.core.api.v1.prana", "Prana"),
        ("src.core.api.v1.contracts", "A2A Contracts"),
    ]:
        try:
            import importlib

            m = importlib.import_module(mod)
            app.include_router(m.router, prefix="/api/v1", tags=[tag])
            count += 1
        except Exception as e:
            logger.warning("Skipping %s router: %s", tag, e)

    logger.debug("copilot/ai_act/enterprise_os routers registered: %s", count)
    return count
