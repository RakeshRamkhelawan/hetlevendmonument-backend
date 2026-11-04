"""Een database-URL mag nooit met gebruiker of wachtwoord in de uitvoer komen (brief 2026-10-23).

De hulpfunctie geeft alleen schema, host, poort en databasenaam terug. De URL wordt gelezen zoals de applicatie hem
leest (`sqlalchemy.engine.make_url`), zodat een wachtwoord met `/` of `%`-tekens niet als host wordt uitgelegd.
"""

from __future__ import annotations

import pytest

from src.core.utils.url_zonder_wachtwoord import database_url_zonder_wachtwoord

URL = "postgresql+asyncpg://appgebruiker:g3heim-W8woord@db.example.com:5432/sanskriti"


def test_gebruiker_en_wachtwoord_staan_er_niet_in() -> None:
    tekst = database_url_zonder_wachtwoord(URL)

    assert ("appgebruiker" in tekst, "g3heim" in tekst, "W8woord" in tekst) == (False, False, False)


def test_schema_host_poort_en_database_blijven_zichtbaar() -> None:
    assert (
        database_url_zonder_wachtwoord(URL) == "postgresql+asyncpg://db.example.com:5432/sanskriti"
    )


def test_zonder_poort_blijft_de_poort_weg() -> None:
    assert (
        database_url_zonder_wachtwoord("postgresql://u:p@host.example/db")
        == "postgresql://host.example/db"
    )


def test_een_wachtwoord_met_een_schuine_streep_wordt_niet_als_host_gelezen() -> None:
    tekst = database_url_zonder_wachtwoord("postgresql://u:ab/cd:ef@host.example:5433/db")

    assert tekst == "postgresql://host.example:5433/db"


def test_een_wachtwoord_met_procenttekens_komt_er_niet_in() -> None:
    tekst = database_url_zonder_wachtwoord("postgresql://u:p%40ss%2Fword@host.example/db")

    assert ("p%40ss" in tekst, "word" in tekst) == (False, False)


def test_queryparameters_met_een_geheim_blijven_weg() -> None:
    tekst = database_url_zonder_wachtwoord(
        "postgresql://u:p@host.example/db?sslpassword=geheimpje&sslmode=require"
    )

    assert ("geheimpje" in tekst, "?" in tekst) == (False, False)


def test_sqlite_houdt_zijn_pad() -> None:
    assert database_url_zonder_wachtwoord("sqlite:///./lokaal.db") == "sqlite:///./lokaal.db"


@pytest.mark.parametrize("leeg", [None, "", "   "])
def test_een_ontbrekende_url_geeft_een_vaste_tekst(leeg: str | None) -> None:
    assert database_url_zonder_wachtwoord(leeg) == "<geen database-url>"


def test_een_onleesbare_url_wordt_nooit_teruggegeven() -> None:
    tekst = database_url_zonder_wachtwoord("dit is geen url maar bevat geheim-w8woord")

    assert tekst == "<database-url>"


@pytest.mark.parametrize(
    ("url", "staart"),
    [
        ("postgresql://u:pa@ss@host:5432/db", "ss"),
        ("postgresql://u:a@b@c@host/db", "b@c"),
        ("postgresql://u:p@ss@host/db?sslmode=require", "ss@"),
        ("postgresql://u:pa?x@ho@st/db", "ho@st"),
        ("postgresql://u:pa@ss?x=1@host/db", "ss"),
    ],
)
def test_een_wachtwoord_met_een_ruwe_apenstaart_toont_geen_staartdeel(url: str, staart: str) -> None:
    """Een ruwe `@` in het wachtwoord laat de URL-lezer het tweede deel als host zien; dan tonen we niets."""
    tekst = database_url_zonder_wachtwoord(url)

    assert (tekst, staart in tekst.replace("<database-url>", "")) == ("<database-url>", False)


def test_een_normale_url_met_een_apenstaart_voor_de_host_blijft_leesbaar() -> None:
    assert database_url_zonder_wachtwoord("postgresql://u:p%40ss@host:5432/db") == "postgresql://host:5432/db"
