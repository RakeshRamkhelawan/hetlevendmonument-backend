from .afschrift_router import router as _afschrift_router
from .instellingen_router import router as _instellingen_router
from .router import router
from .tijdlijn_router import router as _tijdlijn_router

# Zelfde prefix, eigen bestand: router.py zit tegen de grens van 200 regels (ADR-033).
router.include_router(_afschrift_router)
router.include_router(_instellingen_router)
router.include_router(_tijdlijn_router)

__all__ = ["router"]
