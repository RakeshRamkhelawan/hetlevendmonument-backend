"""Workflows domain registry (ADR-033 Laag 2, max 80 regels).

SP-API-003 Dag 1: workflow flat bestanden gemigreerd naar v1/workflow/ domain package.
"""

from typing import Any

from fastapi import FastAPI
from loguru import logger


def register(app: FastAPI) -> int:
    """Register workflow routers. Returns count."""
    count = 0

    # SP-API-003: workflow domein gemigreerd naar v1/workflow/
    from src.core.api.v1.workflow import domain_router as workflow_domain_router

    app.include_router(workflow_domain_router)
    count += 1

    from src.core.api.template_endpoints import router as template_router

    app.include_router(template_router, tags=["Workflow Templates"])
    count += 1

    from src.core.api.v1.snapshot_endpoints import router as snapshot_router

    app.include_router(snapshot_router, prefix="/api/v1")
    count += 1

    from src.core.api.tool_endpoints import router as tool_catalog_router

    app.include_router(tool_catalog_router, prefix="/api/v1", tags=["Tool Catalog"])
    count += 1

    from src.core.api.workflow_builder_ws import router as builder_ws_router

    app.include_router(builder_ws_router, tags=["Workflow Builder WS"])
    count += 1

    from src.core.api.v1.focus_builder.proxy import get_focus_builder_router

    app.include_router(get_focus_builder_router(), prefix="/api/v1", tags=["Focus Builder V1"])
    count += 1

    from src.core.api.v1.canvas.router import router as canvas_router

    app.include_router(canvas_router, prefix="/api/v1")
    count += 1

    for mod, tag in [
        ("src.core.api.v1.sync.router", "Sync"),
        ("src.core.api.v1.sync.json_router", "Sync"),
        ("src.core.api.v1.sync.ws_handler", None),
    ]:
        try:
            import importlib

            m = importlib.import_module(mod)
            kw: dict[str, Any] = {"tags": [tag]} if tag else {}
            app.include_router(m.router, prefix="/api/v1", **kw)
            count += 1
        except Exception as e:
            logger.warning("Skipping Sync router %s: %s", mod, e)

    logger.debug("workflow routers registered: %s", count)
    return count
