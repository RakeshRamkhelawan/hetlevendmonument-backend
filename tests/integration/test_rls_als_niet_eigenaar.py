"""Row Level Security werkt echt: als NIET-eigenaar, via de echte sessielaag (brief 2026-10-21, ADR-036 OP-113 en OP-151).

**Wat dit toevoegt aan `tests/integration/security/`.** Daar wordt het gedrag van de policies per tabel gemeten met
een kale `SET ROLE`. Deze test gaat door de ECHTE laag: een SQLAlchemy-engine die als `sanskritisetu_app` verbindt,
met de `begin`-hook `_zet_tenantcontext` die de tenant uit de ContextVar haalt. Dat is het pad dat een klant in
productie neemt. Twee dingen worden bewezen:

1. **Klant A leest geen rij van klant B**, op een steekproef over de gebieden uit de brief: facturen
   (`receivables`, de debiteurenketen), gebruikers (`users`), personeel/HR (`employee_skills`, `skills`) en
   `agents`. Een bonnentabel bestaat op 8fdb38cb nog niet; die komt in de steekproef zodra hij er is.
2. **Ook niet na een commit midden in het verzoek** (OP-113). `SET LOCAL` verdween bij een commit en liet een LEGE
   tenantcontext achter; de policies zagen dan of niets of alles. De hook zet daarom per TRANSACTIE opnieuw
   `set_config(..., true)`, en deze test commit tussen twee leesacties door.

Daarnaast meet `meet_rol` (de startcontrole uit `applicatierol_controle.py`) op een ECHTE verbinding: als
`postgres` (superuser) geeft hij problemen, als `sanskritisetu_app` geen.

**Mutatiebewijs (2026-10-21), beide richtingen, een regel per element:**
- `_zet_tenantcontext` doet niets (vroeg `return`)            -> 16 ROOD (alle lees- en commit-tests), 9 groen
- policy op `receivables` vervangen door `USING (true)`        -> 5 ROOD, precies de tests van die tabel; de
  andere vier tabellen blijven groen (de legitieme kant)
- ongewijzigd                                                  -> 25 GROEN
De startcontrole zelf is per voorwaarde gemuteerd in `tests/unit/database/test_applicatierol_controle.py`.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncGenerator, Iterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

import psycopg2
import pytest
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT, connection as PgConnection
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool
from tests.fixtures.testdatabase import testdatabase_poort
from tests.integration.security.test_the_application_role_is_confined_to_its_tenant import (
    _ROL,
    _SCRATCH_DB,
    _bouw_verse_database,
    _dsn,
    _postgres_bereikbaar,
)

from src.core.database.applicatierol_controle import beoordeel_rol, meet_rol
from src.core.middleware.tenant_context import set_tenant_id

pytestmark = [
    pytest.mark.integration,
    pytest.mark.security,
    pytest.mark.skipif(
        not _postgres_bereikbaar(),
        reason="vereist PostgreSQL op de netwerkpoort uit SANSKRITISETU_TEST_DATABASE_URL",
    ),
]

#: De steekproef. Alle zes hebben `tenant_id`; elke klant krijgt er twee rijen in.
STEEKPROEF = ("receivables", "users", "agents", "skills", "employee_skills")


@dataclass(frozen=True)
class Klanten:
    a: int
    b: int


def _nieuw_id(cur: psycopg2.extensions.cursor) -> int:
    rij = cur.fetchone()
    assert rij is not None, "INSERT ... RETURNING id gaf geen rij terug: de opstelling is mislukt"
    return int(rij[0])


@pytest.fixture(scope="module")
def db() -> Iterator[PgConnection]:
    """Verse database uit de migratieketen; de eigenaarsverbinding dient alleen de opstelling."""
    _bouw_verse_database()
    conn = psycopg2.connect(_dsn(_SCRATCH_DB))
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def klanten(db: PgConnection) -> Klanten:
    """Twee klanten die in elke steekproeftabel elk TWEE rijen hebben, aangemaakt als eigenaar."""
    with db.cursor() as cur:
        cur.execute(
            "INSERT INTO tenants (name, slug, is_active, max_users, max_agents, max_storage_gb) "
            "VALUES ('RLS A', 'rls-echt-a', true, 10, 50, 5), ('RLS B', 'rls-echt-b', true, 10, 50, 5)"
        )
        cur.execute("SELECT slug, id FROM tenants WHERE slug IN ('rls-echt-a', 'rls-echt-b')")
        tenants = dict(cur.fetchall())
        for tenant in tenants.values():
            for volgnummer in (1, 2):
                cur.execute(
                    "INSERT INTO users (tenant_id, email) VALUES (%s, %s) RETURNING id",
                    (tenant, f"{uuid.uuid4().hex[:10]}@rls-echt.example.com"),
                )
                user_id = _nieuw_id(cur)
                cur.execute(
                    "INSERT INTO skills (tenant_id, name) VALUES (%s, %s) RETURNING id",
                    (tenant, f"vaardigheid-{tenant}-{volgnummer}"),
                )
                skill_id = _nieuw_id(cur)
                cur.execute(
                    "INSERT INTO employee_skills (tenant_id, user_id, skill_id, level) "
                    "VALUES (%s, %s, %s, 3)",
                    (tenant, user_id, skill_id),
                )
                cur.execute(
                    "INSERT INTO agents (tenant_id, name, agent_type) VALUES (%s, %s, 'test')",
                    (tenant, f"agent-{tenant}-{volgnummer}"),
                )
                cur.execute(
                    "INSERT INTO receivables (tenant_id, customer_name, customer_email, "
                    "invoice_number, amount, currency, due_date, status, source) "
                    "VALUES (%s, 'Klant', 'klant@rls-echt.example.com', %s, 10.00, 'EUR', "
                    "'2026-12-01', 'open', 'handmatig')",
                    (tenant, f"F-{tenant}-{volgnummer}"),
                )
    return Klanten(a=tenants["rls-echt-a"], b=tenants["rls-echt-b"])


def _async_url() -> str:
    gebruiker = os.environ.get("POSTGRES_USER", "postgres")
    wachtwoord = os.environ.get("POSTGRES_PASSWORD", "postgres")
    return (
        f"postgresql+asyncpg://{gebruiker}:{wachtwoord}@127.0.0.1:"
        f"{testdatabase_poort()}/{_SCRATCH_DB}"
    )


@asynccontextmanager
async def _applicatiesessie(tenant: int | None) -> AsyncGenerator[AsyncSession]:
    """Een sessie die als `sanskritisetu_app` draait, met de tenant uit de ContextVar."""
    engine = create_async_engine(
        _async_url(), poolclass=NullPool, connect_args={"server_settings": {"role": _ROL}}
    )
    set_tenant_id(tenant)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as sessie:
            yield sessie
    finally:
        set_tenant_id(None)
        await engine.dispose()


async def _klanten_in(sessie: AsyncSession, tabel: str) -> list[int]:
    """De tenant-ids van de rijen die deze sessie in `tabel` ziet."""
    uitkomst = await sessie.execute(text(f"SELECT tenant_id FROM {tabel}"))  # nosec B608 - vaste lijst
    return [int(rij[0]) for rij in uitkomst.all()]


class TestDeSessieDraaitAlsNietEigenaar:
    """De meting is niet leeg: de sessie IS de applicatierol en die omzeilt RLS niet."""

    async def test_de_sessie_draait_als_de_applicatierol(self, klanten: Klanten) -> None:
        async with _applicatiesessie(klanten.a) as sessie:
            rol = (await sessie.execute(text("SELECT current_user"))).scalar_one()

        assert rol == _ROL

    async def test_de_applicatierol_wordt_door_de_startcontrole_goedgekeurd(
        self, klanten: Klanten
    ) -> None:
        async with _applicatiesessie(klanten.a) as sessie:
            meting = await meet_rol(await sessie.connection())

        assert beoordeel_rol(meting) == []

    async def test_postgres_wordt_afgekeurd(self, klanten: Klanten) -> None:
        engine = create_async_engine(_async_url(), poolclass=NullPool)
        try:
            async with engine.connect() as conn:
                meting = await meet_rol(conn)
        finally:
            await engine.dispose()

        assert any("superuser" in p for p in beoordeel_rol(meting))


@pytest.fixture
def lid_van_de_eigenaarrol(db: PgConnection) -> Iterator[str]:
    """Een wegwerprol in het TESTcluster die via lidmaatschap de rechten van de eigenaar erft."""
    naam = f"rls_lid_{uuid.uuid4().hex[:8]}"
    with db.cursor() as cur:
        cur.execute("SELECT tableowner FROM pg_tables WHERE tablename = 'receivables'")
        rij = cur.fetchone()
        assert rij is not None
        eigenaar = str(rij[0])
        cur.execute(f'CREATE ROLE "{naam}" NOLOGIN INHERIT')
        cur.execute(f'GRANT "{eigenaar}" TO "{naam}"')
    yield naam
    with db.cursor() as cur:
        cur.execute(f'DROP ROLE IF EXISTS "{naam}"')


class TestEenRolDieDeEigenaarErft:
    """Gate 2 ronde 1, F2: PostgreSQL past RLS ook niet toe op een lid van de eigenaarrol."""

    async def test_een_lid_van_de_eigenaarrol_wordt_afgekeurd(
        self, lid_van_de_eigenaarrol: str
    ) -> None:
        engine = create_async_engine(
            _async_url(),
            poolclass=NullPool,
            connect_args={"server_settings": {"role": lid_van_de_eigenaarrol}},
        )
        try:
            async with engine.connect() as conn:
                meting = await meet_rol(conn)
        finally:
            await engine.dispose()

        assert (meting.rol, any("eigenaar" in p for p in beoordeel_rol(meting))) == (
            lid_van_de_eigenaarrol,
            True,
        )


class TestKlantALeestNietsVanKlantB:
    @pytest.mark.parametrize("tabel", STEEKPROEF)
    async def test_klant_a_ziet_alleen_eigen_rijen(self, klanten: Klanten, tabel: str) -> None:
        async with _applicatiesessie(klanten.a) as sessie:
            gezien = await _klanten_in(sessie, tabel)

        assert (len(gezien) > 0, set(gezien)) == (True, {klanten.a})

    @pytest.mark.parametrize("tabel", STEEKPROEF)
    async def test_klant_b_ziet_alleen_eigen_rijen(self, klanten: Klanten, tabel: str) -> None:
        async with _applicatiesessie(klanten.b) as sessie:
            gezien = await _klanten_in(sessie, tabel)

        assert (len(gezien) > 0, set(gezien)) == (True, {klanten.b})

    @pytest.mark.parametrize("tabel", STEEKPROEF)
    async def test_zonder_klantcontext_ziet_de_applicatierol_niets(
        self, klanten: Klanten, tabel: str
    ) -> None:
        async with _applicatiesessie(None) as sessie:
            gezien = await _klanten_in(sessie, tabel)

        assert gezien == []

    async def test_een_rij_voor_een_andere_klant_schrijven_wordt_geweigerd(
        self, klanten: Klanten
    ) -> None:
        async with _applicatiesessie(klanten.a) as sessie:
            with pytest.raises(DBAPIError, match="row-level security"):
                await sessie.execute(
                    text(
                        "INSERT INTO agents (tenant_id, name, agent_type) "
                        "VALUES (:t, 'indringer', 'test')"
                    ),
                    {"t": klanten.b},
                )


class TestOokNaEenCommitMiddenInHetVerzoek:
    """OP-113: `SET LOCAL` verdween bij een commit; de hook zet de context per transactie opnieuw."""

    @pytest.mark.parametrize("tabel", STEEKPROEF)
    async def test_na_een_commit_ziet_klant_a_nog_steeds_alleen_eigen_rijen(
        self, klanten: Klanten, tabel: str
    ) -> None:
        async with _applicatiesessie(klanten.a) as sessie:
            voor = await _klanten_in(sessie, tabel)
            await sessie.commit()
            na = await _klanten_in(sessie, tabel)

        assert (set(voor), set(na), len(na) > 0) == ({klanten.a}, {klanten.a}, True)

    async def test_na_meerdere_commits_blijft_de_scheiding_staan(self, klanten: Klanten) -> None:
        async with _applicatiesessie(klanten.b) as sessie:
            for _ in range(3):
                await _klanten_in(sessie, "receivables")
                await sessie.commit()
            laatste = await _klanten_in(sessie, "receivables")

        assert set(laatste) == {klanten.b}
