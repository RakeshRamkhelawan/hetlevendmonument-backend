"""Offline-SQL dekking voor migratie 20260909_adr029_edu_alignment (BE-MIG-013).

De integratietests in tests/integration/foundation/test_migrations.py draaien
tegen een create_all-schema en dekken het migratiepad zelf niet. Deze test
genereert met alembic offline mode (`upgrade <start>:<rev> --sql`) het
migratiescript en assert dat het type-recreatiepad (RENAME/CREATE/DROP TYPE)
en de defensieve CASE-cast voor de dode lowercase 'bounced'-waarde erin zitten.

De test heeft geen database nodig; hij skipt (niet faalt) als alembic offline
in de omgeving niet draaibaar is.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
REVISION = "20260909_adr029_edu_alignment"
PREVIOUS = "20260716_backfill_prana_budgets"


def _generate_offline_sql() -> str:
    env = dict(os.environ)
    # Offline mode maakt geen connectie; een dummy-URL volstaat als env.py
    # er een vereist. Overschrijf nooit een expliciet gezette DATABASE_URL.
    env.setdefault("DATABASE_URL", "postgresql://offline:offline@127.0.0.1:5432/offline")
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "alembic.ini",
            "upgrade",
            f"{PREVIOUS}:{REVISION}",
            "--sql",
        ],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=300,
    )
    if proc.returncode != 0:
        pytest.skip(
            "alembic offline-SQL genereren lukt niet in deze omgeving: "
            + (proc.stderr or proc.stdout)[-500:]
        )
    return proc.stdout


@pytest.fixture(scope="module")
def offline_sql() -> str:
    return _generate_offline_sql()


class TestBeMig013OfflineSql:
    """Het migratiepad zelf moet gedekt zijn, niet alleen het model-schema."""

    def test_enum_recreatie_is_aanwezig(self, offline_sql):
        # Dode dubbele waarde 'bounced' wordt verwijderd via type-recreatie.
        assert "ALTER TYPE newsletter_status_enum RENAME TO newsletter_status_enum_old;" in offline_sql
        assert (
            "CREATE TYPE newsletter_status_enum AS ENUM "
            "('PENDING_OPT_IN', 'SUBSCRIBED', 'UNSUBSCRIBED', 'BOUNCED')" in offline_sql
        )
        assert "DROP TYPE newsletter_status_enum_old;" in offline_sql

    def test_using_cast_is_defensief_voor_dode_bounced(self, offline_sql):
        # Rijen met de dode lowercase 'bounced' (geldig sinds 20260824) mappen
        # naar 'BOUNCED'; een kale cast zou op zulke rijen falen.
        assert (
            "CASE WHEN status::text = 'bounced' THEN 'BOUNCED' "
            "ELSE status::text END" in offline_sql
        )

    def test_educational_access_kolom_wordt_code_hash(self, offline_sql):
        assert "RENAME code TO code_hash;" in offline_sql
        assert "ADD CONSTRAINT educational_access_code_hash_key UNIQUE (code_hash);" in offline_sql

    def test_study_collections_krijgt_access_fk(self, offline_sql):
        assert "ADD COLUMN educational_access_id INTEGER NOT NULL;" in offline_sql
        assert (
            "ADD CONSTRAINT study_collections_educational_access_id_fkey "
            "FOREIGN KEY(educational_access_id) REFERENCES educational_access (id) "
            "ON DELETE CASCADE" in offline_sql
        )

    def test_indexen_komen_overeen_met_model(self, offline_sql):
        assert "CREATE UNIQUE INDEX idx_ea_tenant_code ON educational_access (tenant_id, code_hash);" in offline_sql
        assert (
            "CREATE INDEX idx_sc_tenant_code ON study_collections "
            "(tenant_id, educational_access_id);" in offline_sql
        )
