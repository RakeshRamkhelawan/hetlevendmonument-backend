# dsm:exempt reason: ADR-033 Laag 3 registry -- lazy import van router-modules is by design
"""Agents domain registry (ADR-033 Laag 2, max 80 regels)."""

from fastapi import FastAPI
from loguru import logger


def register(app: FastAPI) -> int:
    """Register agent and agent-submodule routers. Returns count."""
    count = 0

    # Core agents -- migrated to v1/agents/ (SP-API-003 Dag 3)
    from src.core.api.v1.agents import domain_router as agents_domain_router
    from src.core.api.v1.cva import domain_router as cva_domain_router

    app.include_router(agents_domain_router)
    count += 1
    app.include_router(cva_domain_router)
    count += 1

    # Agent submodules -- knowledge migrated to v1/knowledge/ (SP-API-003 Dag 5)
    try:
        from src.core.api.v1.knowledge import domain_router as knowledge_domain_router

        app.include_router(knowledge_domain_router, prefix="/api/v1/agents", tags=["Knowledge"])
        count += 1
    except Exception as e:
        logger.warning("Skipping Knowledge Agent router: %s", e)

    # Sentiment scanner -- migrated to v1/sentiment_scanner/ (SP-API-006 Dag 4)
    try:
        from src.core.api.v1.sentiment_scanner import domain_router as sentiment_domain_router

        app.include_router(sentiment_domain_router)
        count += 1
    except Exception as e:
        logger.warning("Skipping Sentiment Agent router: %s", e)

    # Diagnostics -- health v1 domain router (SP-API-004 Dag 4)
    try:
        from src.core.api.v1.health import domain_router as health_diagnostics_router

        app.include_router(health_diagnostics_router, prefix="/api/v1/agents", tags=["Diagnostics"])
        count += 1
    except Exception as e:
        logger.warning("Skipping Diagnostics Agent router: %s", e)

    try:
        from src.core.agents.translation_agent import router as translation

        app.include_router(translation, prefix="/api/v1/agents", tags=["Translation"])
        count += 1
    except Exception as e:
        logger.warning("Skipping Translation Agent router: %s", e)

    # Subagents -- migrated to v1/subagents/ (SP-API-007 Dag 3)
    try:
        from src.core.api.v1.subagents import domain_router as subagents_domain_router

        app.include_router(subagents_domain_router)
        count += 1
    except Exception as e:
        logger.warning("Skipping Subagents router: %s", e)

    logger.debug("agents routers registered: %s", count)
    return count
