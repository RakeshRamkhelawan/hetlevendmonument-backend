"""Packs domain registry (ADR-033 Laag 3, max 80 regels). Pakket aanzetten, dag 1."""

from fastapi import FastAPI


def register(app: FastAPI) -> int:
    """Register the packs domain router (pakketten per klant aan- en uitzetten). Returns count."""
    from src.core.api.v1.packs import router as packs_router

    app.include_router(packs_router)
    return 1
