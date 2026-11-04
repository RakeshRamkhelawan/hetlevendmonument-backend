"""Het overzicht per factuur: wat er is gebeurd, door wie en wanneer, in het Nederlands (debiteuren vanzelf afronden, B4).

Lezen vraagt `receivables:read` en mag 60 keer per minuut. De tenant komt uit de JWT-context; een factuur van een ander
bedrijf bestaat hier niet (404). Het antwoord bevat geen brieftekst en geen adres van de debiteur.

BEWUST GEEN `from __future__ import annotations`: zie `router.py` (rate-limit-decorators met `functools.wraps`).
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from .dependencies import (
    UserResponse,
    _resolve_tenant_id,
    consent_read_limit,
    get_current_user,
    get_db,
    lees_tijdlijn,
    require_resource_permission,
)

router = APIRouter(tags=["Debiteuren"])


@router.get("/{receivable_id}/tijdlijn")
@consent_read_limit
async def get_receivable_timeline(
    request: Request,
    receivable_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserResponse = Depends(get_current_user),
    _: int = Depends(require_resource_permission("receivables", "read")),
) -> dict[str, object]:
    """De gebeurtenissen van een factuur van de eigen tenant, oudste eerst."""
    gebeurtenissen = await lees_tijdlijn(
        db, tenant_id=_resolve_tenant_id(current_user), receivable_id=receivable_id
    )
    return {"success": True, "data": gebeurtenissen}
