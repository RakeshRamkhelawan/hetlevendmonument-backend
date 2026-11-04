"""Elke tabel met een RLS-policy heeft de tenantkolom VOORAAN in een index (OP-161).

Row Level Security voegt aan elke query een `tenant_id = ...`-voorwaarde toe. Staat die
kolom niet als LEIDENDE kolom in een index, dan kan de planner de voorwaarde niet in een
index-scan duwen en valt hij terug op een sequential scan -- op elke query, op die tabel.

De vakliteratuur noemt dit de belangrijkste prestatievalkuil bij RLS. Een gemeten
voorbeeld elders: 120 ms tegen 1,2 ms op een miljoen rijen. Dat cijfer is niet van ons en
wordt hier alleen als richting genoemd.

**Waarom dit vandaag onzichtbaar is.** De applicatie verbindt als tabeleigenaar, en
PostgreSQL slaat RLS voor de eigenaar over. De 138 policies doen dus niets, en dus kost
ook niets iets. Op de dag dat de applicatie een eigen rol krijgt (OP-151) worden ze
allemaal tegelijk actief. Een tekort dat zich dan aandient als "de applicatie is ineens
traag" is een van de moeilijkst toe te wijzen storingen die er zijn.

Gemeten 2026-08-17 op een database uit `alembic upgrade head`: 137 tabellen met een policy
en een tenantkolom, waarvan **131 met** en **6 zonder** leidende index.

Deze guard toetst de STRUCTUUR -- welke index er ligt -- en niet de snelheid. Een
snelheidsmeting vraagt representatieve datavolumes en die zijn er in een testdatabase
niet; een `EXPLAIN ANALYZE` op lege tabellen levert een getal op dat niets zegt.

**Mutatiebewijs (2026-08-17), beide richtingen:**
- De indexmigratie uit de keten gehaald -> ROOD met exact die zes tabelnamen.
- Een index toegevoegd met de tenantkolom op de TWEEDE positie -> nog steeds ROOD voor die
  tabel. Dat is de kern: het gaat om de leidende kolom, niet om het bestaan van een index
  waarin de kolom ergens voorkomt.
- Ongewijzigd -> GROEN.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
from pathlib import Path

import psycopg2
import pytest
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from tests.fixtures.testdatabase import testdatabase_poort

# Tabellen die bewust geen leidende tenantindex hebben. Gedateerd, reden per regel.
KNOWN_ZONDER_INDEX: dict[str, str] = {}


def _postgres_bereikbaar() -> bool:
    poort = testdatabase_poort()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(2)
        return s.connect_ex(("127.0.0.1", poort)) == 0


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not _postgres_bereikbaar(),
        reason="vereist PostgreSQL op POSTGRES_PORT (standaard 5455)",
    ),
]

_QUERY = """
    WITH policytabellen AS (
        SELECT DISTINCT tablename AS naam FROM pg_policies WHERE schemaname = 'public'
    ),
    tenantkolom AS (
        SELECT c.relname AS naam, a.attname AS kolom
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
        JOIN pg_attribute a ON a.attrelid = c.oid
                           AND a.attname IN ('tenant_id', 'contributed_by_tenant_id')
        WHERE c.relkind IN ('r', 'p')
    ),
    eerste_kolom AS (
        SELECT c.relname AS naam,
               (SELECT a.attname FROM pg_attribute a
                 WHERE a.attrelid = c.oid AND a.attnum = x.indkey[0]) AS voorop
        FROM pg_index x
        JOIN pg_class c ON c.oid = x.indrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace AND n.nspname = 'public'
    )
    SELECT p.naam, t.kolom, bool_or(e.voorop = t.kolom) AS heeft_leidende_index
    FROM policytabellen p
    JOIN tenantkolom t ON t.naam = p.naam
    LEFT JOIN eerste_kolom e ON e.naam = p.naam
    GROUP BY p.naam, t.kolom
    ORDER BY p.naam
