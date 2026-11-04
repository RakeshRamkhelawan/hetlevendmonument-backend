"""Analytics, monitoring, health & feature-flag domain registry (ADR-033 Laag 2, max 80 regels)."""

from fastapi import FastAPI
from loguru import logger


def register(app: FastAPI) -> int:
    """Register monitoring, analytics, health and feature-flag routers. Returns count."""
    count = 0

    from src.core.api.v1.analytics import router as analytics_router
    from src.core.api.v1.analytics.agents import router as agent_analytics_router
    from src.core.api.v1.analytics_ingest import domain_router as analytics_ingest_domain_router
    from src.core.api.v1.monitoring_v1 import domain_router as monitoring_v1_domain_router
    from src.core.api.v1.production import domain_router as production_domain_router
    from src.core.api.v1.rbac import domain_router as rbac_domain_router
    from src.core.api.v1.security import domain_router as security_domain_router

    app.include_router(analytics_ingest_domain_router)
    count += 1
    app.include_router(monitoring_v1_domain_router)
    count += 1
    app.include_router(production_domain_router)
    count += 1
    app.include_router(rbac_domain_router)
    count += 1
    app.include_router(security_domain_router)
    count += 1
    app.include_router(analytics_router, prefix="/api/v1")
    count += 1
    app.include_router(agent_analytics_router, prefix="/api/v1")
    count += 1

    # Events (OODA loop monitoring)
    try:
        from src.core.api.events_endpoints import router as events_router

        app.include_router(events_router, prefix="/api/v1", tags=["Events"])
        count += 1
    except Exception as e:
        logger.warning("Skipping Event system router: %s", e)

    # Health checks -- migrated to v1/health/ (SP-API-004 Dag 4)
    from src.core.api.v1.health import domain_router as health_domain_router

    app.include_router(health_domain_router)
    count += 1

    # Feature flags (SP-API-006 Dag 3)
    try:
        from src.core.api.v1.feature_flags import domain_router as ff_domain_router

        app.include_router(ff_domain_router)
        count += 1
    except Exception as e:
        logger.warning("Skipping Feature Flags router: %s", e)
    try:
        from src.core.api.v1.experimentation import domain_router as exp_dr

        app.include_router(exp_dr)
        count += 1  # noqa: E702
    except Exception as e:
        logger.warning("Skipping Experimentation router: %s", e)
    try:
        from src.core.api.v1.ai_features import domain_router as ai_dr

        app.include_router(ai_dr)
        count += 1  # noqa: E702
    except Exception as e:
        logger.warning("Skipping AI Features router: %s", e)
    try:
        from src.core.api.v1.prediction import domain_router as pred_dr

        app.include_router(pred_dr)
        count += 1  # noqa: E702
    except Exception as e:
        logger.warning("Skipping Prediction router: %s", e)

    logger.debug("analytics routers registered: %s", count)
    return count
