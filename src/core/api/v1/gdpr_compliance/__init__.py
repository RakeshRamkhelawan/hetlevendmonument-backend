"""GDPR Compliance domain package (ADR-033 Laag 2).

URL prefix: /api/gdpr (zonder /v1/) -- sub-routers bevatten de volledige prefix.
The flat file gdpr_compliance_endpoints.py delegates to this package via re-export.
"""

from fastapi import APIRouter

from .router import router as gdpr_composite_router

domain_router = APIRouter(tags=["GDPR Compliance"])
domain_router.include_router(gdpr_composite_router)

__all__ = ["domain_router"]
