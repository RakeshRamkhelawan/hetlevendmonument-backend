"""De testsuite wist alleen een database die aantoonbaar een TESTdatabase is.

Brief 2026-10-26 (de testsuite wist alleen een testdatabase). Gemeten: de sessie-fixture van de integratietests
(`tests/integration/conftest.py`, `setup_database_schema`) beeindigt eerst alle andere verbindingen op de database
(`pg_terminate_backend`) en doet dan `DROP SCHEMA IF EXISTS legacy CASCADE` en `... public CASCADE` op de database uit
`SANSKRITISETU_TEST_DATABASE_URL`; `tests/fixtures/database.py` (`postgres_engine`) doet `DROP SCHEMA public CASCADE`.
Er was GEEN controle dat die database een testdatabase is. Op 2026-10-26 maakte een meting daardoor de gedeelde
testdatabase `sanskritisetu` op 5455 leeg en bouwde hem opnieuw op.

De regel (`tests/fixtures/testdatabase.py::eis_testdatabase`): de databasenaam eindigt op `_test` EN de netwerkpoort is
niet die van de ontwikkeldatabase (5435). Anders een fout, en er is niets gewist of beeindigd.

Twee soorten toetsen:
  1. gedrag van de controle zelf, in BEIDE richtingen (een niet-testnaam en poort 5435 worden geweigerd; een
     testnaam op 5455 mag, en `sanskritisetu_test` ook);
  2. BEDRADING, per AST: elke functie onder `tests/` met een `DROP SCHEMA`-opdracht roept `eis_testdatabase` aan
     VOOR de eerste destructieve opdracht (`DROP SCHEMA` of `pg_terminate_backend`). Een nieuwe plek zonder die
     aanroep maakt deze test rood.

BEWUST BUITEN BEREIK (Gate 2, beveiligingsreview 2026-10-27, niet in deze brief): de bedrading toetst alleen
`DROP SCHEMA`. `TRUNCATE ... CASCADE` in `reset_db_per_module` en een paar tests (gedekt doordat de sessie-fixture
eerst loopt, niet zelf bewaakt), de scratch-databases met `DROP DATABASE` in vijf integratietests, en
`Base.metadata.drop_all` in `tests/als/conftest.py` zitten niet achter `eis_testdatabase`. Voor die plekken is een
eigen brief nodig.

MUTATIEBEWIJS (2026-10-27, per mutatie van de productiekant van de testsuite, kopie als terugweg; basis 12 groen):
    conftest: `eis_testdatabase` weg                         -> ROOD (bedrading)
    database.py: `eis_testdatabase` weg                      -> ROOD (bedrading)
    conftest: controle NA `pg_terminate_backend`/`DROP`     -> ROOD (volgorde)
    helper: achtervoegsel `_test` niet meer geeist            -> ROOD (4)
    helper: ontwikkelpoort 5435 niet meer geweigerd           -> ROOD
    helper: weigert alles                                     -> ROOD (4)
    helper: querystring niet meer geweigerd (Gate 2)          -> ROOD (2)
    helper: host/poort niet meer geeist (Gate 2)              -> ROOD (2)
    alles terug                                               -> GROEN (15)
EIND-TOT-EIND (2026-10-27, echte database op 5455, `test_billing_status_endpoints.py`): niet-testnaam
`integratie_meting_1026` -> `GeenTestdatabase`, 205 tabellen ervoor EN erna (niets gewist); poort 5435 met een
testnaam -> `GeenTestdatabase`; testnaam `drop_meting_1027_test` op 5455 -> 2 passed.
"""

from __future__ import annotations

import ast
import functools
from pathlib import Path

import pytest

from tests.fixtures.testdatabase import GeenTestdatabase, eis_testdatabase

REPO_ROOT = Path(__file__).resolve().parents[3]
TESTS = REPO_ROOT / "tests"

