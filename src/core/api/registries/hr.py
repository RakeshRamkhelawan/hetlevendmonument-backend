"""HR domain registry (ADR-033 Laag 3, max 80 regels)."""

from fastapi import FastAPI


def register(app: FastAPI) -> int:
    """Register the hr domain router. Returns count."""
    from src.core.api.v1.hr import router as hr_router

    app.include_router(hr_router)
    return 1
