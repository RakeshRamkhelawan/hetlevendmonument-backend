"""Gedeelde dependencies voor het `noodstop`-domein (noodstop per klant; ADR-033 Laag 2).

De router (`router.py`) importeert hier alles vandaan en NIETS rechtstreeks uit `governance`,
`agents`, `als` of de repository-laag (ADR-033 par. 2).

- `require_noodstop_beheerder`: een beheerder van de klant (centrale definitie `is_admin`, die een
  platformbeheerder ook doorlaat). De klant komt uit de JWT-context (`require_tenant_id`), nooit
  uit het verzoek (ADR-003).
- `require_platform_beheerder`: alleen een platformbeheerder; voor de platformroute die een
  ANDERE klant stilzet. Het klantnummer staat daar in het pad van een route die een gewone
  beheerder niet bereikt, nooit in een body of query.
"""

from __future__ import annotations

from fastapi import Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.auth.dependencies import validate_csrf_token
from src.core.api.v1.admin.dependencies import (
    UserResponse,
    get_current_user,
    get_db,
    is_admin,
    is_platform_superuser,
    require_tenant_id,
)
from src.core.governance.rate_limiter import noodstop_read_limit, noodstop_write_limit
from src.core.governance.noodstop_service import (
    NoodstopAuditMislukt,
    NoodstopDoorPlatformGezet,
    NoodstopKlantOnbekend,
    NoodstopService,
    NoodstopStand,
)

from .schemas import REDEN_MAX_LENGTE

__all__ = [
    "NoodstopAuditMislukt",
    "NoodstopDoorPlatformGezet",
    "NoodstopKlantOnbekend",
    "NoodstopService",
    "NoodstopStand",
    "REDEN_MAX_LENGTE",
    "UserResponse",
    "get_noodstop_service",
    "noodstop_read_limit",
    "noodstop_write_limit",
    "require_noodstop_beheerder",
    "require_platform_beheerder",
    "require_tenant_id",
    "validate_csrf_token",
]


async def require_noodstop_beheerder(
    current_user: UserResponse = Depends(get_current_user),
) -> UserResponse:
    """Alleen een beheerder mag de noodstop van de eigen klant lezen of wijzigen."""
    if not is_admin(current_user):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "NOODSTOP_BEHEERDER_VEREIST",
                "message": "Alleen een beheerder kan de noodstop bedienen.",
            },
        )
    return current_user


async def require_platform_beheerder(
    current_user: UserResponse = Depends(get_current_user),
) -> UserResponse:
    """Alleen een platformbeheerder; een beheerder van een klant is niet genoeg."""
    if not is_platform_superuser(current_user):
        raise HTTPException(
            status_code=403,
            detail={
                "code": "NOODSTOP_PLATFORM_VEREIST",
                "message": "Alleen het platform kan de noodstop van een andere klant bedienen.",
            },
        )
    return current_user


async def get_noodstop_service(db: AsyncSession = Depends(get_db)) -> NoodstopService:
    """De noodstopservice, met de sessie van dit verzoek."""
    return NoodstopService(db)
