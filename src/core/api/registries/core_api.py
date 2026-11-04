"""Core API domain registry (ADR-033 Laag 2, max 80 regels)."""

from fastapi import FastAPI
from loguru import logger


def register(app: FastAPI) -> int:
    """Register core API routers. Returns count."""
    count = 0

    from src.core.api.analytics_endpoints import router as analytics_router  # type: ignore[attr-defined]
    from src.core.api.v1.copilot_intent import domain_router as copilot_intent_domain_router
    from src.core.api.demo_endpoints import router as demo_router
    from src.core.api.v1.governance_admin import domain_router as governance_domain_router
    from src.core.api.llm_endpoints import router as llm_router
    from src.core.api.v1.missions import domain_router as mission_domain_router
    from src.core.api.v1.models import domain_router as models_domain_router
    from src.core.api.v1.synthesis import domain_router as synthesis_domain_router
    from src.core.api.v1.audit import domain_router as audit_domain_router
    from src.core.api.v1.memory import domain_router as memory_domain_router

    app.include_router(copilot_intent_domain_router)
    count += 1
    app.include_router(models_domain_router)
    count += 1
    app.include_router(demo_router, tags=["Demo Playground"])
    count += 1
    app.include_router(mission_domain_router)
    count += 1
    app.include_router(synthesis_domain_router)
    count += 1
    app.include_router(governance_domain_router)
    count += 1
    app.include_router(audit_domain_router)
    count += 1
    app.include_router(analytics_router)
    count += 1
    app.include_router(memory_domain_router)
    count += 1
    app.include_router(llm_router, prefix="/api/v1")
    count += 1

    try:
        from src.domains.memory.router import router as agent_memory_router

        app.include_router(agent_memory_router, tags=["Agent Memory"])
        count += 1
    except Exception as e:
        logger.warning("Skipping Agent Memory router: %s", e)

    logger.debug("core_api routers registered: %s", count)
    return count
