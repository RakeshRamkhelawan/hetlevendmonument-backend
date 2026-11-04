"""Scheduling domain registry -- facade for REST + WebSocket scheduling routes (ADR-033 Laag 2, max 80 regels)."""

from fastapi import FastAPI

from src.core.api.registries import scheduling_rest, scheduling_ws


def register(app: FastAPI) -> int:
    """Register all scheduling routers (REST + WebSocket). Returns count."""
    return scheduling_rest.register(app) + scheduling_ws.register(app)
