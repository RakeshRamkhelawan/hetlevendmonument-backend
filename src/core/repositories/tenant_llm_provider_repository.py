"""Opslag van de providerketen van een tenant. Pure persistentie, geen beleid.

**Waarom hier geen SSRF-controle en geen versleuteling staat.** Dat stond er wel in de eerste
versie, en `tests/architecture/test_dsm_009_no_medium_backward.py` viel daarop om: de
DSM-indeling rekent `src/core/repositories` tot `infra` en `src/core/security` tot `auth`, en
infra mag niet van auth afhangen. Die regel wijst hier iets echts aan -- opslag hoort niet te
weten wat een geldig adres is of hoe een sleutel versleuteld wordt.

Het beleid zit daarom in `src/core/services/tenant_llm_provider_service.py`. Deze klasse krijgt
een adres dat AL gevalideerd is en een sleutel die AL versleuteld is, en slaat die op. Dat het
zo blijft, bewaakt
`tests/architecture/test_elk_schrijfpad_naar_een_klanteindpunt_wordt_gevalideerd.py`.

**Wat hier WEL beschermt.** De tabel heeft RLS-policies, maar die zijn vandaag inert: de
applicatie verbindt als eigenaar van de tabellen (ADR-036 OP-151, gemeten). Het expliciete
`tenant_id`-filter op elke methode hieronder is dus niet een tweede laag maar de ENIGE laag.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.rbac_models import Tenant
from src.core.models.tenant_llm_provider_models import TenantLLMProvider


@dataclass(frozen=True)
class OpgeslagenProvider:
    """Een rij zoals hij in de database staat -- de sleutel nog VERSLEUTELD.

    Ontsleutelen is werk van de servicelaag. Deze klasse geeft nooit een leesbare sleutel
    terug, ook niet per ongeluk, omdat ze er geen kan maken.
    """

    id: int
    volgorde: int
    naam: str
    base_url: str
    model: str
    api_key_encrypted: str | None
    actief: bool


class TenantLLMProviderRepository:
    """Leest en schrijft de providerrijen van EEN tenant."""

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    @staticmethod
    def _controleer_tenant(tenant_id: int) -> None:
        if not isinstance(tenant_id, int) or isinstance(tenant_id, bool) or tenant_id <= 0:
            raise ValueError("tenant_id moet een positief geheel getal zijn")

    async def mag_extern(self, tenant_id: int) -> bool:
        """Staat deze tenant KLANT-EIGEN externe providers toe? Standaard is dat FALSE.

        Deze vlag gaat over de eindpunten die de klant zelf laat inrichten, NIET over Mistral: dat is de
        platformverwerker (besluit Rakesh 2026-10-15, bevestigd door de regie 2026-10-19) en wordt hierdoor
        niet geblokkeerd. Zie `src/core/shared/tenant_llm_keuze.py`.
        """
        self._controleer_tenant(tenant_id)
        resultaat = await self._db.execute(
            select(Tenant.externe_providers_toegestaan).where(Tenant.id == tenant_id)
        )
        return bool(resultaat.scalar_one_or_none())

    async def instellingen(self, tenant_id: int) -> dict[str, object] | None:
        """`tenants.settings` van deze tenant (JSON-kolom), of `None` als er geen bruikbare rij is."""
        self._controleer_tenant(tenant_id)
        resultaat = await self._db.execute(select(Tenant.settings).where(Tenant.id == tenant_id))
        waarde = resultaat.scalar_one_or_none()
        return dict(waarde) if isinstance(waarde, dict) else None

    async def alle(self, tenant_id: int) -> list[OpgeslagenProvider]:
        """Alle rijen van deze tenant, op volgorde."""
        self._controleer_tenant(tenant_id)
        resultaat = await self._db.execute(
            select(TenantLLMProvider)
            .where(TenantLLMProvider.tenant_id == tenant_id)
            .order_by(TenantLLMProvider.volgorde)
        )
        return [self._naar_rij(rij) for rij in resultaat.scalars().all()]

    async def actieve(self, tenant_id: int) -> list[OpgeslagenProvider]:
        """Alleen de actieve rijen -- dit is de failoverketen van ADR-026."""
        self._controleer_tenant(tenant_id)
        resultaat = await self._db.execute(
            select(TenantLLMProvider)
            .where(
                TenantLLMProvider.tenant_id == tenant_id,
                TenantLLMProvider.actief.is_(True),
            )
            .order_by(TenantLLMProvider.volgorde)
        )
        return [self._naar_rij(rij) for rij in resultaat.scalars().all()]

    async def voeg_toe(
        self,
        tenant_id: int,
        *,
        volgorde: int,
        naam: str,
        base_url: str,
        model: str,
        api_key_encrypted: str | None = None,
        actief: bool = True,
    ) -> int:
        """Sla een rij op.

        `base_url` hoort AL gevalideerd te zijn en `api_key_encrypted` AL versleuteld; deze
        klasse controleert dat niet en kan dat ook niet. Roep dit daarom nooit rechtstreeks aan
        -- de weg loopt via `TenantLLMProviderService`, en een architectuurbewaker houdt dat zo.
        """
        self._controleer_tenant(tenant_id)
        rij = TenantLLMProvider(
            tenant_id=tenant_id,
            volgorde=volgorde,
            naam=naam,
            base_url=base_url,
            model=model,
            api_key_encrypted=api_key_encrypted,
            actief=actief,
        )
        self._db.add(rij)
        await self._db.flush()
        return int(rij.id)

    @staticmethod
    def _naar_rij(rij: TenantLLMProvider) -> OpgeslagenProvider:
        return OpgeslagenProvider(
            id=rij.id,
            volgorde=rij.volgorde,
            naam=rij.naam,
            base_url=rij.base_url,
            model=rij.model,
            api_key_encrypted=rij.api_key_encrypted,
            actief=rij.actief,
        )
