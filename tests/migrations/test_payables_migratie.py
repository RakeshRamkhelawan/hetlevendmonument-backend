"""Migratie `20261024_payables_rls`: upgrade, RLS, downgrade en upgrade op ECHTE PostgreSQL (crediteuren dag 1).

Draait in een eigen wegwerpdatabase die deze module aanmaakt en weer weggooit; de server komt uit
`SANSKRITISETU_TEST_DATABASE_URL` (nooit geraden, zie `tests/fixtures/testdatabase.py`). Een offline `--sql`-run toont een
onvolledig schema, dus de DO-blok-tak voor RLS is alleen tegen een echte server te toetsen. Er staan alleen minimale `tenants`- en
`users`-tabellen in, voor de vreemde sleutels. De hele keten (verse database, alle migraties) loopt in
`tests/integration/security/test_payables_is_confined_to_its_tenant.py`.
"""

from __future__ import annotations

import importlib.util
import uuid
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations

from tests.fixtures.testdatabase import testdatabase_url

MIGRATIE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "alembic"
    / "versions"
    / "20261024_payables_rls.py"
)
TABELLEN = ("suppliers", "payables")

pytestmark = [pytest.mark.integration]


def _laad_migratie() -> ModuleType:
    spec = importlib.util.spec_from_file_location("payables_migratie", MIGRATIE)
    assert spec is not None and spec.loader is not None, f"migratie ontbreekt: {MIGRATIE}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def engine() -> Iterator[sa.Engine]:
    naam = f"payables_wegwerp_{uuid.uuid4().hex[:8]}"
    beheer = sa.create_engine(
        testdatabase_url(database="postgres", sync=True), isolation_level="AUTOCOMMIT"
    )
    with beheer.connect() as c:
        c.execute(sa.text(f'CREATE DATABASE "{naam}"'))
    eng = sa.create_engine(testdatabase_url(database=naam, sync=True))
    with eng.begin() as c:
        c.execute(sa.text("CREATE TABLE tenants (id integer PRIMARY KEY)"))
        c.execute(sa.text("INSERT INTO tenants (id) VALUES (1), (2)"))
        c.execute(sa.text("CREATE TABLE users (id integer PRIMARY KEY)"))
    try:
        yield eng
    finally:
        eng.dispose()
        with beheer.connect() as c:
            c.execute(sa.text(f'DROP DATABASE IF EXISTS "{naam}" WITH (FORCE)'))
        beheer.dispose()


def _draai(eng: sa.Engine, richting: str) -> None:
    module = _laad_migratie()
    with eng.begin() as c:
        ctx = MigrationContext.configure(c)
        with Operations.context(ctx):
            getattr(module, richting)()


def _bestaat(eng: sa.Engine, tabel: str) -> bool:
    with eng.connect() as c:
        return c.execute(sa.text(f"SELECT to_regclass('public.{tabel}')")).scalar() is not None


def _scalar(eng: sa.Engine, sql: str) -> object:
    with eng.connect() as c:
        return c.execute(sa.text(sql)).scalar()


def test_het_revisiebestand_hangt_aan_de_vorige_kop() -> None:
    module = _laad_migratie()

    assert (module.revision, module.down_revision) == (
        "20261024_payables_rls",
        "20261023_schemadrift_schadelijk",
    )


def test_upgrade_maakt_beide_tabellen(engine: sa.Engine) -> None:
    _draai(engine, "upgrade")

    assert [_bestaat(engine, t) for t in TABELLEN] == [True, True]


@pytest.mark.parametrize("tabel", TABELLEN)
def test_upgrade_zet_rls_aan_zonder_force(engine: sa.Engine, tabel: str) -> None:
    _draai(engine, "upgrade")

    rij = _scalar(
        engine,
        f"SELECT relrowsecurity::text || ',' || relforcerowsecurity::text FROM pg_class WHERE relname = '{tabel}'",
    )

    assert rij == "true,false"


@pytest.mark.parametrize("tabel", TABELLEN)
def test_de_policy_heeft_de_tenantexpressie_en_geldt_voor_alle_commandos(
    engine: sa.Engine, tabel: str
) -> None:
    _draai(engine, "upgrade")

    rij = _scalar(
        engine,
        "SELECT cmd || '|' || qual FROM pg_policies "
        f"WHERE tablename = '{tabel}' AND policyname = 'rls_{tabel}_tenant_isolation'",
    )

    assert isinstance(rij, str) and rij.startswith("ALL|") and "app.current_tenant" in rij


def test_een_factuur_met_een_leverancier_van_een_andere_tenant_wordt_geweigerd(
    engine: sa.Engine,
) -> None:
    _draai(engine, "upgrade")
    with engine.begin() as c:
        c.execute(sa.text("INSERT INTO suppliers (tenant_id, name) VALUES (2, 'Van tenant twee')"))
        leverancier = c.execute(sa.text("SELECT id FROM suppliers")).scalar()

    with pytest.raises(sa.exc.IntegrityError):
        with engine.begin() as c:
            c.execute(
                sa.text(
                    "INSERT INTO payables (tenant_id, supplier_id, invoice_number, amount_cents, currency, "
                    "invoice_date, due_date, status) VALUES (1, :l, 'X-1', 100, 'EUR', '2026-10-01', '2026-10-31', 'ontvangen')"
                ),
                {"l": leverancier},
            )


def test_downgrade_laat_precies_de_twee_tabellen_vallen(engine: sa.Engine) -> None:
    _draai(engine, "upgrade")

    _draai(engine, "downgrade")

    assert [_bestaat(engine, t) for t in (*TABELLEN, "tenants", "users")] == [
        False,
        False,
        True,
        True,
    ]


def test_downgrade_met_gegevens_erin_werkt(engine: sa.Engine) -> None:
    """Een downgrade mag niet stuklopen op de verwijzing van de ene tabel naar de andere."""
    _draai(engine, "upgrade")
    with engine.begin() as c:
        c.execute(sa.text("INSERT INTO suppliers (tenant_id, name) VALUES (1, 'Leverancier')"))
        c.execute(
            sa.text(
                "INSERT INTO payables (tenant_id, supplier_id, invoice_number, amount_cents, currency, "
                "invoice_date, due_date, status) SELECT 1, id, 'X-1', 100, 'EUR', '2026-10-01', '2026-10-31', 'ontvangen' "
                "FROM suppliers"
            )
        )

    _draai(engine, "downgrade")

    assert not _bestaat(engine, "payables") and not _bestaat(engine, "suppliers")


def test_upgrade_downgrade_upgrade_geeft_weer_beide_tabellen_met_rls(engine: sa.Engine) -> None:
    _draai(engine, "upgrade")
    _draai(engine, "downgrade")

    _draai(engine, "upgrade")

    aan = [
        _scalar(engine, f"SELECT relrowsecurity FROM pg_class WHERE relname = '{t}'")
        for t in TABELLEN
    ]
    assert aan == [True, True]
