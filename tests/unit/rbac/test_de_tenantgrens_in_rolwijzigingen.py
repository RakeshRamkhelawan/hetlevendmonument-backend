"""De tenantgrens bij het toekennen en intrekken van rollen (OP-183).

Gemeten gat voor deze fix: POST /api/rbac/users/assign-role (en revoke-role, en beide
bulk-varianten) neemt user_id ongevalideerd uit de request body
(src/core/api/v1/rbac/assignment_router.py:20) terwijl de tenant uit de middlewarecontext
komt (:43). RBACService.assign_role deed twee queries -- op Role en op user_roles -- en
daarna user_roles.insert(), zonder ooit User op te halen en dus zonder enige vergelijking
met User.tenant_id (src/core/services/rbac_service.py:384-443).

De ORM-tenantfilter kan dit niet afvangen: user_roles heeft geen tenant_id-kolom
(src/core/models/rbac_models.py:36-43) en de filter laat INSERT bewust ongemoeid
(src/core/database/tenant_query_filter.py:230-231).

Deze toetsen draaien tegen een ECHTE (sqlite-)sessie en niet tegen een AsyncMock. Dat is
de les van OP-185: een dubbel geeft een vaste rij terug ongeacht de query, waardoor een
WHERE-clausule onzichtbaar is en stil verwijderd kan worden terwijl de guard groen blijft.

Mutatiebewijs in BEIDE richtingen: de weigerende kant EN de legitieme kant, zodat
"weiger alles" geen geldige oplossing is.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.models.rbac_models import Role, User, user_roles
from src.core.services.rbac_service import RBACService

EIGEN_TENANT = 1
VREEMDE_TENANT = 9


@pytest_asyncio.fixture
async def sessie() -> AsyncIterator[AsyncSession]:
    """Een echte async sessie met alleen de tabellen die dit pad aanraakt."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from src.core.models.rbac_models import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    tabellen = [Base.metadata.tables[naam] for naam in ("tenants", "roles", "users", "user_roles")]
    async with engine.begin() as conn:
        await conn.run_sync(lambda c: Base.metadata.create_all(c, tables=tabellen))
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as open_sessie:
        yield open_sessie
    await engine.dispose()


async def _zaai(sessie: AsyncSession) -> tuple[int, int, int]:
    """Een rol in de eigen tenant, een eigen gebruiker en een gebruiker van een ander."""
    rol = Role(name="editor", tenant_id=EIGEN_TENANT)
    eigen = User(tenant_id=EIGEN_TENANT, email="eigen@example.com", hashed_password="x")
    vreemd = User(tenant_id=VREEMDE_TENANT, email="vreemd@example.com", hashed_password="x")
    sessie.add_all([rol, eigen, vreemd])
    await sessie.commit()
    return int(rol.id), int(eigen.id), int(vreemd.id)


async def _rijen(sessie: AsyncSession, user_id: int) -> list[int]:
    treffer = await sessie.execute(
        select(user_roles.c.role_id).where(user_roles.c.user_id == user_id)
    )
    return [int(r[0]) for r in treffer.all()]


class TestToekennen:
    @pytest.mark.asyncio
    async def test_een_gebruiker_van_een_andere_tenant_krijgt_de_rol_niet(
        self, sessie: AsyncSession
    ) -> None:
        """De weigerende richting: dit is het gat dat OP-183 beschrijft."""
        _, _, vreemd_id = await _zaai(sessie)

        gelukt = await RBACService(sessie).assign_role(vreemd_id, "editor", EIGEN_TENANT)

        assert gelukt is False
        assert await _rijen(sessie, vreemd_id) == []

    @pytest.mark.asyncio
    async def test_een_gebruiker_in_de_eigen_tenant_krijgt_de_rol_wel(
        self, sessie: AsyncSession
    ) -> None:
        """De legitieme richting, zodat "weiger alles" afvalt."""
        rol_id, eigen_id, _ = await _zaai(sessie)

        gelukt = await RBACService(sessie).assign_role(eigen_id, "editor", EIGEN_TENANT)

        assert gelukt is True
        assert await _rijen(sessie, eigen_id) == [rol_id]

    @pytest.mark.asyncio
    async def test_een_onbekende_gebruiker_krijgt_hetzelfde_antwoord(
        self, sessie: AsyncSession
    ) -> None:
        """Onbekend en vreemd geven hetzelfde antwoord: geen bestaansorakel."""
        await _zaai(sessie)

        gelukt = await RBACService(sessie).assign_role(424242, "editor", EIGEN_TENANT)

        assert gelukt is False


class TestIntrekken:
    @pytest.mark.asyncio
    async def test_de_rol_van_een_vreemde_gebruiker_blijft_staan(
        self, sessie: AsyncSession
    ) -> None:
        """Intrekken is even ernstig als toekennen: dit wist andermans rol niet."""
        rol_id, _, vreemd_id = await _zaai(sessie)
        # De vreemde gebruiker heeft de rol al -- gezet buiten de service om, want de
        # service weigert hem nu juist toe te kennen.
        await sessie.execute(user_roles.insert().values(user_id=vreemd_id, role_id=rol_id))
        await sessie.commit()

        gelukt = await RBACService(sessie).revoke_role(vreemd_id, "editor", EIGEN_TENANT)

        assert gelukt is False
        assert await _rijen(sessie, vreemd_id) == [rol_id]

    @pytest.mark.asyncio
    async def test_de_eigen_rol_wordt_wel_ingetrokken(self, sessie: AsyncSession) -> None:
        """De legitieme richting van het intrekpad."""
        rol_id, eigen_id, _ = await _zaai(sessie)
        await sessie.execute(user_roles.insert().values(user_id=eigen_id, role_id=rol_id))
        await sessie.commit()

        gelukt = await RBACService(sessie).revoke_role(eigen_id, "editor", EIGEN_TENANT)

        assert gelukt is True
        assert await _rijen(sessie, eigen_id) == []


class TestDeBulkvarianten:
    """Gemeten: bulk_assign_roles/:715 en bulk_revoke_roles/:727 lopen DOOR assign_role en
    revoke_role heen. Deze toets legt dat vast, zodat de guard niet stil omzeild wordt
    door een toekomstige bulk-implementatie met een eigen insert."""

    @pytest.mark.asyncio
    async def test_bulk_scheidt_de_eigen_van_de_vreemde_gebruiker(
        self, sessie: AsyncSession
    ) -> None:
        rol_id, eigen_id, vreemd_id = await _zaai(sessie)

        uitkomst = await RBACService(sessie).bulk_assign_roles(
            [eigen_id, vreemd_id], "editor", EIGEN_TENANT
        )

        per_gebruiker = {int(r["user_id"]): bool(r["success"]) for r in uitkomst}
        assert per_gebruiker == {eigen_id: True, vreemd_id: False}
        assert await _rijen(sessie, eigen_id) == [rol_id]
        assert await _rijen(sessie, vreemd_id) == []
