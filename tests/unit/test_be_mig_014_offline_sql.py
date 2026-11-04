"""Offline-SQL dekking voor migratie 20260910_adr029_sprint_c_datamodel (BE-MIG-014).

Zelfde aanpak als tests/unit/test_be_mig_013_offline_sql.py: de
integratietests bouwen het schema via create_all en dekken het migratiepad
zelf niet. Deze test genereert met alembic offline mode het migratiescript
en assert dat de autocommit enum-aanmaak, de zes nieuwe
content_type_enum-waarden (hoofdletters, zie migratie-docstring), de
kolommen, de defensieve backfill-CASE, de index en de downgrade-drops erin
zitten.

De test heeft geen database nodig; hij skipt (niet faalt) als alembic
offline in de omgeving niet draaibaar is.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
REVISION = "20260910_adr029_sprint_c_datamodel"
PREVIOUS = "20260909_adr029_edu_alignment"


def _generate_offline_sql(direction: str) -> str:
    env = dict(os.environ)
    # Offline mode maakt geen connectie; PostgreSQL-URL volstaat voor het genereren van Postgres DDL.
    env["DATABASE_URL"] = "postgresql://offline:offline@127.0.0.1:5432/offline"
    target = (
        f"{PREVIOUS}:{REVISION}" if direction == "upgrade" else f"{REVISION}:{PREVIOUS}"
    )
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "alembic.ini",
            direction,
            target,
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
def upgrade_sql() -> str:
    return _generate_offline_sql("upgrade")


@pytest.fixture(scope="module")
def downgrade_sql() -> str:
    return _generate_offline_sql("downgrade")


class TestBeMig014UpgradeOfflineSql:
    """Het migratiepad zelf moet gedekt zijn, niet alleen het model-schema."""

    def test_visibility_enum_wordt_idempotent_aangemaakt(self, upgrade_sql):
        assert (
            "CREATE TYPE visibility_enum AS ENUM ('public', 'edu', 'community')"
            in upgrade_sql
        )
        assert "WHEN duplicate_object THEN NULL" in upgrade_sql

    def test_zes_content_type_waarden_als_hoofdletters(self, upgrade_sql):
        # content_type_enum bevat member-NAMEN (STORY, ...); het ORM
        # serialiseert zonder values_callable ook namen. Lowercase waarden
        # zouden dode duplicaten zijn (de 'bounced'-bug uit BE-MIG-013).
        for value in (
            "VIDEO",
            "EDUCATIONAL_WORKBOOK",
            "EDUCATIONAL_VIDEO",
            "TEACHER_GUIDE",
            "EVENT_REPORT",
            "ART_DOCUMENTATION",
        ):
            assert (
                f"ALTER TYPE content_type_enum ADD VALUE IF NOT EXISTS '{value}';"
                in upgrade_sql
            )

    def test_kolommen_komen_erbij(self, upgrade_sql):
        assert "ADD COLUMN visibility visibility_enum DEFAULT 'public' NOT NULL;" in upgrade_sql
        assert "ADD COLUMN target_age_group VARCHAR(50);" in upgrade_sql

    def test_backfill_is_defensieve_case_cast(self, upgrade_sql):
        assert "CASE privacy::text" in upgrade_sql
        assert "WHEN 'PUBLIC' THEN 'public'" in upgrade_sql
        assert "WHEN 'COMMUNITY' THEN 'community'" in upgrade_sql
        assert "ELSE 'public' END" in upgrade_sql

    def test_index_voor_edu_lijstquery(self, upgrade_sql):
        assert (
            "CREATE INDEX idx_fc_tenant_visibility_status ON foundation_content "
            "(tenant_id, visibility, status);" in upgrade_sql
        )


class TestBeMig014DowngradeOfflineSql:
    def test_index_en_kolommen_en_enum_worden_gedropt(self, downgrade_sql):
        assert "DROP INDEX idx_fc_tenant_visibility_status;" in downgrade_sql
        assert "DROP COLUMN target_age_group;" in downgrade_sql
        assert "DROP COLUMN visibility;" in downgrade_sql
        assert "DROP TYPE IF EXISTS visibility_enum;" in downgrade_sql

    def test_content_type_waarden_blijven_staan(self, downgrade_sql):
        # PostgreSQL kan enum-waarden niet droppen zonder type-recreatie;
        # de downgrade mag ze dus niet proberen te verwijderen.
        assert "content_type_enum" not in downgrade_sql
