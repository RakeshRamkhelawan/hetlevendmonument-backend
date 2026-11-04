"""Pakketstand per klant (pakket aanzetten, dag 1; ADR-005, ADR-039).

Elke methode neemt de klant als parameter en filtert expliciet op `tenant_id`; de klant komt uit de
JWT-context van de route, nooit uit het verzoek. Een ontbrekende rij betekent UIT.

De repository commit NIET: `PackActivationService` commit de stand en schrijft daarna de auditregel
los in `best_effort`; een mislukte auditregel draait de stand dus niet terug.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.rbac_models import User
from src.core.models.tenant_pack_activation_models import TenantPackActivation


@dataclass(frozen=True)
class PackActivation:
    """De stand van een pakket voor een klant, zoals de route hem teruggeeft."""

    pack_id: str
    is_enabled: bool
    enabled_by_user_id: int | None
    enabled_at: datetime


@dataclass(frozen=True)
class PakketStand:
    """De stand van een pakket met wie hem het laatst wijzigde (voor de lijst)."""

    is_enabled: bool
    changed_by_email: str | None
    changed_at: datetime


class TenantPackActivationsRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def is_enabled(self, tenant_id: int, pack_id: str) -> bool:
        """Staat dit pakket voor deze klant aan? Geen rij = uit."""
        stand = (
            await self._db.execute(
                select(TenantPackActivation.is_enabled).where(
                    TenantPackActivation.tenant_id == tenant_id,
                    TenantPackActivation.pack_id == pack_id,
                )
            )
        ).scalar_one_or_none()
        return stand is True

    async def stand_per_pakket(self, tenant_id: int) -> dict[str, PakketStand]:
        """De stand van elk pakket waarvoor deze klant een rij heeft, met de laatste wijziger.

        De wijziger wordt opgezocht BINNEN dezelfde klant: een gebruiker van een andere klant
        komt hier nooit terug (en een verwijderde gebruiker geeft `None`).
        """
        rijen = await self._db.execute(
            select(
                TenantPackActivation.pack_id,
                TenantPackActivation.is_enabled,
                TenantPackActivation.enabled_at,
                User.email,
            )
            .outerjoin(
                User,
                and_(
                    User.id == TenantPackActivation.enabled_by_user_id,
                    User.tenant_id == tenant_id,
                ),
            )
            .where(TenantPackActivation.tenant_id == tenant_id)
        )
        return {
            str(r.pack_id): PakketStand(
                is_enabled=bool(r.is_enabled), changed_by_email=r.email, changed_at=r.enabled_at
            )
            for r in rijen
        }

    async def enabled_pack_ids(self, tenant_id: int) -> set[str]:
        """De id's van alle pakketten die voor deze klant aan staan."""
        rijen = await self._db.execute(
            select(TenantPackActivation.pack_id).where(
                TenantPackActivation.tenant_id == tenant_id,
                TenantPackActivation.is_enabled.is_(True),
            )
        )
        return {str(pack_id) for pack_id in rijen.scalars().all()}

    async def set_enabled(
        self, tenant_id: int, pack_id: str, enabled: bool, *, user_id: int
    ) -> PackActivation:
        """Zet het pakket voor deze klant aan of uit; een tweede keer wijzigt dezelfde rij."""
        invoegen = insert(TenantPackActivation).values(
            tenant_id=tenant_id,
            pack_id=pack_id,
            is_enabled=enabled,
            enabled_by_user_id=user_id,
        )
        rij = (
            await self._db.execute(
                invoegen.on_conflict_do_update(
                    constraint="uq_tenant_pack_activations_tenant_pack",
                    set_={
                        "is_enabled": enabled,
                        "enabled_by_user_id": user_id,
                        "enabled_at": func.now(),
                    },
                ).returning(
                    TenantPackActivation.pack_id,
                    TenantPackActivation.is_enabled,
                    TenantPackActivation.enabled_by_user_id,
                    TenantPackActivation.enabled_at,
                )
            )
        ).one()
        return PackActivation(
            pack_id=rij.pack_id,
            is_enabled=rij.is_enabled,
            enabled_by_user_id=rij.enabled_by_user_id,
            enabled_at=rij.enabled_at,
        )
