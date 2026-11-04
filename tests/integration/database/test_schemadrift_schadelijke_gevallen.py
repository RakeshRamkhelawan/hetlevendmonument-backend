"""De schadelijke schemadrift-gevallen van 2026-10-23: schrijven moet weer slagen.

Bron: `docs/backend/schemadrift-indeling-2026-10-23.md`. Alle tests draaien tegen een verse
database die ALLEEN uit de migratieketen is opgebouwd (de unittests bouwen met `create_all`
en zien zulke gaten per definitie niet).

Gedekt:
1. een risico-regel (`governance_risk_entries`) kan geschreven en teruggelezen worden;
2. een tenant met een slug van 60 tekens wordt opgeslagen (database was 50, model 100);
3. de drie NOT NULL-kolommen die het model niet kent blokkeren geen insert meer
   (`educational_access.code`, `study_collections.access_code`,
   `pack_usage_aggregates.company_size`);
4. de migratie is omkeerbaar, en een downgrade die gegevens zou afkappen weigert in plaats
   van data te verliezen.

Niet gedekt (bewust, zie het rapport): `pack_usage_aggregates.pack_id` (UUID tegen tekst).
Dat vraagt het laten vallen van een verwijzing en een type-omzetting waarvan de downgrade met
data niet kan; dat is interlock 1 en wacht op Rakesh.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import psycopg2
import pytest
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from sqlalchemy import create_engine, select, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import Session
from tests.fixtures.testdatabase import testdatabase_poort

_REPO_ROOT = Path(__file__).resolve().parents[3]
# Vast, niet `-1`: een latere migratie op develop mag deze tests niet stilletjes iets anders laten toetsen.
_VORIGE_REVISIE = "20261020_tenant_ap_verbindingen"
_SCRATCH_DB = f"schemadrift_schadelijk_{os.environ.get('PYTEST_XDIST_WORKER', 'main')}"


def _poort() -> str:
    return str(testdatabase_poort())


def _server_dsn(database: str) -> str:
    return f"host=127.0.0.1 port={_poort()} user=postgres password=postgres dbname={database}"


def _alembic(*argumenten: str) -> subprocess.CompletedProcess[str]:
    omgeving = dict(os.environ)
    omgeving["DATABASE_URL"] = (
        f"postgresql+asyncpg://postgres:postgres@127.0.0.1:{_poort()}/{_SCRATCH_DB}"
    )
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "src/alembic.ini", *argumenten],
        cwd=_REPO_ROOT,
        env=omgeving,
        capture_output=True,
        text=True,
        timeout=900,
    )


@pytest.fixture(scope="module")
def keten_database() -> Iterator[str]:
    conn = psycopg2.connect(_server_dsn("postgres"))
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (_SCRATCH_DB,),
            )
            cur.execute(f'DROP DATABASE IF EXISTS "{_SCRATCH_DB}"')
            cur.execute(f'CREATE DATABASE "{_SCRATCH_DB}"')
    finally:
        conn.close()
    gedraaid = _alembic("upgrade", "head")
    assert gedraaid.returncode == 0, f"upgrade head faalde:\n{gedraaid.stderr[-3000:]}"
    yield _SCRATCH_DB


@pytest.fixture
def sessie(keten_database: str) -> Iterator[Session]:
    """Een sessie in een transactie die altijd wordt teruggedraaid."""
    from src.core.database import import_all_models  # noqa: F401

    motor = create_engine(
        f"postgresql+psycopg2://postgres:postgres@127.0.0.1:{_poort()}/{keten_database}"
    )
    with Session(motor) as s:
        yield s
        s.rollback()
    motor.dispose()


_TOEGANG = text(
    "INSERT INTO educational_access (tenant_id, code_hash, email, role, is_active) "
    "VALUES (:t, :h, :e, 'student', true) RETURNING id"
)


def _tenant(s: Session, slug: str = "meting-tenant") -> int:
    waarde = s.execute(
        text(
            "INSERT INTO tenants (name, slug, is_active, max_users, max_agents, max_storage_gb) "
            "VALUES (:naam, :slug, true, 1, 1, 1) RETURNING id"
        ),
        {"naam": f"naam-{slug}", "slug": slug},
    ).scalar_one()
    return int(waarde)


@pytest.mark.integration
class TestSchrijvenSlaagtOpDeKeten:
    def test_een_risicoregel_wordt_geschreven_en_teruggelezen(self, keten_database: str) -> None:
        """Via asyncpg, zoals de applicatie: psycopg2 stuurt de enum als losse tekst en ziet
        het ontbrekende databasetype niet (gemeten bij het schrijven van deze test)."""
        from src.core.database import import_all_models  # noqa: F401
        from src.core.governance.risk_register import RiskEntry, RiskImpact, RiskLikelihood

        async def scenario() -> tuple[RiskLikelihood, RiskImpact]:
            motor = create_async_engine(
                f"postgresql+asyncpg://postgres:postgres@127.0.0.1:{_poort()}/{keten_database}"
            )
            try:
                async with AsyncSession(motor) as s:
                    tenant_id = (
                        await s.execute(
                            text(
                                "INSERT INTO tenants (name, slug, is_active, max_users, "
                                "max_agents, max_storage_gb) VALUES ('risico', 'risico', true, "
                                "1, 1, 1) RETURNING id"
                            )
                        )
                    ).scalar_one()
                    s.add(
                        RiskEntry(
                            tenant_id=tenant_id,
                            agent_name="agent",
                            risk_description="beschrijving",
                            likelihood=RiskLikelihood.POSSIBLE,
                            impact=RiskImpact.MAJOR,
                            mitigation="maatregel",
                            residual_risk="high",
                        )
                    )
                    await s.flush()
                    s.expire_all()
                    regel = (
                        await s.execute(select(RiskEntry).where(RiskEntry.tenant_id == tenant_id))
                    ).scalar_one()
                    gelezen = (regel.likelihood, regel.impact)
                    await s.rollback()
                    return gelezen
            finally:
                await motor.dispose()

        assert asyncio.run(scenario()) == (RiskLikelihood.POSSIBLE, RiskImpact.MAJOR)

    def test_een_tenant_met_een_slug_van_60_tekens_wordt_opgeslagen(self, sessie: Session) -> None:
        slug = "s" * 60
        tenant_id = _tenant(sessie, slug)
        opgeslagen = sessie.execute(
            text("SELECT slug FROM tenants WHERE id = :id"), {"id": tenant_id}
        ).scalar_one()
        assert opgeslagen == slug

    def test_toegang_zonder_oude_code_kolom_wordt_geschreven(self, sessie: Session) -> None:
        """Rauwe SQL, niet het model: het model schrijft enumNAMEN ('STUDENT') terwijl de
        database de waarden ('student') kent; dat is een eigen bevinding, zie het rapport."""
        tenant_id = _tenant(sessie)
        sessie.execute(_TOEGANG, {"t": tenant_id, "h": "h" * 64, "e": "a@example.com"})
        aantal = sessie.execute(text("SELECT count(*) FROM educational_access")).scalar_one()
        assert aantal == 1

    def test_een_studiecollectie_zonder_access_code_wordt_geschreven(self, sessie: Session) -> None:
        tenant_id = _tenant(sessie)
        toegang_id = sessie.execute(
            _TOEGANG, {"t": tenant_id, "h": "g" * 64, "e": "b@example.com"}
        ).scalar_one()
        sessie.execute(
            text(
                "INSERT INTO study_collections (tenant_id, name, educational_access_id) "
                "VALUES (:t, 'collectie', :a)"
            ),
            {"t": tenant_id, "a": toegang_id},
        )
        aantal = sessie.execute(text("SELECT count(*) FROM study_collections")).scalar_one()
        assert aantal == 1

    def test_company_size_blokkeert_een_insert_niet_meer(self, sessie: Session) -> None:
        nullable = sessie.execute(
            text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name = 'pack_usage_aggregates' AND column_name = 'company_size'"
            )
        ).scalar_one()
        assert nullable == "YES"


@pytest.mark.integration
class TestDeOpruimstapVanDeJobDraaitOpDeKeten:
    """Gate 2-opmerking: de opruimstap draait nu voor het eerst echt, dus meet hem."""

    def test_cleanup_old_aggregations_slaagt_op_het_ketenschema(self, keten_database: str) -> None:
        from src.core.database import import_all_models  # noqa: F401
        from src.core.jobs.analytics_aggregation import cleanup_old_aggregations

        async def scenario() -> int:
            motor = create_async_engine(
                f"postgresql+asyncpg://postgres:postgres@127.0.0.1:{_poort()}/{keten_database}"
            )
            try:
                async with AsyncSession(motor) as s:
                    return await cleanup_old_aggregations(s)
            finally:
                await motor.dispose()

        assert asyncio.run(scenario()) == 0


@pytest.mark.integration
class TestDeMigratieIsOmkeerbaarEnVerliestGeenData:
    """Volgorde telt: deze klasse verandert de versie van de database en zet hem terug."""

    def test_downgrade_weigert_als_een_slug_te_lang_is_voor_50_tekens(
        self, keten_database: str
    ) -> None:
        conn = psycopg2.connect(_server_dsn(keten_database))
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO tenants (name, slug, is_active, max_users, max_agents, "
                "max_storage_gb) VALUES ('lang', %s, true, 1, 1, 1)",
                ("x" * 60,),
            )
        gedraaid = _alembic("downgrade", _VORIGE_REVISIE)
        with conn.cursor() as cur:
            cur.execute("SELECT length(slug) FROM tenants WHERE name = 'lang'")
            lengte = cur.fetchone()
            cur.execute("DELETE FROM tenants WHERE name = 'lang'")
        conn.close()

        assert gedraaid.returncode != 0 and lengte == (60,), (
            "de downgrade hoort te weigeren en de slug ongemoeid te laten; "
            f"rc={gedraaid.returncode}, lengte={lengte}\n{gedraaid.stderr[-1500:]}"
        )

    def test_downgrade_en_weer_upgrade_slagen_zonder_data(self, keten_database: str) -> None:
        def slug_lengte() -> int:
            conn = psycopg2.connect(_server_dsn(keten_database))
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "SELECT character_maximum_length FROM information_schema.columns "
                        "WHERE table_name = 'tenants' AND column_name = 'slug'"
                    )
                    rij = cur.fetchone()
                    assert rij is not None
                    return int(rij[0])
            finally:
                conn.close()

        voor = slug_lengte()
        terug = _alembic("downgrade", _VORIGE_REVISIE)
        assert terug.returncode == 0, f"downgrade faalde:\n{terug.stderr[-2000:]}"
        na_downgrade = slug_lengte()
        weer = _alembic("upgrade", "head")
        assert weer.returncode == 0, f"upgrade na downgrade faalde:\n{weer.stderr[-2000:]}"
        assert (voor, na_downgrade, slug_lengte()) == (100, 50, 100)

    def test_er_is_precies_een_head(self, keten_database: str) -> None:
        gedraaid = _alembic("heads")
        koppen = [r for r in gedraaid.stdout.splitlines() if "(head)" in r]
        assert len(koppen) == 1, gedraaid.stdout
