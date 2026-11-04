"""Gedeelde dependencies voor het `packs`-domein (pakket aanzetten, dag 1; ADR-033 Laag 2).

De router (`router.py`) importeert hier alles vandaan en NIETS rechtstreeks uit `governance`,
`agents`, `als` of de repository-laag (ADR-033 par. 2): dat deed de HR-router eerst wel en vier
architecture-guards vingen dat.

- `require_packs_execute` / `require_packs_manage`: het recht `packs:execute` (lijst: elke
  medewerker met dat recht) en `packs:manage` (aanzetten: alleen de beheerder, via `*:*`), uit de
  database. De gebruiker komt terug zodat de route zijn id voor de auditregel heeft; de klant komt
  uit de JWT-context (`require_tenant_id`), nooit uit het verzoek (ADR-003).
- `get_pack_catalogue`: de pakketten uit de catalogus (`config/domain_packs.yaml`), op id. Alleen
  wat in de catalogus staat kan worden aangezet of getoond.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.api.auth.dependencies import validate_csrf_token
from src.core.api.v1.agentic.dependencies import DomainPackOrchestrator
from src.core.api.v1.admin.dependencies import (
    RBACService,
    UserResponse,
    get_current_user,
    get_db,
    require_resource_permission,
)
from src.core.governance.rate_limiter import pack_activation_read_limit, pack_activation_write_limit
from src.core.governance.services.audit_service import AuditService
from src.core.middleware.tenant_context import require_tenant_id
from src.core.repositories.pack_activation_service import (
    EVENT_TYPE,
    PackActivation,
    PackActivationService,
    PakketStand,
)
from src.core.utils.best_effort import best_effort

from .schemas import PACK_ID_MAX_LENGTE

__all__ = [
    "CataloguePack",
    "PACK_ID_MAX_LENGTE",
    "PackActivationService",
    "PakketStand",
    "UserResponse",
    "get_pack_activation_service",
    "get_pack_catalogue",
    "kan_pakketten_beheren",
    "pack_activation_read_limit",
    "pack_activation_write_limit",
    "require_packs_execute",
    "require_packs_manage",
    "require_tenant_id",
    "validate_csrf_token",
]


def _vereis_pack_recht(actie: str) -> Callable[..., Awaitable[UserResponse]]:
    """Het recht `packs:<actie>` uit de database; de gebruiker komt terug (voor de auditregel)."""
    toets = require_resource_permission("packs", actie)

    async def _afhankelijkheid(
        current_user: UserResponse = Depends(get_current_user),
        _user_id: int = Depends(toets),
    ) -> UserResponse:
        return current_user

    return _afhankelijkheid


require_packs_execute = _vereis_pack_recht("execute")
require_packs_manage = _vereis_pack_recht("manage")


async def kan_pakketten_beheren(
    current_user: UserResponse = Depends(require_packs_execute),
    db: AsyncSession = Depends(get_db),
) -> bool:
    """Heeft de aanvrager ook `packs:manage`? Een vraag, geen weigering (geen 403, geen waarschuwing).

    De lijst is er voor iedereen met `packs:execute`; wie het pakket het laatst wijzigde (een
    e-mailadres) is alleen voor de beheerder (AVG-dataminimalisatie, besluit regie 2026-10-15).
    """
    return await RBACService(db).has_permission(current_user.id, "packs", "manage")


def _schrijf_audit_voor(
    db: AsyncSession,
) -> Callable[[PackActivation, int, int, str, str], Awaitable[None]]:
    """De auditregel voor een pakketwijziging, na de commit van de stand en in `best_effort`."""

    async def _schrijf(
        stand: PackActivation, tenant_id: int, user_id: int, source_ip: str, endpoint: str
    ) -> None:
        # Alleen het pakket en de stand: geen namen, geen e-mailadressen.
        async with best_effort(f"{EVENT_TYPE} audit log", db_session=db):
            await AuditService.log_event(
                db=db,
                event_type=EVENT_TYPE,
                severity="low",
                source_ip=source_ip,
                endpoint=endpoint,
                description="Pakket aangezet" if stand.is_enabled else "Pakket uitgezet",
                tenant_id=tenant_id,
                user_id=user_id,
                action=EVENT_TYPE,
                metadata={"pack_id": stand.pack_id, "is_enabled": stand.is_enabled},
            )
            await db.commit()

    return _schrijf


async def get_pack_activation_service(db: AsyncSession = Depends(get_db)) -> PackActivationService:
    """De pakketstand per klant, met de sessie van dit verzoek."""
    return PackActivationService(db, audit=_schrijf_audit_voor(db))


@dataclass(frozen=True)
class CataloguePack:
    """Wat de route van een pakket uit de catalogus toont."""

    pack_id: str
    name: str
    description: str | None
    display_name: str | None = None


def get_pack_catalogue() -> dict[str, CataloguePack]:
    """De pakketten uit de catalogus (`config/domain_packs.yaml`), op id.

    `name` is de Engelse naam, `display_name` de Nederlandse weergavenaam voor het scherm en `description` de
    korte Nederlandse omschrijving (die hebben alleen de pilootpakketten; de rest blijft leeg). Staat hier en
    niet in de service: een service in `repositories` die `als` importeert is een infra->agent_runtime-paar
    (`test_dsm_no_agent_runtime_infra_circular_pair`).
    """
    return {
        pack_id: CataloguePack(
            pack_id=pack_id,
            name=str(pack.name),
            description=getattr(pack, "description", None),
            display_name=getattr(pack, "display_name", None),
        )
        for pack_id, pack in DomainPackOrchestrator().catalog.packs.items()
    }
