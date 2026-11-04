"""Foundation Portal main router (ADR-033 Laag 2)."""

from fastapi import APIRouter

router = APIRouter(prefix="/{tenantSlug}/foundation")

# Public endpoints
from . import contact, content, donations, map, newsletter, oai_pmh, settings, sitemap

router.include_router(contact.router)
router.include_router(content.router)
router.include_router(donations.router)
router.include_router(map.router)
router.include_router(newsletter.router)
router.include_router(settings.router)
router.include_router(oai_pmh.router)
router.include_router(sitemap.router)

# Auth endpoints
from . import auth

router.include_router(auth.router)

# Admin endpoints (curator + admin only)
from .admin import archief, curatie

router.include_router(curatie.router)
router.include_router(archief.router)

# Takedown endpoints (authenticated)
from . import takedown

router.include_router(takedown.router)

# Upload endpoints (authenticated, BE-EP-036)
from . import upload

router.include_router(upload.router)

# Edu endpoints (BE-EP-039: POST /edu/session publiek, rest vereist sessie)
from . import edu

router.include_router(edu.router)

# Docentenomgeving (BE-EP-055): aanvragen, klassen, lessen per klas, leerlingantwoorden
from . import docent

router.include_router(docent.router)

# Webhook endpoints (BE-EP-049: Brevo event & bounce handling)
from . import webhooks

router.include_router(webhooks.router)
