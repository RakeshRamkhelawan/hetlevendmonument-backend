"""Ratel: de schemadrift tussen model en migratieketen mag niet STIJGEN (en niet stil dalen).

**Wat dit bewaakt.** Op een verse database uit de migraties meldt `alembic check` 401
verschillen met `Base.metadata` (gemeten 2026-10-23 op 76934611). Het rapport
`docs/backend/schemadrift-indeling-2026-10-23.md` deelt ze in naar soort en oordeel.
Dit bestand legt het AANTAL PER SOORT vast. Een model dat een kolom of index krijgt zonder
migratie laat een soort stijgen en maakt deze test rood, ook als de bestaande schuld
ongewijzigd blijft.

**Waarom een ratel en geen nul-eis.** 401 verschillen opruimen is een reeks migraties, een
deel met DROP of onomkeerbaar werk (interlock 1). Tot dat gebeurd is, mag de schuld alleen
krimpen. Daalt een aantal, dan moet de baseline mee omlaag: anders ontstaat er stilletjes
ruimte om er elders weer iets bij te zetten (dezelfde afspraak als de Any-ratel).

**Mutatiebewijs (2026-10-23), beide richtingen:**
1. Een kolom aan een model toegevoegd zonder migratie -> ROOD, `add_column` 0 -> 1 in de melding.
2. Een index aan een model toegevoegd zonder migratie -> ROOD, `add_index` 114 -> 115.
3. Een baselinewaarde met 1 omhoog gezet -> ROOD (`daalt`), de ratel dwingt omlaag-trekken af.
4. Ongewijzigd -> GROEN, en `test_de_meting_is_niet_leeg` bewaakt dat er uberhaupt
   meldingen gevonden worden; zonder die helft is "meet niets" een geldige oplossing.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import psycopg2
import pytest
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT
from tests.fixtures.testdatabase import testdatabase_poort

_REPO_ROOT = Path(__file__).resolve().parents[3]
# Per xdist-worker een eigen naam, om dezelfde reden als in test_the_chain_builds_the_whole_schema.
_SCRATCH_DB = f"schemadrift_ratel_{os.environ.get('PYTEST_XDIST_WORKER', 'main')}"
_MARKERING = "SCHEMADRIFT_JSON "

#: Aantal verschillen per soort. Gemeten 2026-10-23 op een verse keten, basis 76934611.
#: De oordelen per soort staan in het rapport; hier staat alleen hoeveel er zijn.
#: Deze getallen mogen alleen DALEN, en dan moet deze lijst mee.
BASELINE: dict[str, int] = {
    "add_constraint": 1,
    "add_fk": 7,
    "add_index": 114,
    "add_table_comment": 2,
    "modify_comment": 106,
    "modify_nullable": 54,
    "modify_type": 11,  # 14 tot 2026-10-23: slug en risico-enum gerepareerd
    "remove_column": 13,
    "remove_constraint": 12,
    "remove_fk": 13,
    "remove_index": 64,
    "remove_table_comment": 1,
}


def _server_dsn(database: str) -> str:
    poort = str(testdatabase_poort())
    return f"host=127.0.0.1 port={poort} user=postgres password=postgres dbname={database}"


def _omgeving() -> dict[str, str]:
    omgeving = dict(os.environ)
    poort = str(testdatabase_poort())
    omgeving["DATABASE_URL"] = (
        f"postgresql+asyncpg://postgres:postgres@127.0.0.1:{poort}/{_SCRATCH_DB}"
    )
    return omgeving


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


def _draai(commando: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        commando,
        cwd=_REPO_ROOT,
        env=_omgeving(),
        capture_output=True,
        text=True,
        timeout=900,
    )


def tel_uit_uitvoer(stdout: str) -> dict[str, int]:
    """Het getelde resultaat uit de uitvoer van `scripts/schemadrift_meten.py`."""
    for regel in stdout.splitlines():
        if regel.startswith(_MARKERING):
            return {str(k): int(v) for k, v in json.loads(regel[len(_MARKERING) :]).items()}
    raise AssertionError("de meting gaf geen resultaatregel; is het script stuk?")


def soorten_die_stijgen(
    gemeten: dict[str, int], baseline: dict[str, int]
) -> dict[str, tuple[int, int]]:
    """{soort: (baseline, gemeten)} voor elke soort waarvan het aantal HOGER is dan de baseline."""
    return {
        s: (baseline.get(s, 0), n) for s, n in sorted(gemeten.items()) if n > baseline.get(s, 0)
    }


def soorten_die_dalen(
    gemeten: dict[str, int], baseline: dict[str, int]
) -> dict[str, tuple[int, int]]:
    """{soort: (baseline, gemeten)} voor elke soort waarvan het aantal LAGER is dan de baseline."""
    return {s: (n, gemeten.get(s, 0)) for s, n in sorted(baseline.items()) if gemeten.get(s, 0) < n}


@pytest.fixture(scope="module")
def gemeten_drift() -> dict[str, int]:
    """Bouw een verse database uit de migraties en tel de drift per soort."""
    _verse_database()
    keten = _draai([sys.executable, "-m", "alembic", "-c", "src/alembic.ini", "upgrade", "head"])
    assert keten.returncode == 0, (
        f"`alembic upgrade head` faalde ({keten.returncode}); zonder deze controle zou de "
        f"ratel een leeg schema meten en stil groen worden.\n{keten.stderr[-3000:]}"
    )
    meting = _draai([sys.executable, "scripts/schemadrift_meten.py"])
    assert meting.returncode == 0, f"de driftmeting faalde:\n{meting.stderr[-3000:]}"
    return tel_uit_uitvoer(meting.stdout)


@pytest.mark.integration
class TestDeSchemadriftStijgtNiet:
    def test_geen_soort_stijgt_boven_de_baseline(self, gemeten_drift: dict[str, int]) -> None:
        stijgt = soorten_die_stijgen(gemeten_drift, BASELINE)
        assert not stijgt, (
            "Er is NIEUWE schemadrift tussen model en migratieketen (soort: baseline -> nu):\n"
            + "\n".join(f"  {s}: {b} -> {n}" for s, (b, n) in stijgt.items())
            + "\n\nWelke het is, zie je met `python scripts/schemadrift_meten.py --lijst` op een "
            "verse keten. Meestal: een kolom of index in een model zonder migratie. Schrijf de "
            "migratie; zet de baseline NIET omhoog."
        )

    def test_geen_soort_daalt_stil_onder_de_baseline(self, gemeten_drift: dict[str, int]) -> None:
        daalt = soorten_die_dalen(gemeten_drift, BASELINE)
        assert not daalt, (
            "De schuld is gekrompen -- trek de baseline mee omlaag, anders ontstaat er ruimte "
            "om er elders iets bij te zetten (soort: baseline -> nu):\n"
            + "\n".join(f"  {s}: {b} -> {n}" for s, (b, n) in daalt.items())
        )

    def test_de_meting_is_niet_leeg(self, gemeten_drift: dict[str, int]) -> None:
        assert sum(gemeten_drift.values()) >= 100, (
            f"Slechts {sum(gemeten_drift.values())} verschillen gemeten; op 2026-10-23 waren het "
            "er 401. Is de meting stuk of is de schuld echt weg (dan hoort deze ratel een "
            "nul-eis te worden)?"
        )


class TestDeVergelijkingZelfIsNietBlind:
    """Mutatiebewijs zonder database."""

    def test_een_nieuwe_soort_telt_als_stijging(self) -> None:
        assert soorten_die_stijgen({"add_column": 1}, {"add_index": 3}) == {"add_column": (0, 1)}

    def test_een_hoger_aantal_telt_als_stijging(self) -> None:
        assert soorten_die_stijgen({"add_index": 4}, {"add_index": 3}) == {"add_index": (3, 4)}

    def test_een_gelijk_of_lager_aantal_is_geen_stijging(self) -> None:
        gemeten = {"add_index": 3, "modify_type": 1}
        assert soorten_die_stijgen(gemeten, {"add_index": 3, "modify_type": 2}) == {}

    def test_een_lager_aantal_telt_als_daling(self) -> None:
        assert soorten_die_dalen({"add_index": 2}, {"add_index": 3}) == {"add_index": (3, 2)}

    def test_een_verdwenen_soort_telt_als_daling(self) -> None:
        assert soorten_die_dalen({}, {"add_index": 3}) == {"add_index": (3, 0)}

    def test_de_resultaatregel_wordt_uit_rumoerige_uitvoer_gehaald(self) -> None:
        uitvoer = 'INFO ruis\nSCHEMADRIFT_JSON {"add_index": 3}\nnog meer ruis\n'
        assert tel_uit_uitvoer(uitvoer) == {"add_index": 3}

    def test_uitvoer_zonder_resultaatregel_faalt_hard(self) -> None:
        with pytest.raises(AssertionError):
            tel_uit_uitvoer("geen markering hier")
