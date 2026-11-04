"""Migratie `20261020_tenant_ap_verbindingen`: upgrade, RLS en downgrade op ECHTE PostgreSQL.

Draait in een eigen wegwerpdatabase die deze module aanmaakt en weer weggooit; de server komt uit
`SANSKRITISETU_TEST_DATABASE_URL` (nooit geraden, zie `tests/fixtures/testdatabase.py`). Een
offline `--sql`-run toont een onvolledig schema, dus de DO-blok-tak voor RLS is alleen tegen een
echte server te toetsen. Er staat alleen een minimale `tenants`-tabel in, voor de vreemde sleutel.
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
    / "20261020_tenant_ap_verbindingen.py"
)
TABEL = "tenant_ap_verbindingen"
POLICY = "rls_tenant_ap_verbindingen_tenant_isolation"

pytestmark = [pytest.mark.integration]


def _laad_migratie() -> ModuleType:
    spec = importlib.util.spec_from_file_location("ap_verbindingen_migratie", MIGRATIE)
    assert spec is not None and spec.loader is not None, f"migratie ontbreekt: {MIGRATIE}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def engine() -> Iterator[sa.Engine]:
    naam = f"ap_verbindingen_wegwerp_{uuid.uuid4().hex[:8]}"
    beheer = sa.create_engine(
        testdatabase_url(database="postgres", sync=True), isolation_level="AUTOCOMMIT"
    )
    with beheer.connect() as c:
        c.execute(sa.text(f'CREATE DATABASE "{naam}"'))
    eng = sa.create_engine(testdatabase_url(database=naam, sync=True))
    with eng.begin() as c:
        c.execute(sa.text("CREATE TABLE tenants (id integer PRIMARY KEY)"))
        c.execute(sa.text("INSERT INTO tenants (id) VALUES (1), (2)"))
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


def _bestaat(eng: sa.Engine) -> bool:
    with eng.connect() as c:
        return c.execute(sa.text(f"SELECT to_regclass('public.{TABEL}')")).scalar() is not None


def _scalar(eng: sa.Engine, sql: str) -> object:
    with eng.connect() as c:
        return c.execute(sa.text(sql)).scalar()


def _voeg_rij_in(eng: sa.Engine, tenant_id: int) -> None:
    with eng.begin() as c:
        c.execute(
            sa.text(
                f"INSERT INTO {TABEL} (tenant_id, base_url, email, wachtwoord_encrypted, project_id) "
                "VALUES (:t, 'https://ap.example.com', 'a@example.com', 'versleuteld', 'p1')"
            ),
            {"t": tenant_id},
        )


def test_upgrade_maakt_de_tabel(engine: sa.Engine) -> None:
    _draai(engine, "upgrade")

    assert _bestaat(engine)


def test_upgrade_zet_rls_aan(engine: sa.Engine) -> None:
    _draai(engine, "upgrade")

    aan = _scalar(engine, f"SELECT relrowsecurity FROM pg_class WHERE relname = '{TABEL}'")

    assert aan is True


def test_upgrade_maakt_de_policy_met_de_tenantexpressie(engine: sa.Engine) -> None:
    _draai(engine, "upgrade")

    expressie = _scalar(
        engine,
        f"SELECT qual FROM pg_policies WHERE tablename = '{TABEL}' AND policyname = '{POLICY}'",
    )

    assert isinstance(expressie, str) and "app.current_tenant" in expressie


def test_de_policy_geldt_voor_alle_commando_s(engine: sa.Engine) -> None:
    _draai(engine, "upgrade")

    commando = _scalar(
        engine,
        f"SELECT cmd FROM pg_policies WHERE tablename = '{TABEL}' AND policyname = '{POLICY}'",
    )

    assert commando == "ALL"


def test_een_tweede_rij_voor_dezelfde_tenant_wordt_geweigerd(engine: sa.Engine) -> None:
    _draai(engine, "upgrade")
    _voeg_rij_in(engine, 1)

    with pytest.raises(sa.exc.IntegrityError):
        _voeg_rij_in(engine, 1)


def test_twee_tenants_met_hetzelfde_adres_en_project_worden_geweigerd(engine: sa.Engine) -> None:
    _draai(engine, "upgrade")
    _voeg_rij_in(engine, 1)

    with pytest.raises(sa.exc.IntegrityError):
        _voeg_rij_in(engine, 2)


def test_twee_tenants_met_hetzelfde_adres_maar_een_ander_project_mogen_wel(
    engine: sa.Engine,
) -> None:
    _draai(engine, "upgrade")
    _voeg_rij_in(engine, 1)
    with engine.begin() as c:
        c.execute(
            sa.text(
                f"INSERT INTO {TABEL} (tenant_id, base_url, email, wachtwoord_encrypted, project_id) "
                "VALUES (2, 'https://ap.example.com', 'b@example.com', 'versleuteld', 'p2')"
            )
        )

    assert _scalar(engine, f"SELECT count(*) FROM {TABEL}") == 2


def test_een_onbekende_tenant_wordt_geweigerd_door_de_vreemde_sleutel(engine: sa.Engine) -> None:
    _draai(engine, "upgrade")

    with pytest.raises(sa.exc.IntegrityError):
        _voeg_rij_in(engine, 999)


def test_het_verwijderen_van_een_tenant_neemt_zijn_rij_mee(engine: sa.Engine) -> None:
    _draai(engine, "upgrade")
    _voeg_rij_in(engine, 2)

    with engine.begin() as c:
        c.execute(sa.text("DELETE FROM tenants WHERE id = 2"))

    assert _scalar(engine, f"SELECT count(*) FROM {TABEL}") == 0


def test_downgrade_haalt_de_tabel_weg(engine: sa.Engine) -> None:
    _draai(engine, "upgrade")

    _draai(engine, "downgrade")

    assert not _bestaat(engine)


def test_downgrade_laat_de_tenants_tabel_ongemoeid(engine: sa.Engine) -> None:
    _draai(engine, "upgrade")

    _draai(engine, "downgrade")

    assert _scalar(engine, "SELECT count(*) FROM tenants") == 2


def test_upgrade_na_downgrade_werkt_opnieuw(engine: sa.Engine) -> None:
    _draai(engine, "upgrade")
    _draai(engine, "downgrade")

    _draai(engine, "upgrade")

    assert _bestaat(engine)
