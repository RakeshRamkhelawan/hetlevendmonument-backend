"""Scheduling WebSocket router registry (ADR-033 Laag 2, max 80 regels)."""

from fastapi import FastAPI
from loguru import logger


def register(app: FastAPI) -> int:
    """Register scheduling WebSocket router. Returns count."""
    count: int = 0

    try:
        from src.core.scheduling.api.websocket import router as scheduling_ws_router

        app.include_router(scheduling_ws_router)
        count += 1
        logger.debug("Scheduling WebSocket router registered")
    except Exception as e:
        logger.warning("Skipping Scheduling WebSocket router: %s", e)

    return count
