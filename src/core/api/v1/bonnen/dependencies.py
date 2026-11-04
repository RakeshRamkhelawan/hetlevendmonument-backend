"""Gedeelde dependencies voor het `bonnen`-domein (bonlezer dag 3, ADR-033 Laag 2).

De route importeert hier alles vandaan en NOOIT rechtstreeks `src.core.als`, `database` of `governance`
(ADR-033 par. 2, bewaakt door `.importlinter`).

Het recht is `receipts:read` / `receipts:write` uit de database (rollen `user` en `editor`; de beheerder via
`*:*`). Gekozen boven hergebruik van `receivables:*`: een bon is een uitgave van het bedrijf, geen
vordering op een klant, en wie debiteuren mag zien hoeft daarom nog geen bonnen te mogen uploaden.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.als.bonlezer.bevestiging import BonBevestiging
from src.core.als.bonlezer.btw_overzicht import (
    BtwOverzicht,
    Kwartaal,
    huidig_kwartaal,
    parse_kwartaal,
)
from src.core.als.bonlezer.dienst import maak_dienst
from src.core.als.bonlezer.lezer import MAX_BYTES
from src.core.als.bonlezer.upload import BonDienst, BonNietGevonden, UploadFout
from src.core.als.bonlezer.worker import upload_root
from src.core.api.auth.dependencies import validate_csrf_token
from src.core.api.v1.admin.dependencies import (
    UserResponse,
    _resolve_tenant_id,
    get_current_user,
    require_resource_permission,
)
from src.core.database.database import get_db
from src.core.governance.rate_limiter import privacy_rate_limit
from src.core.governance.services.audit_service import AuditService
from src.core.utils.best_effort import best_effort

#: 12 uploads per minuut per gebruiker, ook geweigerde (security-review dag 3: het quotum op openstaande
#: opdrachten alleen is te omzeilen door na elke bon de status op te vragen).
bonnen_upload_limit = privacy_rate_limit(max_requests=12, window_seconds=60)

#: Lezen (lijst, export, status) en bevestigen lopen over alle bestanden van de tenant: ook die krijgen een
#: grens per gebruiker (security-review dag 4, bevinding 1).
bonnen_read_limit = privacy_rate_limit(max_requests=60, window_seconds=60)
bonnen_write_limit = privacy_rate_limit(max_requests=30, window_seconds=60)

__all__ = [
    "MAX_BYTES",
    "BonAudit",
    "BonBevestiging",
    "BonDienst",
    "BonNietGevonden",
    "BtwOverzicht",
    "Kwartaal",
    "UploadFout",
    "UserResponse",
    "_resolve_tenant_id",
    "_toets_read",
    "_toets_write",
    "bonnen_read_limit",
    "bonnen_upload_limit",
    "bonnen_write_limit",
    "get_bon_audit",
    "get_bon_bevestiging",
    "get_bon_dienst",
    "get_btw_overzicht",
    "get_current_user",
    "get_db",
    "get_nu",
    "huidig_kwartaal",
    "parse_kwartaal",
    "require_receipts_read",
    "require_receipts_write",
    "validate_csrf_token",
]


#: De rechtentoetsen zelf, op moduleniveau: een test kan ze vervangen zonder de afhankelijkheid hieronder
#: (die de gebruiker voor de snelheidsbegrenzing op het verzoek zet) te omzeilen.
_toets_read = require_resource_permission("receipts", "read")
_toets_write = require_resource_permission("receipts", "write")


def _vereis_receipts_recht(
    toets: Callable[..., Awaitable[int]],
) -> Callable[..., Awaitable[UserResponse]]:
    """Het recht uit `toets`; de gebruiker komt terug zodat de route de tenant uit de JWT haalt.

    De gebruiker wordt ook op `request.state.user` gezet: de snelheidsbegrenzing (`privacy_rate_limit`)
    bepaalt haar sleutel (`<tenant>:<gebruiker>:<pad>`) daaruit en valt anders terug op het IP, dat achter
    de proxy voor iedereen hetzelfde is (code- en security-review dag 3, ronde 2). Niets in `src/` zette
    `request.state.user` tot dan toe.
    """

    async def _afhankelijkheid(
        request: Request,
        current_user: UserResponse = Depends(get_current_user),
        _user_id: int = Depends(toets),
    ) -> UserResponse:
        request.state.user = current_user
        return current_user

    return _afhankelijkheid


require_receipts_read = _vereis_receipts_recht(_toets_read)
require_receipts_write = _vereis_receipts_recht(_toets_write)


def get_bon_dienst() -> BonDienst:
    return maak_dienst()


class BonAudit:
    """De auditregels van een bon; de route kent de database (ADR-033) en `best_effort` niet."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def upload(
        self,
        request: Request,
        current_user: UserResponse,
        *,
        tenant_id: int,
        bestand_id: str,
        aantal_bytes: int,
    ) -> None:
        # Alleen een nummer en een aantal: geen bestandsnaam en geen inhoud in de auditregel.
        await self._schrijf(
            request,
            current_user,
            event_type="bon_upload",
            omschrijving="Bon geupload",
            tenant_id=tenant_id,
            metadata={"bestand_id": bestand_id, "bytes": aantal_bytes},
        )

    async def bevestigd(
        self,
        request: Request,
        current_user: UserResponse,
        *,
        tenant_id: int,
        bestand_id: str,
    ) -> None:
        """Wie wanneer welke bon bevestigde; de gegevens van de bon zelf staan er NIET in."""
        await self._schrijf(
            request,
            current_user,
            event_type="bon_bevestigd",
            omschrijving="Velden van een bon bevestigd",
            tenant_id=tenant_id,
            metadata={"bestand_id": bestand_id},
        )

    async def _schrijf(
        self,
        request: Request,
        current_user: UserResponse,
        *,
        event_type: str,
        omschrijving: str,
        tenant_id: int,
        metadata: dict[str, object],
    ) -> None:
        async with best_effort(f"{event_type} audit log", db_session=self._db):
            await AuditService.log_event(
                db=self._db,
                event_type=event_type,
                severity="low",
                source_ip=request.client.host if request.client else "unknown",
                endpoint=str(request.url.path),
                description=omschrijving,
                tenant_id=tenant_id,
                user_id=current_user.id,
                action=event_type,
                metadata=metadata,
            )
            await self._db.commit()


def get_bon_audit(db: AsyncSession = Depends(get_db)) -> BonAudit:
    return BonAudit(db)


def get_btw_overzicht() -> BtwOverzicht:
    return BtwOverzicht(upload_root())


def get_nu() -> datetime:
    """De klok als afhankelijkheid: een test kan het standaardkwartaal zo vastzetten."""
    return datetime.now(timezone.utc)


def get_bon_bevestiging() -> BonBevestiging:
    return BonBevestiging(upload_root())
