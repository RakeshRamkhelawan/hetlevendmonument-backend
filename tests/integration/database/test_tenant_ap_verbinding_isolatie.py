"""Tenantisolatie van de ActivePieces-verbinding, tegen een ECHTE PostgreSQL.

De RLS-policy van de tabel is vandaag inert (de applicatie verbindt als eigenaar, ADR-036
OP-151), dus het expliciete `tenant_id`-filter in de repository is de enige laag. Een dubbelganger
voert dat filter nooit uit; daarom draaien deze tests tegen de echte engine.

Vereist de testdatabase: `SANSKRITISETU_TEST_DATABASE_URL` (poort 5455).
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.rbac_models import Tenant
from src.core.models.tenant_ap_verbinding_models import TenantAPVerbinding
from src.core.repositories.tenant_ap_verbinding_repository import TenantAPVerbindingRepository

pytestmark = pytest.mark.integration


async def _maak_tenant(db: AsyncSession) -> int:
    """Een verse tenant met een unieke naam (`name` en `slug` zijn UNIQUE)."""
    kenmerk = uuid.uuid4().hex[:12]
    tenant = Tenant(name=f"ap-isolatie-{kenmerk}", slug=f"ap-isolatie-{kenmerk}")
    db.add(tenant)
    await db.flush()
    return int(tenant.id)


async def _twee_tenants_met_rij(db: AsyncSession) -> tuple[int, int]:
    repo = TenantAPVerbindingRepository(db)
    tenant_a = await _maak_tenant(db)
    tenant_b = await _maak_tenant(db)
    await repo.upsert(tenant_a, "https://a.example.com", "a@a.example", "versleuteld-a", "proj-a")
    await repo.upsert(tenant_b, "https://b.example.com", "b@b.example", "GEHEIM-VAN-B", "proj-b")
    return tenant_a, tenant_b


@pytest.mark.asyncio
async def test_get_geeft_de_rij_van_de_eigen_tenant(postgres_session: AsyncSession) -> None:
    tenant_a, _ = await _twee_tenants_met_rij(postgres_session)

    rij = await TenantAPVerbindingRepository(postgres_session).get(tenant_a)

    assert rij is not None and rij.project_id == "proj-a"


@pytest.mark.asyncio
async def test_get_toont_geen_veld_van_de_andere_tenant(postgres_session: AsyncSession) -> None:
    tenant_a, _ = await _twee_tenants_met_rij(postgres_session)

    rij = await TenantAPVerbindingRepository(postgres_session).get(tenant_a)

    assert rij is not None and rij.wachtwoord_encrypted != "GEHEIM-VAN-B"


@pytest.mark.asyncio
async def test_get_van_een_tenant_zonder_rij_geeft_none_ook_als_een_ander_er_een_heeft(
    postgres_session: AsyncSession,
) -> None:
    await _twee_tenants_met_rij(postgres_session)
    tenant_c = await _maak_tenant(postgres_session)

    assert await TenantAPVerbindingRepository(postgres_session).get(tenant_c) is None


@pytest.mark.asyncio
async def test_upsert_van_a_laat_de_rij_van_b_ongemoeid(postgres_session: AsyncSession) -> None:
    tenant_a, tenant_b = await _twee_tenants_met_rij(postgres_session)
    repo = TenantAPVerbindingRepository(postgres_session)

    await repo.upsert(
        tenant_a, "https://nieuw.example.com", "nieuw@a.example", "nieuw-a", "p-nieuw"
    )

    rij_b = await repo.get(tenant_b)
    assert rij_b is not None and rij_b.wachtwoord_encrypted == "GEHEIM-VAN-B"


@pytest.mark.asyncio
async def test_upsert_van_a_laat_het_adres_van_b_ongemoeid(postgres_session: AsyncSession) -> None:
    tenant_a, tenant_b = await _twee_tenants_met_rij(postgres_session)
    repo = TenantAPVerbindingRepository(postgres_session)

    await repo.upsert(
        tenant_a, "https://nieuw.example.com", "nieuw@a.example", "nieuw-a", "p-nieuw"
    )

    rij_b = await repo.get(tenant_b)
    assert rij_b is not None and rij_b.base_url == "https://b.example.com"


@pytest.mark.asyncio
async def test_een_tweede_upsert_van_dezelfde_tenant_werkt_de_rij_bij(
    postgres_session: AsyncSession,
) -> None:
    tenant_a, _ = await _twee_tenants_met_rij(postgres_session)
    repo = TenantAPVerbindingRepository(postgres_session)

    await repo.upsert(
        tenant_a, "https://nieuw.example.com", "nieuw@a.example", "nieuw-a", "p-nieuw"
    )

    rij = await repo.get(tenant_a)
    assert rij is not None and rij.project_id == "p-nieuw"


@pytest.mark.asyncio
async def test_een_tweede_upsert_maakt_geen_tweede_rij(postgres_session: AsyncSession) -> None:
    tenant_a, _ = await _twee_tenants_met_rij(postgres_session)
    repo = TenantAPVerbindingRepository(postgres_session)

    await repo.upsert(
        tenant_a, "https://nieuw.example.com", "nieuw@a.example", "nieuw-a", "p-nieuw"
    )

    aantal = await postgres_session.scalar(
        select(func.count())
        .select_from(TenantAPVerbinding)
        .where(TenantAPVerbinding.tenant_id == tenant_a)
    )
    assert aantal == 1


@pytest.mark.asyncio
async def test_upsert_geeft_de_rij_van_de_eigen_tenant_terug(
    postgres_session: AsyncSession,
) -> None:
    tenant_a = await _maak_tenant(postgres_session)

    rij = await TenantAPVerbindingRepository(postgres_session).upsert(
        tenant_a, "https://a.example.com", "a@a.example", "versleuteld-a", "proj-a"
    )

    assert rij.tenant_id == tenant_a


@pytest.mark.asyncio
@pytest.mark.parametrize("ongeldig", [0, -1, True])
async def test_get_weigert_een_ongeldige_tenant_voor_de_query(
    postgres_session: AsyncSession, ongeldig: object
) -> None:
    """`True` staat er met opzet bij: `isinstance(True, int)` is waar in Python."""
    with pytest.raises(ValueError):
        await TenantAPVerbindingRepository(postgres_session).get(ongeldig)  # type: ignore[arg-type]


@pytest.mark.asyncio
@pytest.mark.parametrize("ongeldig", [0, -1, True])
async def test_upsert_weigert_een_ongeldige_tenant_voor_de_query(
    postgres_session: AsyncSession, ongeldig: object
) -> None:
    with pytest.raises(ValueError):
        await TenantAPVerbindingRepository(postgres_session).upsert(
            ongeldig,  # type: ignore[arg-type]
            "https://x.example.com",
            "x@x.example",
            "v",
            "p",
        )
