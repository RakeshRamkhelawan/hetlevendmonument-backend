"""BE-MIG-015 -- de migratieketen draait vanaf een LEGE database naar head.

Gemeten defect (markt-review 2026-09-24, database.md): `alembic upgrade head` op
een verse PostgreSQL faalde met

    psycopg2.errors.DuplicateColumn: column "code_hash" of relation
    "educational_access" already exists
    [SQL: ALTER TABLE educational_access RENAME code TO code_hash]

Oorzaak: sinds de herkoppeling van 2026-09-18 draait `20260917_kolomdrift`
(ADR-036 OP-249) VOOR `20260909_adr029_edu_alignment`. Kolomdrift voegt
`educational_access.code_hash` en `study_collections.educational_access_id`
onvoorwaardelijk toe; edu_alignment deed daarna een onvoorwaardelijke
RENAME/ADD van diezelfde kolommen. In die ketenpositie kon edu_alignment
nooit slagen -- op geen enkele omgeving.

Deze test is het bewijs op een ECHTE lege database (patroon overgenomen van
tests/integration/database/test_the_chain_builds_the_whole_schema.py): een
wegwerp-database op de expliciet opgegeven testserver
(SANSKRITISETU_TEST_DATABASE_URL, ADR-036 OP-243), de volledige keten erop,
en de eindtoestand van educational_access / study_collections getoetst zoals
de MIGRATIES die bouwen -- niet zoals `Base.metadata.create_all` die bouwt
(dat dekken tests/integration/foundation/test_migrations.py al).

Daarnaast de roundtrip van precies de gerepareerde migratie: downgrade naar
`20260917_kolomdrift` moet de pre-alignment-toestand (beide kolommen)
terugzetten, en upgrade head daarna weer de aligned eindtoestand. Die
roundtrip faalde structureel zodra de upgrade defensief werd -- de downgrade
moet nu weten welke objecten van kolomdrift zijn en die met rust laten.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import psycopg2
import pytest
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

from tests.fixtures.testdatabase import testdatabase_poort

_REPO_ROOT = Path(__file__).resolve().parents[3]
# Per xdist-worker een eigen naam: de fixture dropt/creeert de database, dus
# met een vaste naam zouden workers elkaars verbinding afkappen midden in de
# keten (zelfde les als test_the_chain_builds_the_whole_schema.py, 2026-08-17).
_SCRATCH_DB = f"wk1_verse_keten_{os.environ.get('PYTEST_XDIST_WORKER', 'main')}"

_HEAD = "20260924_merge_adr029_tenant_llm_heads"
_VOOR_EDU_ALIGNMENT = "20260917_kolomdrift"


def _server_dsn(database: str) -> str:
    poort = str(testdatabase_poort())
    return f"host=127.0.0.1 port={poort} user=postgres password=postgres dbname={database}"


def _verse_database() -> None:
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


def _alembic(*args: str) -> subprocess.CompletedProcess[str]:
    poort = str(testdatabase_poort())
    omgeving = dict(os.environ)
    omgeving["DATABASE_URL"] = (
        f"postgresql+asyncpg://postgres:postgres@127.0.0.1:{poort}/{_SCRATCH_DB}"
    )
    return subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "src/alembic.ini", *args],
        cwd=_REPO_ROOT,
        env=omgeving,
        capture_output=True,
        text=True,
        timeout=900,
    )


def _upgrade_head() -> None:
    resultaat = _alembic("upgrade", "head")
    assert resultaat.returncode == 0, (
        f"`alembic upgrade head` op een VERSE database faalde met returncode "
        f"{resultaat.returncode}. Dat is het defect uit BE-MIG-015: een nieuwe "
        "omgeving (klant, regio, calamiteitherstel) kan niet worden opgebouwd.\n"
        f"--- stderr (laatste 4000 tekens) ---\n{resultaat.stderr[-4000:]}"
    )


def _kolommen(tabel: str) -> dict[str, tuple[str, int | None, str]]:
    conn = psycopg2.connect(_server_dsn(_SCRATCH_DB))
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT column_name, data_type, character_maximum_length, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = %s",
                (tabel,),
            )
            return {r[0]: (r[1], r[2], r[3]) for r in cur.fetchall()}
    finally:
        conn.close()


def _indexdef(tabel: str, index: str) -> str | None:
    conn = psycopg2.connect(_server_dsn(_SCRATCH_DB))
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT indexdef FROM pg_indexes "
                "WHERE schemaname = 'public' AND tablename = %s AND indexname = %s",
                (tabel, index),
            )
            rij = cur.fetchone()
            return rij[0] if rij else None
    finally:
        conn.close()


def _fk_doel(tabel: str, kolom: str) -> str | None:
    conn = psycopg2.connect(_server_dsn(_SCRATCH_DB))
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT ccu.table_name FROM information_schema.table_constraints tc "
                "JOIN information_schema.key_column_usage kcu "
                "ON tc.constraint_name = kcu.constraint_name "
                "JOIN information_schema.constraint_column_usage ccu "
                "ON tc.constraint_name = ccu.constraint_name "
                "WHERE tc.constraint_type = 'FOREIGN KEY' "
                "AND tc.table_name = %s AND kcu.column_name = %s",
                (tabel, kolom),
            )
            rij = cur.fetchone()
            return rij[0] if rij else None
    finally:
        conn.close()


def _alembic_versie() -> str:
    conn = psycopg2.connect(_server_dsn(_SCRATCH_DB))
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT version_num FROM alembic_version")
            rij = cur.fetchone()
            assert rij is not None, "alembic_version is leeg -- de keten heeft niet gedraaid"
            return rij[0]
    finally:
        conn.close()


@pytest.fixture(scope="module")
def verse_keten() -> None:
    """Bouw een verse database met ALLEEN de migraties (duurt ongeveer een minuut)."""
    _verse_database()
    _upgrade_head()


@pytest.mark.integration
class TestVerseDatabaseNaarHead:
    """De kern van BE-MIG-015: van leeg naar head, met de edu-eindtoestand erin."""

    def test_keten_staat_op_de_verwachte_head(self, verse_keten: None) -> None:
        assert _alembic_versie() == _HEAD

    def test_educational_access_heeft_alleen_code_hash(self, verse_keten: None) -> None:
        kolommen = _kolommen("educational_access")
        assert "code" not in kolommen, (
            "het plaintext-restant `code` uit 20260824_adr029_portal_v1 hoort na "
            "edu_alignment weg te zijn"
        )
        assert "code_hash" in kolommen
        _, lengte, nullable = kolommen["code_hash"]
        assert lengte == 64
        assert nullable == "NO"

    def test_educational_access_index_en_unieke_sleutel(self, verse_keten: None) -> None:
        indexdef = _indexdef("educational_access", "idx_ea_tenant_code")
        assert indexdef is not None
        assert "UNIQUE" in indexdef
        assert "(tenant_id, code_hash)" in indexdef
        # Precies EEN unieke beperking op code_hash: ofwel die van kolomdrift
        # (uq_educational_access_code_hash) ofwel die van edu_alignment
        # (educational_access_code_hash_key), maar nooit allebei.
        conn = psycopg2.connect(_server_dsn(_SCRATCH_DB))
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT conname FROM pg_constraint c "
                    "JOIN pg_class t ON t.oid = c.conrelid "
                    "WHERE t.relname = 'educational_access' AND c.contype = 'u' "
                    "AND (SELECT attname FROM pg_attribute "
                    "     WHERE attrelid = c.conrelid AND attnum = c.conkey[1]) = 'code_hash'"
                )
                namen = [r[0] for r in cur.fetchall()]
        finally:
            conn.close()
        assert len(namen) == 1, f"verwacht 1 unieke sleutel op code_hash, vond {namen}"

    def test_study_collections_heeft_alleen_de_fk_kolom(self, verse_keten: None) -> None:
        kolommen = _kolommen("study_collections")
        assert "access_code" not in kolommen
        assert "educational_access_id" in kolommen
        _, _, nullable = kolommen["educational_access_id"]
        assert nullable == "NO"
        assert _fk_doel("study_collections", "educational_access_id") == "educational_access"

    def test_study_collections_indexen(self, verse_keten: None) -> None:
        samengesteld = _indexdef("study_collections", "idx_sc_tenant_code")
        assert samengesteld is not None
        assert "(tenant_id, educational_access_id)" in samengesteld
        assert _indexdef("study_collections", "ix_study_collections_educational_access_id") is not None

    def test_roundtrip_edu_alignment(self, verse_keten: None) -> None:
        """Downgrade naar kolomdrift zet de pre-alignment-toestand terug; upgrade
        head herstelt de eindtoestand. Dit faalt als de downgrade objecten
        aanraakt die kolomdrift bezit (diens downgrade verwacht ze onder diens
        namen aan te treffen)."""
        omlaag = _alembic("downgrade", _VOOR_EDU_ALIGNMENT)
        assert omlaag.returncode == 0, (
            f"downgrade naar {_VOOR_EDU_ALIGNMENT} faalde:\n{omlaag.stderr[-3000:]}"
        )
        assert _alembic_versie() == _VOOR_EDU_ALIGNMENT
        # Pre-alignment-toestand: beide kolommen bestaan (kolomdrift voegde
        # code_hash toe; edu_alignment's downgrade zet code terug).
        ea = _kolommen("educational_access")
        assert "code" in ea and "code_hash" in ea
        sc = _kolommen("study_collections")
        assert "access_code" in sc and "educational_access_id" in sc

        omhoog = _alembic("upgrade", "head")
        assert omhoog.returncode == 0, (
            f"upgrade head na de downgrade faalde:\n{omhoog.stderr[-3000:]}"
        )
        assert _alembic_versie() == _HEAD
        ea = _kolommen("educational_access")
        assert "code" not in ea and "code_hash" in ea
        sc = _kolommen("study_collections")
        assert "access_code" not in sc and "educational_access_id" in sc
