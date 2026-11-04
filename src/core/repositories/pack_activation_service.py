"""Pakketten per klant aan- en uitzetten, met een auditregel (pakket aanzetten, dag 1; ADR-005, ADR-039).

De service sluit de schrijfstap af: eerst de pakketstand vastleggen en committen, daarna de auditregel
(backend-regel: primaire data eerst, audit blokkeert nooit). De auditregel zelf wordt als functie
meegegeven door `api/v1/packs/dependencies.py`: de service importeert zo geen `governance`, want dat
telt mee in de koppelingsplafonds van agent_runtime (DSM-006, DSM-008; gemeten 2026-10-14: 10 > 9
en Ce 246 > 244 toen de service `AuditService` zelf importeerde). De router praat alleen
met deze service (ADR-033: geen sessie, geen governance en geen repository in Laag 1).

De klant komt als parameter binnen en is door de route uit de JWT-context gehaald; een
`tenant_id` uit het verzoek komt hier nooit.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.repositories.tenant_pack_activations_repository import (
    PackActivation,
    PakketStand,
    TenantPackActivationsRepository,
)

__all__ = [
    "EVENT_TYPE",
    "AuditSchrijver",
    "PackActivation",
    "PakketStand",
    "PackActivationService",
]

EVENT_TYPE = "pack_activation_changed"

#: (stand, tenant_id, user_id, source_ip, endpoint) -> schrijft de auditregel; mag niet blokkeren.
AuditSchrijver = Callable[[PackActivation, int, int, str, str], Awaitable[None]]


class PackActivationService:
    def __init__(self, db: AsyncSession, audit: AuditSchrijver | None = None) -> None:
        self._db = db
        self._audit = audit
        self._repo = TenantPackActivationsRepository(db)

    async def stand_per_pakket(self, tenant_id: int) -> dict[str, PakketStand]:
        """De stand per pakket voor deze klant, met wie hem het laatst wijzigde."""
        return await self._repo.stand_per_pakket(tenant_id)

    async def set_enabled(
        self,
        tenant_id: int,
        pack_id: str,
        enabled: bool,
        *,
        user_id: int,
        source_ip: str,
        endpoint: str,
    ) -> PackActivation:
        """Zet het pakket aan of uit en legt de wijziging vast; idempotent."""
        stand = await self._repo.set_enabled(tenant_id, pack_id, enabled, user_id=user_id)
        await self._db.commit()
        if self._audit is not None:
            await self._audit(stand, tenant_id, user_id, source_ip, endpoint)
        return stand
