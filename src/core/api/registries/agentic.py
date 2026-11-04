"""Agentic features domain registry (ADR-033 Laag 2, max 80 regels)."""

import importlib
from typing import Any

from fastapi import FastAPI
from loguru import logger


def register(app: FastAPI) -> int:  # noqa: PLR0912
    """Register agentic feature routers. Returns count."""
    count = 0

    from src.core.api.agentic_flow_endpoints import router as agentic_flow_router
    from src.core.api.assistant_endpoints import router as assistant_router
    from src.core.api.copilot_websocket_endpoints import router as copilot_ws_router
    from src.core.api.orchestrator_endpoints import router as orchestrator_router
    from src.core.api.v1.agentic.router import router as agentic_router
    from src.core.api.v1.digital_twin.router import router as digital_twin_router
    from src.core.api.v1.agentic.websocket import router as agentic_ws_router
    from src.core.api.v1.ai_copilot.router import router as copilot_streaming_router
    from src.core.api.v1.autonomous.progress_ws import router as autonomous_progress
    from src.core.api.v1.autonomous.router import router as autonomous_exec_router
    from src.core.api.v1.collaboration.router import router as collaboration_router
    from src.core.api.v1.gamification.router import router as gamification_router
    from src.core.api.v1.ml.router import router as ml_predictor_router
    from src.core.api.v1.personas.router import router as personas_router
    from src.core.api.v1.privacy.router import router as privacy_router
    from src.core.api.v1.system.llm_health import router as llm_health_router
    from src.core.api.v1.system.llm_status import router as system_router
    from src.core.api.v1.tenant_custom_data.router import router as tenant_custom_data_router
    from src.core.api.v1.terminal.router import router as terminal_router
    from src.domains.agentic.api.experiments import router as experiments_router

    _mandatory: list[tuple[Any, dict[str, Any]]] = [  # TODO(TYPE): replace Any with concrete type
        (agentic_router, {"prefix": "/api/v1"}),
        (experiments_router, {}),
        (agentic_flow_router, {}),
        (orchestrator_router, {}),
        (copilot_streaming_router, {}),
        (copilot_ws_router, {}),
        (autonomous_exec_router, {}),
        (autonomous_progress, {}),
        (collaboration_router, {}),
        (ml_predictor_router, {}),
        (gamification_router, {}),
        (privacy_router, {}),
        (agentic_ws_router, {}),
        (terminal_router, {}),
        (personas_router, {}),
        (system_router, {}),
        (llm_health_router, {}),
        (assistant_router, {"prefix": "/api/v1", "tags": ["Assistant"]}),
        (tenant_custom_data_router, {}),
        (digital_twin_router, {"prefix": "/api/v1"}),
    ]
    for _r, _kw in _mandatory:
        app.include_router(_r, **_kw)
    count += len(_mandatory)

    for mod, tag in [
        ("src.core.api.v1.als.router", "ALS"),
        ("src.core.api.v1.routing.router", "Routing"),
        ("src.core.api.v1.orchestration.router", "Orchestration"),
    ]:
        try:
            m = importlib.import_module(mod)
            app.include_router(m.router, prefix="/api/v1", tags=[tag])
            count += 1
        except Exception as e:
            logger.warning("Skipping %s router: %s", tag, e)

    logger.debug("agentic routers registered: %s", count)
    return count
