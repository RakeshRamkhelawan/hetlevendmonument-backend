"""Tenants / P5 CRUD domain registry (ADR-033 Laag 2, max 80 regels).

Covers: tenants, users, documents, tools, procedures (stub, gated).
"""

import os

from fastapi import FastAPI
from loguru import logger


def _stub_crud_enabled() -> bool:
    """P5 stub is disabled by default; never active in production."""
    raw = os.getenv("ENABLE_P5_STUB_CRUD_ROUTERS", "false").strip().lower()
    env = os.getenv("ENVIRONMENT", "development").lower()
    if raw in {"1", "true", "yes", "on"} and env in {"production", "prod"}:
        logger.warning("ENABLE_P5_STUB_CRUD_ROUTERS=true ignored in ENVIRONMENT=%s", env)
        return False
    return raw in {"1", "true", "yes", "on"}


def register(app: FastAPI) -> int:
    """Register tenant, user, document, tools and procedures routers. Returns count."""
    count = 0

    try:
        from src.core.api.v1.tenants.router import router as tenants_router

        app.include_router(tenants_router, prefix="/api/v1")
        count += 1
    except Exception as e:
        logger.warning("Skipping Tenants router: %s", e)

    try:
        from src.core.api.v1.users.router import router as users_router

        app.include_router(users_router, prefix="/api/v1")
        count += 1
    except Exception as e:
        logger.warning("Skipping Users router: %s", e)

    try:
        from src.core.api.v1.documents.router import router as documents_router

        app.include_router(documents_router, prefix="/api/v1")
        count += 1
    except Exception as e:
        logger.warning("Skipping Documents router: %s", e)

    try:
        from src.core.api.v1.tools.router import router as tools_router

        app.include_router(tools_router, prefix="/api/v1")
        count += 1
    except Exception as e:
        logger.warning("Skipping Tools router: %s", e)

    if _stub_crud_enabled():
        try:
            from src.core.api.v1.procedures.router import router as procedures_router

            app.include_router(procedures_router, prefix="/api/v1")
            count += 1
        except Exception as e:
            logger.warning("Skipping Procedures router: %s", e)
    else:
        logger.warning("P5 stub procedures router disabled (ENABLE_P5_STUB_CRUD_ROUTERS not set).")

    logger.debug("tenants routers registered: %s", count)
    return count
