"""Company layer domain registry (ADR-033 Laag 2, max 80 regels)."""

from typing import Any

from fastapi import FastAPI
from loguru import logger


def register(app: FastAPI) -> int:
    """Register company layer and domain pack routers. Returns count."""
    count = 0

    try:
        from src.core.api.v1.company.department_individual_router import router as dept_ind_router
        from src.core.api.v1.company.department_router import router as department_router
        from src.core.api.v1.company.external_agent_router import router as external_agent_router
        from src.core.api.v1.company.goal_router import router as goal_router
        from src.core.api.v1.company.router import router as company_router

        app.include_router(company_router, prefix="/api/v1", tags=["Companies"])
        count += 1
        app.include_router(department_router, prefix="/api/v1", tags=["Departments"])
        count += 1
        app.include_router(dept_ind_router, prefix="/api/v1", tags=["Departments"])
        count += 1
        app.include_router(goal_router, prefix="/api/v1", tags=["Goals"])
        count += 1
        app.include_router(external_agent_router, prefix="/api/v1", tags=["External Agents"])
        count += 1
    except Exception as e:
        logger.warning("Skipping Company Layer routers: %s", e)

    for mod, attr, prefix, tag in [
        ("src.core.api.domain_packs", "router", None, "Domain Packs"),
        ("src.core.api.pack_feedback_endpoints", "router", None, "Pack Feedback"),
        ("src.core.api.v1.company.pack_selector_router", "router", "/api/v1", "Pack Selector"),
    ]:
        try:
            import importlib

            m = importlib.import_module(mod)
            kw: dict[str, Any] = {"prefix": prefix} if prefix else {}
            app.include_router(getattr(m, attr), tags=[tag], **kw)
            count += 1
        except Exception as e:
            logger.warning("Skipping %s router: %s", tag, e)

    try:
        from src.core.api.v1.company.board_router import router as board_router
        from src.core.api.v1.company.onboarding_router import router as onboarding_router
        from src.core.api.v1.company.template_router import router as template_router

        app.include_router(template_router, prefix="/api/v1", tags=["Templates"])
        count += 1
        app.include_router(onboarding_router, prefix="/api/v1", tags=["Onboarding"])
        count += 1
        app.include_router(board_router, prefix="/api/v1", tags=["Board Governance"])
        count += 1
    except Exception as e:
        logger.warning("Skipping Fase 7 routers: %s", e)

    logger.debug("company routers registered: %s", count)
    return count
