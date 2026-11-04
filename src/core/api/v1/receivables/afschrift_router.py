"""Een bankafschrift (CAMT.053) inlezen en betaalde facturen vanzelf afvinken (debiteuren vanzelf afronden, B2).

Het bestand komt als losse inhoud van het verzoek (`application/xml` of `text/xml`), niet als formulier: er komt geen
extra pakket voor bij. De inhoud wordt tijdens het lezen begrensd (5 MB) en NIET bewaard of gelogd. Recht:
`receivables:write` (afvinken is een statuswijziging naar `betaald`), CSRF, 10 per minuut.

BEWUST GEEN `from __future__ import annotations`: zie `router.py` (rate-limit-decorators met `functools.wraps`).
"""

from fastapi import APIRouter, Depends, HTTPException, Request, status

from .dependencies import (
    ReceivableRepository,
    UserResponse,
    _resolve_tenant_id,
    consent_update_limit,
    get_current_user,
    get_receivable_repository,
    require_resource_permission,
    validate_csrf_token,
    verwerk_bankafschrift,
)

router = APIRouter(tags=["Debiteuren"])

#: Gelijk aan `services.bankafschrift.MAX_BYTES`; hier apart omdat de router geen service importeert (ADR-033).
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
_TOEGESTANE_TYPES = ("application/xml", "text/xml")


async def _lees_begrensd(request: Request) -> bytes:
    delen: list[bytes] = []
    totaal = 0
    async for stuk in request.stream():
        totaal += len(stuk)
        if totaal > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Dit bestand is te groot voor een bankafschrift (hoogstens 5 MB).",
            )
        delen.append(stuk)
    return b"".join(delen)


@router.post("/bankafschrift")
@consent_update_limit
async def upload_bankafschrift(
    request: Request,
    repo: ReceivableRepository = Depends(get_receivable_repository),
    current_user: UserResponse = Depends(get_current_user),
    user_id: int = Depends(require_resource_permission("receivables", "write")),
    _csrf: None = Depends(validate_csrf_token),
) -> dict[str, object]:
    """Vink de facturen af die een bijschrijving op het afschrift hebben; de rest meldt het als "niet gekoppeld"."""
    soort = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if soort not in _TOEGESTANE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Stuur het bankafschrift als XML-bestand (CAMT.053).",
        )
    data = await _lees_begrensd(request)
    tenant_id = _resolve_tenant_id(current_user)
    uitkomst = await verwerk_bankafschrift(repo, tenant_id=tenant_id, user_id=user_id, data=data)
    return {"success": True, "data": uitkomst}
