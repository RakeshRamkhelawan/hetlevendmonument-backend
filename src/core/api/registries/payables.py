"""Payables domain registry (ADR-033 Laag 3, max 80 regels). Crediteuren dag 1."""

from fastapi import FastAPI


def register(app: FastAPI) -> int:
    """Register the payables (crediteuren) domain router. Returns count."""
    from src.core.api.v1.payables import router as payables_router

    app.include_router(payables_router)
    return 1