#: De opdracht die een functie tot een wispunt maakt, en wat in DIEZELFDE functie ook als destructief telt: eerst
#: beeindigt de sessie-fixture alle andere verbindingen en pas dan volgt de DROP.
WISOPDRACHT = "DROP SCHEMA"
DESTRUCTIEF = (WISOPDRACHT, "PG_TERMINATE_BACKEND")

TESTNAAM_OP_5455 = "postgresql+asyncpg://postgres:postgres@127.0.0.1:5455/sanskritisetu_test"


# --- gedrag van de controle ---------------------------------------------------------------------------------------


def test_een_testdatabase_op_de_testpoort_mag() -> None:
    eis_testdatabase(TESTNAAM_OP_5455)


def test_de_naam_sanskriti_test_mag_ook() -> None:
    eis_testdatabase("postgresql+asyncpg://postgres:postgres@127.0.0.1:5455/sanskriti_test")


def test_een_wegwerpnaam_met_testachtervoegsel_mag() -> None:
    eis_testdatabase("postgresql+asyncpg://postgres:postgres@localhost:5432/integratie_meting_test")


def test_een_naam_zonder_testachtervoegsel_wordt_geweigerd() -> None:
    with pytest.raises(GeenTestdatabase):
        eis_testdatabase("postgresql+asyncpg://postgres:postgres@127.0.0.1:5455/sanskritisetu")


def test_de_ontwikkelpoort_wordt_geweigerd_ook_met_een_testnaam() -> None:
    with pytest.raises(GeenTestdatabase):
        eis_testdatabase("postgresql+asyncpg://postgres:postgres@127.0.0.1:5435/sanskritisetu_test")


def test_een_testnaam_midden_in_de_naam_telt_niet() -> None:
    with pytest.raises(GeenTestdatabase):
        eis_testdatabase("postgresql+asyncpg://postgres:postgres@127.0.0.1:5455/test_sanskritisetu")


def test_een_url_zonder_databasenaam_wordt_geweigerd() -> None:
    with pytest.raises(GeenTestdatabase):
        eis_testdatabase("postgresql+asyncpg://postgres:postgres@127.0.0.1:5455")


def test_queryparameters_die_de_database_of_poort_overschrijven_worden_geweigerd() -> None:
    """Gate 2: bij asyncpg wint `?database=`/`?port=` van het pad. `x_test?database=sanskritisetu&port=5435` haalde de
    naamcontrole terwijl de engine naar de ontwikkeldatabase ging."""
    with pytest.raises(GeenTestdatabase):
        eis_testdatabase(
            "postgresql+asyncpg://postgres:postgres@127.0.0.1:5455/x_test?database=sanskritisetu&port=5435"
        )


def test_elke_querystring_wordt_geweigerd_ook_een_onschuldige() -> None:
    with pytest.raises(GeenTestdatabase):
        eis_testdatabase(TESTNAAM_OP_5455 + "?sslmode=disable")


def test_een_url_zonder_host_en_poort_wordt_geweigerd() -> None:
    """Zonder host/poort neemt asyncpg PGHOST/PGPORT uit de omgeving; die kunnen naar 5435 wijzen."""
    with pytest.raises(GeenTestdatabase):
        eis_testdatabase("postgresql+asyncpg://postgres:postgres@/sanskritisetu_test")


def test_een_url_met_host_maar_zonder_poort_wordt_geweigerd() -> None:
    with pytest.raises(GeenTestdatabase):
        eis_testdatabase("postgresql+asyncpg://postgres:postgres@127.0.0.1/sanskritisetu_test")


def test_hoofdletters_in_het_achtervoegsel_tellen_niet_als_test() -> None:
    """`_TEST` is geen afspraak die ergens staat; de controle is bewust strikt op de vaste schrijfwijze."""
    with pytest.raises(GeenTestdatabase):
        eis_testdatabase("postgresql+asyncpg://postgres:postgres@127.0.0.1:5455/sanskritisetu_TEST")


