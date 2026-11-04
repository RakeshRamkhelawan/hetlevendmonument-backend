"""Noodstop per klant (noodstop per klant; ADR-033 Laag 1, ADR-005, ADR-036 OP-03).

- `GET /api/v1/noodstop` (beheerder): de stand van de EIGEN klant.
- `PUT /api/v1/noodstop` (beheerder + CSRF): de eigen klant stilzetten of weer opheffen. De klant komt
  uit de JWT; een `tenant_id` in de body wordt geweigerd. De `reden` is verplicht.
- `GET` en `PUT /api/v1/platform/klanten/{tenant_id}/noodstop` (alleen een platformbeheerder): dezelfde
  twee voor een ANDERE klant. Een stop die zo is gezet kan alleen het platform weer opheffen.

Elke wijziging krijgt een auditregel (`noodstop_changed`: wie, wanneer, waarom).

Importeert NOOIT direct database/governance/agents/workflow/llm: alleen `.dependencies` (Laag 2).
BEWUST GEEN `from __future__ import annotations`: de limiet-decorators gebruiken `functools.wraps`.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request

from .dependencies import (
    NoodstopAuditMislukt,
    NoodstopDoorPlatformGezet,
    NoodstopKlantOnbekend,
    NoodstopService,
    NoodstopStand,
    UserResponse,
    get_noodstop_service,
    noodstop_read_limit,
    noodstop_write_limit,
    require_noodstop_beheerder,
    require_platform_beheerder,
    require_tenant_id,
    validate_csrf_token,
)
from .schemas import NoodstopRequest

router = APIRouter(prefix="/api/v1", tags=["Noodstop"])


def _stand(stand: NoodstopStand) -> dict[str, object]:
    """De velden die een beheerder te zien krijgt; nooit een gebruikersnaam of e-mailadres."""
    return {
        "is_stilgezet": stand.is_stilgezet,
        "reden": stand.reden,
        "changed_at": stand.changed_at,
        "door_platform": stand.changed_by_platform,
    }


def _bron_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


async def _zet(
    service: NoodstopService,
    request: Request,
    tenant_id: int,
    body: NoodstopRequest,
    current_user: UserResponse,
    *,
    door_platform: bool,
) -> dict[str, object]:
    try:
        stand = await service.zet_stand(
            tenant_id,
            body.is_stilgezet,
            reden=body.reden,
            user_id=current_user.id,
            door_platform=door_platform,
            source_ip=_bron_ip(request),
            endpoint=str(request.url.path),
        )
    except NoodstopDoorPlatformGezet as exc:
        raise HTTPException(
            status_code=403,
            detail={"code": "NOODSTOP_DOOR_PLATFORM", "message": str(exc)},
        ) from exc
    except NoodstopAuditMislukt as exc:
        raise HTTPException(
            status_code=503,
            detail={"code": "NOODSTOP_NIET_OPGEHEVEN", "message": str(exc)},
        ) from exc
    except NoodstopKlantOnbekend as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "KLANT_NIET_GEVONDEN", "message": str(exc)},
        ) from exc
    return {"success": True, "data": _stand(stand)}


@router.get("/noodstop")
@noodstop_read_limit
async def get_noodstop(
    request: Request,
    service: NoodstopService = Depends(get_noodstop_service),
    current_user: UserResponse = Depends(require_noodstop_beheerder),
) -> dict[str, object]:
    """De stand van de eigen klant; zonder rij staat de klant niet stil."""
    return {"success": True, "data": _stand(await service.stand(require_tenant_id()))}


@router.put("/noodstop")
@noodstop_write_limit
async def set_noodstop(
    request: Request,
    body: NoodstopRequest,
    service: NoodstopService = Depends(get_noodstop_service),
    current_user: UserResponse = Depends(require_noodstop_beheerder),
    _csrf: None = Depends(validate_csrf_token),
) -> dict[str, object]:
    """De eigen klant stilzetten of opheffen; idempotent."""
    return await _zet(
        service, request, require_tenant_id(), body, current_user, door_platform=False
    )


@router.get("/platform/klanten/{tenant_id}/noodstop")
@noodstop_read_limit
async def get_noodstop_van_klant(
    request: Request,
    tenant_id: Annotated[int, Path(ge=1)],
    service: NoodstopService = Depends(get_noodstop_service),
    current_user: UserResponse = Depends(require_platform_beheerder),
) -> dict[str, object]:
    """De stand van een klant, voor het platform."""
    stand = await service.stand(tenant_id, door_platform=True)
    return {"success": True, "data": _stand(stand)}


@router.put("/platform/klanten/{tenant_id}/noodstop")
@noodstop_write_limit
async def set_noodstop_van_klant(
    request: Request,
    tenant_id: Annotated[int, Path(ge=1)],
    body: NoodstopRequest,
    service: NoodstopService = Depends(get_noodstop_service),
    current_user: UserResponse = Depends(require_platform_beheerder),
    _csrf: None = Depends(validate_csrf_token),
) -> dict[str, object]:
    """Een klant stilzetten of opheffen, door het platform; idempotent."""
    return await _zet(service, request, tenant_id, body, current_user, door_platform=True)
