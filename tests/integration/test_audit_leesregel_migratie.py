"""De migratie 20261024_audit_leesregel is omkeerbaar en zet de begintoestand exact terug (ADR-036 OP-246 en OP-248).

**OP-248.** De downgrade van `20260915_rls_resterende_tabellen.py` zet RLS uit op elke tabel, ook op een die RLS al aan had.
Deze migratie legt de begintoestand van `audit_logs` vast in een commentaar op de policy die hij zelf maakt en zet precies
die terug. De test draait de echte keten (`alembic upgrade/downgrade`) op een eigen wegwerpdatabase en meet in de catalogus:

- begintoestand RLS uit  -> na upgrade aan met twee policies -> na downgrade weer uit en zonder policies -> na tweede upgrade
  weer hetzelfde (upgrade, downgrade, upgrade);
- begintoestand RLS AAN (zonder policy) -> na downgrade blijft RLS aan en zijn de policies weg;
- de policies zijn met de hand weggehaald of hernoemd (begintoestand onbekend) -> de downgrade zet RLS NIET uit.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import psycopg2
import pytest
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT, connection as PgConnection
from tests.integration.security.test_the_application_role_is_confined_to_its_tenant import (
    _SCRATCH_DB,
    _bouw_verse_database,
    _dsn,
    _postgres_bereikbaar,
)
from tests.fixtures.testdatabase import testdatabase_poort

pytestmark = [
    pytest.mark.integration,
    pytest.mark.security,
    # De verse database uit de hele migratieketen kost minuten; de standaardgrens is daar te krap voor.
    pytest.mark.timeout(900),
    pytest.mark.skipif(
        not _postgres_bereikbaar(),
        reason="vereist PostgreSQL op de netwerkpoort uit SANSKRITISETU_TEST_DATABASE_URL",
    ),
]

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _kop_van_de_keten() -> str:
    """De enige head van de alembic-keten, uit de scripts zelf.

    Hier stond de vaste tekst `20261025_audit_anonimiseer_functie`. Zodra `20261026_user_roles_tenant_index` erop kwam
    (src/alembic/versions/20261026_user_roles_tenant_index.py) gaven drie tests een andere revisie terug dan de
    vaste tekst (CI-run 40674951559). Dat de keten precies een head heeft, bewaakt
    tests/unit/database/test_agentic_alembic_chain_complete.py, die de naam bewust vastpint.
    """
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    config = Config(str(_REPO_ROOT / "src" / "alembic.ini"))
    config.set_main_option("script_location", str(_REPO_ROOT / "src" / "alembic"))
    kop = ScriptDirectory.from_config(config).get_current_head()
    assert kop is not None
    return kop


_KOP = _kop_van_de_keten()
_VORIGE = "20261020_tenant_ap_verbindingen"
_BEIDE_POLICIES = ["rls_audit_logs_schrijven", "rls_audit_logs_tenant_isolation"]


def _alembic(*args: str) -> None:
    poort = str(testdatabase_poort())
    omgeving = dict(os.environ)
    omgeving["DATABASE_URL"] = (
        f"postgresql+asyncpg://postgres:postgres@127.0.0.1:{poort}/{_SCRATCH_DB}"
    )
    resultaat = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "src/alembic.ini", *args],
        cwd=_REPO_ROOT,
        env=omgeving,
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
    )
    assert resultaat.returncode == 0, f"alembic {' '.join(args)} faalde: {resultaat.stderr[-1500:]}"


def _toestand(conn: PgConnection) -> tuple[str, bool, bool, list[str]]:
    """(revisie, RLS aan, FORCE aan, policynamen) van `audit_logs`, uit de catalogus."""
    with conn.cursor() as cur:
        cur.execute("SELECT version_num FROM alembic_version")
        revisie = cur.fetchone()
        cur.execute(
            "SELECT relrowsecurity, relforcerowsecurity FROM pg_class WHERE oid = to_regclass('public.audit_logs')"
        )
        vlaggen = cur.fetchone()
        cur.execute("SELECT policyname FROM pg_policies WHERE tablename = 'audit_logs' ORDER BY 1")
        policies = [str(r[0]) for r in cur.fetchall()]
    assert revisie is not None and vlaggen is not None
    return str(revisie[0]), bool(vlaggen[0]), bool(vlaggen[1]), policies


@pytest.fixture
def db() -> Iterator[PgConnection]:
    """Per test een verse database op de kop van de keten, met een eigenaarsverbinding voor de catalogus."""
    _bouw_verse_database()
    conn = psycopg2.connect(_dsn(_SCRATCH_DB))
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    yield conn
    conn.close()


def _zet_rls(conn: PgConnection, aan: bool) -> None:
    with conn.cursor() as cur:
        cur.execute(f"ALTER TABLE audit_logs {'ENABLE' if aan else 'DISABLE'} ROW LEVEL SECURITY")


class TestUpgradeDowngradeUpgrade:
    def test_de_kop_van_de_keten_heeft_beide_policies_en_rls_aan(self, db: PgConnection) -> None:
        assert _toestand(db) == (_KOP, True, False, _BEIDE_POLICIES)

    def test_upgrade_downgrade_upgrade_geeft_telkens_de_verwachte_toestand(
        self, db: PgConnection
    ) -> None:
        kop = _toestand(db)
        _alembic("downgrade", _VORIGE)
        na_downgrade = _toestand(db)
        _alembic("upgrade", "head")
        na_tweede_upgrade = _toestand(db)

        assert (kop, na_downgrade, na_tweede_upgrade) == (
            (_KOP, True, False, _BEIDE_POLICIES),
            (_VORIGE, False, False, []),
            (_KOP, True, False, _BEIDE_POLICIES),
        )


class TestDeBegintoestandWordtExactTeruggezet:
    def test_rls_die_al_aanstond_blijft_aan_na_de_downgrade(self, db: PgConnection) -> None:
        _alembic("downgrade", _VORIGE)
        _zet_rls(db, True)
        _alembic("upgrade", "head")
        na_upgrade = _toestand(db)
        _alembic("downgrade", _VORIGE)
        na_downgrade = _toestand(db)

        assert (na_upgrade, na_downgrade) == (
            (_KOP, True, False, _BEIDE_POLICIES),
            (_VORIGE, True, False, []),
        )

    def test_een_onbekende_begintoestand_zet_rls_niet_uit(self, db: PgConnection) -> None:
        """De leesregel is met de hand hernoemd: wij weten niet hoe de tabel was, dus gaat RLS niet uit."""
        with db.cursor() as cur:
            cur.execute(
                "ALTER POLICY rls_audit_logs_tenant_isolation ON audit_logs RENAME TO handmatig_hernoemd"
            )
        _alembic("downgrade", _VORIGE)
        toestand = _toestand(db)

        assert toestand == (_VORIGE, True, False, ["handmatig_hernoemd"])

    def test_een_onbekende_begintoestand_haalt_beide_policies_weg_en_laat_rls_staan(
        self, db: PgConnection
    ) -> None:
        """Gate 2 F4: het commentaar met de begintoestand ontbreekt; dan gaan de policies weg en blijft RLS zoals het was."""
        with db.cursor() as cur:
            cur.execute("COMMENT ON POLICY rls_audit_logs_tenant_isolation ON audit_logs IS NULL")
        _alembic("downgrade", _VORIGE)
        toestand = _toestand(db)

        assert toestand == (_VORIGE, True, False, [])
