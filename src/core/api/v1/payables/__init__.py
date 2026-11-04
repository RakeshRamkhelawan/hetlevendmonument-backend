from .router import router
from .betaal_router import router as _betaal_router
from .inlezen_router import router as _inlezen_router
from .suppliers_router import router as _suppliers_router

# Zelfde prefix, eigen bestand: ADR-033 houdt een routerbestand klein.
router.include_router(_suppliers_router)
router.include_router(_inlezen_router)
router.include_router(_betaal_router)

__all__ = ["router"]
