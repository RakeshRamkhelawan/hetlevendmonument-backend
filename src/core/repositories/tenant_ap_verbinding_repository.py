"""Opslag van de ActivePieces-verbinding van een tenant. Pure persistentie, geen beleid.

**Waarom hier geen versleuteling staat.** De DSM-indeling rekent `src/core/repositories` tot
`infra` en `src/core/security` tot `auth`, en infra mag niet van auth afhangen. De servicelaag
versleutelt het wachtwoord voor het schrijven en ontsleutelt na het lezen; deze klasse geeft
het opgeslagen (versleutelde) veld ongewijzigd door en kan er geen leesbare variant van maken.

**Wat hier WEL beschermt.** De RLS-policy van de tabel is vandaag inert (applicatie verbindt als
eigenaar, ADR-036 OP-151). Het expliciete `tenant_id`-filter op elke methode is dus de ENIGE
laag. De repository commit niet; de aanroeper beheert de transactie.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.tenant_ap_verbinding_models import TenantAPVerbinding


@dataclass(frozen=True)
class OpgeslagenAPVerbinding:
    """Een rij zoals hij in de database staat -- het wachtwoord nog VERSLEUTELD."""

    id: int
    tenant_id: int
    base_url: str
    email: str
    wachtwoord_encrypted: str
    project_id: str
    created_at: datetime
    updated_at: datetime


class TenantAPVerbindingRepository:
    """Leest en schrijft de ActivePieces-verbinding van EEN tenant."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    @staticmethod
    def _controleer_tenant(tenant_id: int) -> None:
        if not isinstance(tenant_id, int) or isinstance(tenant_id, bool) or tenant_id <= 0:
            raise ValueError("tenant_id moet een positief geheel getal zijn")

    async def get(self, tenant_id: int) -> OpgeslagenAPVerbinding | None:
        """De verbinding van deze tenant, of `None` als die er niet is."""
        self._controleer_tenant(tenant_id)
        resultaat = await self._db.execute(
            select(TenantAPVerbinding).where(TenantAPVerbinding.tenant_id == tenant_id)
        )
        rij = resultaat.scalar_one_or_none()
        return None if rij is None else self._naar_rij(rij)

    async def upsert(
        self,
        tenant_id: int,
        base_url: str,
        email: str,
        wachtwoord_encrypted: str,
        project_id: str,
    ) -> OpgeslagenAPVerbinding:
        """Maak de verbinding van deze tenant aan of werk hem bij; raakt nooit een andere tenant.

        Het conflictdoel is de unieke `tenant_id`, dus de UPDATE-tak kan alleen de rij van
        precies deze tenant raken. `wachtwoord_encrypted` hoort AL versleuteld te zijn; dat kan
        deze klasse niet controleren.
        """
        self._controleer_tenant(tenant_id)
        waarden = {
            "base_url": base_url,
            "email": email,
            "wachtwoord_encrypted": wachtwoord_encrypted,
            "project_id": project_id,
        }
        instructie = (
            insert(TenantAPVerbinding)
            .values(tenant_id=tenant_id, **waarden)
            .on_conflict_do_update(
                index_elements=[TenantAPVerbinding.tenant_id],
                set_={**waarden, "updated_at": func.now()},
            )
            .returning(
                TenantAPVerbinding.id,
                TenantAPVerbinding.tenant_id,
                TenantAPVerbinding.base_url,
                TenantAPVerbinding.email,
                TenantAPVerbinding.wachtwoord_encrypted,
                TenantAPVerbinding.project_id,
                TenantAPVerbinding.created_at,
                TenantAPVerbinding.updated_at,
            )
        )
        rij = (await self._db.execute(instructie)).one()
        return OpgeslagenAPVerbinding(
            id=rij.id,
            tenant_id=rij.tenant_id,
            base_url=rij.base_url,
            email=rij.email,
            wachtwoord_encrypted=rij.wachtwoord_encrypted,
            project_id=rij.project_id,
            created_at=rij.created_at,
            updated_at=rij.updated_at,
        )

    @staticmethod
    def _naar_rij(rij: TenantAPVerbinding) -> OpgeslagenAPVerbinding:
        return OpgeslagenAPVerbinding(
            id=rij.id,
            tenant_id=rij.tenant_id,
            base_url=rij.base_url,
            email=rij.email,
            wachtwoord_encrypted=rij.wachtwoord_encrypted,
            project_id=rij.project_id,
            created_at=rij.created_at,
            updated_at=rij.updated_at,
        )