def test_de_foutmelding_noemt_de_naam_en_de_poort_maar_geen_wachtwoord() -> None:
    with pytest.raises(GeenTestdatabase) as fout:
        eis_testdatabase("postgresql+asyncpg://postgres:geheim123@127.0.0.1:5435/sanskritisetu")

    tekst = str(fout.value)
    assert ("sanskritisetu" in tekst, "5435" in tekst, "geheim123" in tekst) == (True, True, False)


# --- bedrading: elke plek die wist, controleert eerst ---------------------------------------------------------------


def _normaal(tekst: str) -> str:
    """Hoofdletters en een enkele spatie: `drop   schema` en `DROP SCHEMA` zijn dezelfde opdracht (Gate 2)."""
    return " ".join(tekst.split()).upper()


def _naam(knoop: ast.expr) -> str:
    return getattr(knoop, "attr", getattr(knoop, "id", ""))


def _docstring_van(functie: ast.FunctionDef | ast.AsyncFunctionDef) -> ast.Constant | None:
    eerste = functie.body[0] if functie.body else None
    if (
        isinstance(eerste, ast.Expr)
        and isinstance(eerste.value, ast.Constant)
        and isinstance(eerste.value.value, str)
    ):
        return eerste.value
    return None


@functools.cache
def _functies_met_destructieve_opdracht() -> list[tuple[str, str, int, list[int]]]:
    """(bestand, functie, eerste destructieve regel, regels van `eis_testdatabase`-aanroepen).

    Eerst een goedkope bytes-toets op de wisopdracht (2614 bestanden in 1 s), daarna pas een AST van de treffers.
    """
    gevonden: list[tuple[str, str, int, list[int]]] = []
    dit_bestand = Path(__file__).resolve()
    for pad in sorted(TESTS.rglob("*.py")):
        if pad.resolve() == dit_bestand or WISOPDRACHT.encode() not in pad.read_bytes().upper():
            continue
        try:
            boom = ast.parse(pad.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for functie in ast.walk(boom):
            if not isinstance(functie, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            docstring = _docstring_van(functie)
            destructief = [
                n.lineno
                for n in ast.walk(functie)
                if isinstance(n, ast.Constant)
                and isinstance(n.value, str)
                and n is not docstring
                and any(opdracht in _normaal(n.value) for opdracht in DESTRUCTIEF)
            ]
            if not any(
                isinstance(n, ast.Constant)
                and isinstance(n.value, str)
                and n is not docstring
                and WISOPDRACHT in _normaal(n.value)
                for n in ast.walk(functie)
            ):
                continue
            aanroepen = [
                n.lineno
                for n in ast.walk(functie)
                if isinstance(n, ast.Call) and _naam(n.func) == "eis_testdatabase"
            ]
            gevonden.append(
                (pad.relative_to(REPO_ROOT).as_posix(), functie.name, min(destructief), aanroepen)
            )
    return gevonden


def test_er_zijn_plekken_die_wissen_zodat_de_bedrading_iets_meet() -> None:
    bestanden = {bestand for bestand, _, _, _ in _functies_met_destructieve_opdracht()}

    assert {"tests/integration/conftest.py", "tests/fixtures/database.py"} <= bestanden


def test_elke_plek_die_wist_controleert_eerst_dat_het_een_testdatabase_is() -> None:
    zonder = [
        f"{bestand}::{functie} (eerste destructieve regel {regel})"
        for bestand, functie, regel, aanroepen in _functies_met_destructieve_opdracht()
        if not aanroepen or min(aanroepen) >= regel
    ]

    assert zonder == [], (
        "Deze functies wissen een database (DROP SCHEMA of pg_terminate_backend) zonder eerst "
        f"`eis_testdatabase(url)` aan te roepen: {zonder}. Zie tests/fixtures/testdatabase.py."
    )
