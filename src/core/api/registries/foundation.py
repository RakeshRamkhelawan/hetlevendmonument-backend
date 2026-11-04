"""Foundation Portal router registry (ADR-033 Laag 3, max 80 regels)."""

from fastapi import FastAPI


def register(app: FastAPI) -> int:
    """Register the foundation portal and tenant resolution routers. Returns count."""
    from src.core.api.v1.foundation import router as foundation_router
    from src.core.api.v1.foundation.sitemap import host_sitemap_router
    from src.core.api.v1.foundation.tenant_resolution import router as resolution_router

    app.include_router(foundation_router)
    app.include_router(foundation_router, prefix="/api/v1")
    app.include_router(resolution_router)
    app.include_router(host_sitemap_router)
    return 4
