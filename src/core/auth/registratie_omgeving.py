"""Een eigen omgeving voor een nieuwe klant (SP-KLANT-01 dag 1, meetlat scenario 1 stap 2).

Een bezoeker die zich registreert heeft geen tenant. Deze module maakt er een aan, en de
AANROEPER neemt die tenant daarna aan met `adopt_tenant`. De tenant komt dus uit de nieuwe
rij en nooit uit het verzoek: er is hier geen parameter waar een header, query, body of slug
in kan.

Wat hier BEWUST niet staat: een organisatienaam. De bedrijfsnaam komt in de onboarding
(dag 2); tot dan krijgt de omgeving een neutrale, unieke naam. Een naam uit het verzoek zou
bovendien tegen de unieke index op `tenants.name` botsen en daarmee verraden dat een
organisatie al bestaat.
"""

from __future__ import annotations

import uuid

from loguru import logger
from sqlalchemy import delete, func, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from src import config
from src.core.database.bypass_session import pre_auth_lookup
from src.core.models.rbac_models import Tenant, with_four_eyes_defaults

#: De rol van de eerste gebruiker van een nieuwe omgeving. Server-side, nooit uit het verzoek.
EERSTE_GEBRUIKER_ROL = "admin"

#: Sleutel voor `pg_advisory_xact_lock`: serialiseert de eerste registratie in single_tenant.
_SINGLE_TENANT_SLOT = 7_201_004


def is_single_tenant() -> bool:
    """Leest de modus BIJ ELKE AANVRAAG.

    `src.config.DEPLOYMENT_MODE` is een moduleconstante die bij het importeren wordt gezet.
    Een kopie op naam (`from src.config import DEPLOYMENT_MODE`) bevriest hem; via het
    modulekenmerk lezen volgt een wijziging wel.
    """
    return bool(config.DEPLOYMENT_MODE == "single_tenant")


def _is_postgres(db: AsyncSession) -> bool:
    bind = getattr(db, "bind", None)
    dialect = getattr(bind, "dialect", None)
    return bool(dialect is not None and dialect.name == "postgresql")


async def installatie_heeft_al_een_omgeving(db: AsyncSession) -> bool:
    """True zodra er een tenant bestaat. `tenants` heeft geen afschermingsregel.

    Neemt eerst een transactieslot op PostgreSQL, zodat twee gelijktijdige eerste
    registraties in single_tenant niet allebei een lege installatie zien. Het slot valt
    weg bij de commit waarmee de nieuwe tenant wordt vastgelegd.
    """
    if _is_postgres(db):
        await db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _SINGLE_TENANT_SLOT})
    async with pre_auth_lookup(db) as opzoeker:
        aantal = (await opzoeker.execute(select(func.count()).select_from(Tenant))).scalar_one()
    return bool(aantal > 0)


async def maak_omgeving(db: AsyncSession) -> int:
    """Voegt een nieuwe tenant toe (flush, geen commit) en geeft zijn id.

    De slug staat los van de naam: een willekeurig achtervoegsel, geen afleiding uit
    invoer. Zo kan geen registratie een slug uitkiezen die al bestaat of gereserveerd is.
    """
    achtervoegsel = uuid.uuid4().hex[:12]
    tenant = Tenant(
        name=f"Nieuwe omgeving {achtervoegsel}",
        slug=f"org-{achtervoegsel}",
        is_active=True,
        subscription_status="active",
        # ADR-039: een nieuwe omgeving krijgt de vier-ogen-standaard (debiteurenagent dag 3).
        settings=with_four_eyes_defaults(None),
    )
    db.add(tenant)
    await db.flush()
    return tenant.id


async def zaai_rollen(db: AsyncSession, tenant_id: int) -> None:
    """Zaait de standaardrollen van een nieuwe tenant, met dezelfde zaaier als elders.

    `RBACService.ensure_default_roles` is ook wat `zaai_standaardrollen` (tenantbeheer) en
    het opstarten gebruiken; dit is dus geen tweede variant. Moet binnen `adopt_tenant`
    draaien, want `roles` heeft een afschermingsregel. Commit zelf (ook de tenant).
    """
    from src.core.services.rbac_service import RBACService

    await RBACService(db).ensure_default_roles(tenant_id)


async def ruim_mislukte_omgeving_op(db: AsyncSession, tenant_id: int) -> None:
    """Haalt een tenant weg waar de registratie halverwege op stukbleef.

    Bedoeld om geen lege omgeving achter te laten. Faalt het opruimen zelf, dan komt dat in
    het log en blijft de oorspronkelijke fout de uitkomst van het verzoek. `roles` en
    `role_permissions` verdwijnen mee via `ON DELETE CASCADE`.
    """
    try:
        await db.rollback()
        await db.execute(delete(Tenant).where(Tenant.id == tenant_id))
        await db.commit()
    except SQLAlchemyError as e:
        logger.error(
            "Opruimen van mislukte registratie-omgeving %s faalde: %s: %s",
            tenant_id,
            type(e).__name__,
            e,
            exc_info=True,
        )
