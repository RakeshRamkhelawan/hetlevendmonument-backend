"""Noodstopstand per klant (noodstop per klant; ADR-005, ADR-010).

Elke methode neemt de klant als parameter en filtert expliciet op `tenant_id`; de klant komt uit de
JWT-context van de route (of, voor een platformbeheerder, uit het pad van een platformroute),
nooit uit een body of query. Een ontbrekende rij betekent: NIET stilgezet.

De repository commit NIET: de aanroeper sluit de transactie (de service doet daarna de auditregel),
zodat vastleggen en auditeren een geheel blijven.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, func, not_, select, true
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.tenant_noodstop_models import TenantNoodstop


@dataclass(frozen=True)
class NoodstopStand:
    """De stand van een klant, zoals de route hem teruggeeft."""

    tenant_id: int
    is_stilgezet: bool
    reden: str | None
    changed_by_user_id: int | None
    changed_by_platform: bool
    changed_at: datetime | None


def geen_rij(tenant_id: int) -> NoodstopStand:
    """De stand van een klant zonder rij: nooit stilgezet."""
    return NoodstopStand(
        tenant_id=tenant_id,
        is_stilgezet=False,
        reden=None,
        changed_by_user_id=None,
        changed_by_platform=False,
        changed_at=None,
    )


class TenantNoodstopRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def is_stilgezet(self, tenant_id: int) -> bool:
        """Staat deze klant stil? Geen rij = nee."""
        stand = (
            await self._db.execute(
                select(TenantNoodstop.is_stilgezet).where(TenantNoodstop.tenant_id == tenant_id)
            )
        ).scalar_one_or_none()
        return stand is True

    async def get(self, tenant_id: int) -> NoodstopStand:
        """De volledige stand van deze klant; zonder rij de stand 'niet stilgezet'."""
        rij = (
            await self._db.execute(
                select(
                    TenantNoodstop.tenant_id,
                    TenantNoodstop.is_stilgezet,
                    TenantNoodstop.reden,
                    TenantNoodstop.changed_by_user_id,
                    TenantNoodstop.changed_by_platform,
                    TenantNoodstop.changed_at,
                ).where(TenantNoodstop.tenant_id == tenant_id)
            )
        ).one_or_none()
        if rij is None:
            return geen_rij(tenant_id)
        return NoodstopStand(
            tenant_id=rij.tenant_id,
            is_stilgezet=rij.is_stilgezet,
            reden=rij.reden,
            changed_by_user_id=rij.changed_by_user_id,
            changed_by_platform=rij.changed_by_platform,
            changed_at=rij.changed_at,
        )

    async def set_stand(
        self,
        tenant_id: int,
        stilgezet: bool,
        *,
        reden: str,
        user_id: int | None,
        door_platform: bool,
    ) -> NoodstopStand | None:
        """Zet de klant stil of hef de stop op; een tweede keer wijzigt dezelfde rij.

        Geeft `None` als het PLATFORMSLOT de wijziging weigert: staat er een stop die door het
        platform is gezet en schrijft de aanroeper niet als platform, dan raakt de upsert die rij
        niet aan (de `WHERE` van `DO UPDATE` is onwaar, dus 0 rijen). Het slot wordt zo in DE
        schrijfstap beslist, niet in een leesstap ervoor: een platformschrijver tussen lezen en
        schrijven kan het slot dan niet meer omzeilen (Gate 2 ronde 2, punt 2).
        """
        invoegen = insert(TenantNoodstop).values(
            tenant_id=tenant_id,
            is_stilgezet=stilgezet,
            reden=reden,
            changed_by_user_id=user_id,
            changed_by_platform=door_platform,
        )
        # Het platform mag altijd schrijven; een ander alleen als er geen platformstop staat.
        slot_vrij = (
            true()
            if door_platform
            else not_(and_(TenantNoodstop.is_stilgezet, TenantNoodstop.changed_by_platform))
        )
        rij = (
            await self._db.execute(
                invoegen.on_conflict_do_update(
                    constraint="uq_tenant_noodstop_tenant",
                    set_={
                        "is_stilgezet": stilgezet,
                        "reden": reden,
                        "changed_by_user_id": user_id,
                        "changed_by_platform": door_platform,
                        "changed_at": func.now(),
                    },
                    where=slot_vrij,
                ).returning(
                    TenantNoodstop.tenant_id,
                    TenantNoodstop.is_stilgezet,
                    TenantNoodstop.reden,
                    TenantNoodstop.changed_by_user_id,
                    TenantNoodstop.changed_by_platform,
                    TenantNoodstop.changed_at,
                )
            )
        ).one_or_none()
        if rij is None:
            return None
        return NoodstopStand(
            tenant_id=rij.tenant_id,
            is_stilgezet=rij.is_stilgezet,
            reden=rij.reden,
            changed_by_user_id=rij.changed_by_user_id,
            changed_by_platform=rij.changed_by_platform,
            changed_at=rij.changed_at,
        )