"""


_SCRATCH_DB = f"rls_index_check_{os.environ.get('PYTEST_XDIST_WORKER', 'main')}"


def _dsn(database: str) -> str:
    poort = str(testdatabase_poort())
    wachtwoord = os.environ.get("POSTGRES_PASSWORD", "postgres")
    return f"host=127.0.0.1 port={poort} user=postgres password={wachtwoord} dbname={database}"


@pytest.fixture(scope="module")
def dekking() -> list[tuple[str, str, bool]]:
    """Per tabel met een policy: staat de tenantkolom vooraan in een index?

    Bouwt een VERSE database uit de migratieketen. Niet de draaiende testdatabase: die is
    met `Base.metadata.create_all` opgebouwd en heeft daardoor maar 8 policies in plaats
    van 137 -- `create_all` maakt geen policies aan, alleen de conftest-fixture zet er een
    handvol. De niet-vacuum-test hieronder betrapte dat, en dat is precies waarvoor hij er
    staat.
    """
    beheer = psycopg2.connect(_dsn("postgres"))
    beheer.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    try:
        with beheer.cursor() as cur:
            cur.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                "WHERE datname = %s AND pid <> pg_backend_pid()",
                (_SCRATCH_DB,),
            )
            cur.execute(f'DROP DATABASE IF EXISTS "{_SCRATCH_DB}"')
            cur.execute(f'CREATE DATABASE "{_SCRATCH_DB}"')
    finally:
        beheer.close()

    poort = str(testdatabase_poort())
    omgeving = dict(os.environ)
    omgeving["DATABASE_URL"] = (
        f"postgresql+asyncpg://postgres:postgres@127.0.0.1:{poort}/{_SCRATCH_DB}"
    )
    resultaat = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "src/alembic.ini", "upgrade", "head"],
        cwd=Path(__file__).resolve().parents[3],
        env=omgeving,
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert resultaat.returncode == 0, (
        f"`alembic upgrade head` faalde (rc={resultaat.returncode}). Zonder deze controle "
        "zou de guard een leeg schema meten en stil groen worden.\n"
        f"--- stderr ---\n{resultaat.stderr[-3000:]}"
    )

    conn = psycopg2.connect(_dsn(_SCRATCH_DB))
    try:
        with conn.cursor() as cur:
            cur.execute(_QUERY)
            return [(naam, kolom, bool(heeft)) for naam, kolom, heeft in cur.fetchall()]
    finally:
        conn.close()


def test_every_policied_table_has_a_leading_tenant_index(
    dekking: list[tuple[str, str, bool]],
) -> None:
    """Zonder leidende index valt elke query op die tabel terug op een scan."""
    zonder = sorted(
        f"{naam} ({kolom})"
        for naam, kolom, heeft in dekking
        if not heeft and naam not in KNOWN_ZONDER_INDEX
    )

    assert not zonder, (
        f"{len(zonder)} van de {len(dekking)} tabellen met een RLS-policy hebben de "
        "tenantkolom niet als LEIDENDE kolom in een index:\n"
        + "\n".join(f"  - {r}" for r in zonder)
        + "\n\nZodra de applicatie met een eigen rol verbindt worden alle policies actief en "
        "valt elke query op deze tabellen terug op een sequential scan. Dat dient zich aan "
        "als 'de applicatie is ineens traag', zonder aanwijsbare oorzaak.\n"
        "Voeg een index toe met de tenantkolom vooraan, of zet een regel in "
        "KNOWN_ZONDER_INDEX met de reden erbij."
    )


def test_the_guard_is_not_vacuous(dekking: list[tuple[str, str, bool]]) -> None:
    """Een lege meting maakt de test hierboven trivially groen."""
    assert len(dekking) >= 120, (
        f"Slechts {len(dekking)} tabellen met een policy en een tenantkolom gevonden; op "
        "2026-08-17 waren het er 137. Is de keten wel op deze database gedraaid?"
    )
    assert any(heeft for _, _, heeft in dekking), (
        "Geen enkele tabel heeft een leidende tenantindex. Dan klopt de query niet."
    )
