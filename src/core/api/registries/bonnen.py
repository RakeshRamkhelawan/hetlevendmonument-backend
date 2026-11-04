"""Bonnen domain registry (ADR-033 Laag 3, max 80 regels)."""

from fastapi import FastAPI


def register(app: FastAPI) -> int:
    """Register the bonnen domain router. Returns count."""
    from src.core.api.v1.bonnen import router as bonnen_router

    app.include_router(bonnen_router)
    return 1
