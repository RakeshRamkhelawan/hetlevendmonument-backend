"""De noodstop van een klant aan- en uitzetten, met een auditregel (noodstop per klant; ADR-005).

**Zetten** legt de stand vast en commit, en schrijft DAARNA de auditregel in `best_effort`
(backend-regel: primaire data eerst). Een kapot logboek mag een noodstop NOOIT tegenhouden, want
dan kan een beheerder een klant in nood niet stilzetten. De stand zelf bewaart wie, wanneer en
waarom van de LAATSTE wijziging; een auditregel die niet lukt wordt met `logger.error` en
stacktrace gemeld (`best_effort`).

**Opheffen** is andersom: de auditregel gaat in DEZELFDE transactie als de wijziging en is
fail-closed. Lukt hij niet, dan wordt de stop niet opgeheven (rollback) en krijgt de beheerder een
fout (`NoodstopAuditMislukt`): opheffen zet agents weer aan en mag geen onzichtbare wijziging zijn.

**Wie mag wat.** Een beheerder van de klant mag de eigen klant stilzetten en opheffen. Een
platformbeheerder mag elke klant stilzetten en opheffen. Een stop die door het PLATFORM is gezet
mag alleen het platform opheffen (en ook niet door de klant worden overschreven): anders kon de
klant een stop van het platform, bijvoorbeeld bij misbruik, zelf ongedaan maken. Die regel staat
hier en niet in de route, zodat elke aanroeper hem krijgt.

De klant komt als parameter binnen en is door de route uit de JWT-context gehaald (of, voor een
platformroute, uit het pad van een route die alleen een platformbeheerder bereikt); een
`tenant_id` uit een body of query komt hier nooit.
"""

from __future__ import annotations

import logging
from contextlib import AbstractAsyncContextManager, nullcontext

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database.bypass_session import adopt_tenant
from src.core.governance.services.audit_service import AuditService
from src.core.repositories.tenant_noodstop_repository import (
    NoodstopStand as NoodstopStand,  # her-export: `api/v1/noodstop/dependencies.py` haalt hem hier op
)
from src.core.repositories.tenant_noodstop_repository import TenantNoodstopRepository
from src.core.utils.best_effort import best_effort

logger = logging.getLogger(__name__)

EVENT_TYPE = "noodstop_changed"

MELDING_PLATFORM_SLOT = (
    "Deze noodstop is door het platform gezet. Alleen het platform kan hem opheffen of wijzigen."
)


class NoodstopDoorPlatformGezet(Exception):
    """De klant mag deze stop niet wijzigen: het platform heeft hem gezet."""

    def __init__(self) -> None:
        super().__init__(MELDING_PLATFORM_SLOT)


class NoodstopAuditMislukt(Exception):
    """De opheffing is NIET doorgevoerd: de auditregel kon niet worden vastgelegd (fail-closed)."""

    def __init__(self) -> None:
        super().__init__(
            "De noodstop is niet opgeheven omdat de wijziging niet in het logboek kon worden "
            "vastgelegd. Probeer het zo opnieuw."
        )


class NoodstopKlantOnbekend(Exception):
    """De klant bestaat niet (de vreemde sleutel naar `tenants` weigert de rij)."""

    def __init__(self) -> None:
        super().__init__("Deze klant bestaat niet.")


