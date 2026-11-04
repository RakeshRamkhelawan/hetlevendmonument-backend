"""Noodstop domain registry (ADR-033 Laag 3, max 80 regels). Noodstop per klant."""

from fastapi import FastAPI


def register(app: FastAPI) -> int:
    """Register the noodstop domain router (een klant stilzetten of weer opheffen). Returns count."""
    from src.core.api.v1.noodstop import router as noodstop_router

    app.include_router(noodstop_router)
    return 1
