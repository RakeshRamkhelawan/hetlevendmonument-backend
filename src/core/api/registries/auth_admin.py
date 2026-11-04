"""Auth & Admin domain registry (ADR-033 Laag 2, max 80 regels)."""

import os

from fastapi import FastAPI
from loguru import logger


def _rag_enabled() -> bool:
    raw = os.getenv("RAG_ENABLED")
    if raw is not None:
        return raw.strip().lower() in {"1", "true", "yes", "on"}
    legacy = os.getenv("ENABLE_RAG_ROUTERS")
    if legacy is not None:
        logger.warning("ENABLE_RAG_ROUTERS is deprecated; use RAG_ENABLED instead.")
        return legacy.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _register_rag_only(app: FastAPI) -> int:
    """Register only the RAG router when RAG_ENABLED. Returns 0 or 1.

    Extracted helper for unit-testing the RAG feature-flag gate in isolation,
    without mounting the full auth/admin stack.
    """
    if not _rag_enabled():
        return 0
    try:
        from src.core.api.rag_endpoints import router as rag_router

        app.include_router(rag_router, tags=["RAG"])
        return 1
    except (ImportError, ModuleNotFoundError) as e:
        logger.warning("Skipping RAG router (missing dependency): %s", e)
        return 0
    except Exception as e:
        logger.error("RAG router registration failed unexpectedly: %s", e)
        raise


def register(app: FastAPI) -> int:
    """Register auth, admin and management routers. Returns count."""
    count = 0

    from src.core.api.admin_digital_twin import router as admin_digital_twin_router
    from src.core.api.admin_learning_endpoints import router as admin_learning_router
    from src.core.api.auth.router import router as auth_router
    from src.core.api.v1.admin import domain_router as admin_domain_router
    from src.core.api.v1.admin.experiments import router as admin_experiments_router
    from src.core.api.v1.management import domain_router as management_domain_router

    # NOTE: management_endpoints.py replaced by v1/management/ domain router (SP-API-005 Dag 5)
    app.include_router(auth_router, prefix="/api/v1", tags=["Authentication"])
    count += 1
    app.include_router(admin_domain_router)
    count += 1
    # Ook onder /api/v1: de proxy stuurt alleen /api door (brief 2026-10-05-ws-en-admin-buiten-api-prefix)
    app.include_router(admin_domain_router, prefix="/api/v1", include_in_schema=False)
    count += 1
    app.include_router(admin_learning_router, tags=["Learning Admin"])
    count += 1
    app.include_router(admin_digital_twin_router, prefix="/api/v1", tags=["Admin - Digital Twin"])
    count += 1
    app.include_router(management_domain_router)
    count += 1
    app.include_router(admin_experiments_router, prefix="/api/v1", tags=["Admin - Experiments"])
    count += 1

    # RAG -- gated by RAG_ENABLED (default off; vector store post-MVP)
    count += _register_rag_only(app)

    logger.debug("auth_admin routers registered: %s", count)
    return count