class NoodstopService:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db
        self._repo = TenantNoodstopRepository(db)

    def _als_klant(self, tenant_id: int, door_platform: bool) -> AbstractAsyncContextManager[None]:
        """De tenantcontext voor deze klant, als het PLATFORM voor een andere klant handelt.

        Een beheerder werkt in de context van de eigen klant (de JWT), en daar klopt de RLS al.
        Het platform handelt voor een ANDERE klant: zonder dit blok weigert de RLS (de sessie staat
        op de klant van de platformbeheerder) de rij of de auditregel voor de doelklant, gemeten op
        een niet-superuser-rol met `new row violates row-level security policy`. `adopt_tenant`
        zet de context voor dit blok en zet hem daarna terug. De doelklant komt uit het pad van een
        route die alleen een platformbeheerder bereikt, nooit uit een body of query.
        """
        if door_platform:
            return adopt_tenant(self._db, tenant_id)
        return nullcontext()

    async def stand(self, tenant_id: int, *, door_platform: bool = False) -> NoodstopStand:
        """De stand van deze klant; zonder rij 'niet stilgezet'."""
        async with self._als_klant(tenant_id, door_platform):
            return await self._repo.get(tenant_id)

    async def zet_stand(
        self,
        tenant_id: int,
        stilgezet: bool,
        *,
        reden: str,
        user_id: int,
        door_platform: bool,
        source_ip: str,
        endpoint: str,
    ) -> NoodstopStand:
        """Zet de klant stil of hef de stop op en legt de wijziging vast; idempotent."""
        async with self._als_klant(tenant_id, door_platform):
            return await self._zet_stand(
                tenant_id,
                stilgezet,
                reden=reden,
                user_id=user_id,
                door_platform=door_platform,
                source_ip=source_ip,
                endpoint=endpoint,
            )

    async def _zet_stand(
        self,
        tenant_id: int,
        stilgezet: bool,
        *,
        reden: str,
        user_id: int,
        door_platform: bool,
        source_ip: str,
        endpoint: str,
    ) -> NoodstopStand:
        try:
            # Het platformslot wordt in DEZE schrijfstap beslist (zie `set_stand`): geen leesstap
            # ervoor waartussen een platformschrijver het slot kan omzeilen.
            stand = await self._repo.set_stand(
                tenant_id,
                stilgezet,
                reden=reden,
                user_id=user_id,
                door_platform=door_platform,
            )
            if stand is None:
                await self._db.rollback()
                raise NoodstopDoorPlatformGezet()
            if not stand.is_stilgezet:
                # OPHEFFEN: de auditregel in DEZELFDE transactie, fail-closed. Opheffen zet agents
                # weer aan; zonder spoor gebeurt dat niet (Gate 2 ronde 2, punt 5).
                await self._audit_bij_opheffen(
                    tenant_id,
                    stand,
                    reden=reden,
                    user_id=user_id,
                    door_platform=door_platform,
                    source_ip=source_ip,
                    endpoint=endpoint,
                )
            await self._db.commit()
        except IntegrityError as exc:
            # Het enige dat hier kan weigeren is de vreemde sleutel naar `tenants`: de reden is
            # door het schema al op lengte begrensd.
            await self._db.rollback()
            raise NoodstopKlantOnbekend() from exc
        except NoodstopAuditMislukt:
            await self._db.rollback()
            raise
        if stand.is_stilgezet:
            # ZETTEN: de stop staat vast (gecommit); de auditregel is best-effort, want een kapot
            # logboek mag een klant in nood niet onbeschermd laten.
            async with best_effort(f"{EVENT_TYPE} audit log", db_session=self._db):
                await self._schrijf_audit(
                    tenant_id,
                    stand,
                    reden=reden,
                    user_id=user_id,
                    door_platform=door_platform,
                    source_ip=source_ip,
                    endpoint=endpoint,
                )
                await self._db.commit()
        return stand

    async def _audit_bij_opheffen(
        self,
        tenant_id: int,
        stand: NoodstopStand,
        *,
        reden: str,
        user_id: int,
        door_platform: bool,
        source_ip: str,
        endpoint: str,
    ) -> None:
        """De auditregel van een opheffing, in de lopende transactie; elke mislukking is fataal."""
        try:
            gelukt = await self._schrijf_audit(
                tenant_id,
                stand,
                reden=reden,
                user_id=user_id,
                door_platform=door_platform,
                source_ip=source_ip,
                endpoint=endpoint,
            )
        except Exception as exc:
            logger.error("noodstop: auditregel van de opheffing mislukt: %s", exc, exc_info=True)
            raise NoodstopAuditMislukt() from exc
        if gelukt is not True:
            # `log_event` meldt een databasefout als False in plaats van een uitzondering.
            logger.error("noodstop: auditregel van de opheffing niet geschreven")
            raise NoodstopAuditMislukt()

    async def _schrijf_audit(
        self,
        tenant_id: int,
        stand: NoodstopStand,
        *,
        reden: str,
        user_id: int,
        door_platform: bool,
        source_ip: str,
        endpoint: str,
    ) -> bool:
        # Wie, wanneer (de auditregel draagt het tijdstip) en waarom; geen namen of e-mailadressen.
        return await AuditService.log_event(
            db=self._db,
            event_type=EVENT_TYPE,
            severity="high",
            source_ip=source_ip,
            endpoint=endpoint,
            description="Noodstop gezet" if stand.is_stilgezet else "Noodstop opgeheven",
            tenant_id=tenant_id,
            user_id=user_id,
            action=EVENT_TYPE,
            metadata={
                "is_stilgezet": stand.is_stilgezet,
                "reden": reden,
                "door_platform": door_platform,
            },
        )
