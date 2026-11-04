"""Is een DATABASE_URL een herkenbare WEGWERPdatabase? Zo niet, dan schrijven we er niets in.

Gebruikt door `scripts/acceptance_thread.py` (stap 5, stap 7 en `--seed`): die maken rijen aan en
wissen ze weer. Tot 2026-10-14 deed dat script dat in de database uit `DATABASE_URL` zonder te
controleren wat voor database dat was; de standaardwaarde wees naar de gedeelde testserver onder de
naam `sanskritisetu`, dezelfde naam als de ontwikkel- en productiedatabase.

De regel is bewust smal en leesbaar:

- de host is LOKAAL (`localhost`, `127.0.0.1` of `::1`): een wegwerpdatabase staat op deze machine;
- de naam bevat als LOSSE woorden (gescheiden door `_` of `-`) een van `WEGWERP_WOORDEN`. Een los
  woord, zodat `sanskritisetu_test` mag en `latest` of `contest_data` niet;
- de driver is PostgreSQL.

Het antwoord noemt de host en de databasenaam en NOOIT het wachtwoord.
"""

from __future__ import annotations

import re

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError

WEGWERP_WOORDEN = frozenset({"test", "wegwerp", "acceptance", "acceptatie", "scratch", "tmp"})
LOKALE_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})

UITLEG = (
    "Oplossing: zet DATABASE_URL (of SANSKRITISETU_TEST_DATABASE_URL) op een lokale "
    "wegwerpdatabase, zonder queryparameters en met test, wegwerp, acceptatie, acceptance, scratch "
    "of tmp als los woord in de naam (gescheiden door _). Maak er een aan met "
    "`docker exec <container> createdb -U postgres sanskritisetu_acceptatie_wegwerp` en laat "
    "`alembic upgrade head` ertegen draaien."
)


class GeenWegwerpDatabase(RuntimeError):
    """De database uit DATABASE_URL is geen herkenbare wegwerpdatabase."""


def controleer_wegwerp_database(url: str) -> str:
    """Geef `host/databasenaam` terug als dit een herkenbare wegwerpdatabase is, anders een fout."""
    try:
        geparsed = make_url(url)
    except (ArgumentError, TypeError, ValueError):
        raise GeenWegwerpDatabase("DATABASE_URL is geen geldige databaseverwijzing") from None

    host = (geparsed.host or "").lower()
    naam = geparsed.database or ""
    wie = f"host '{host or 'onbekend'}', database '{naam or 'onbekend'}'"

    if not geparsed.drivername.startswith("postgresql"):
        raise GeenWegwerpDatabase(f"{wie}: geen PostgreSQL-database")
    if geparsed.query:
        # Een queryparameter wint van host en databasenaam (asyncpg: `opts.update(url.query)`,
        # gemeten 2026-10-14: `?host=andere&database=prod` stuurt de verbinding naar een andere
        # server terwijl de URL er lokaal uitziet). Daarom: geen enkele parameter.
        raise GeenWegwerpDatabase(
            f"{wie}: queryparameters in de URL zijn niet toegestaan (ze kunnen de host en de "
            "database overschrijven)"
        )
    if host not in LOKALE_HOSTS:
        raise GeenWegwerpDatabase(f"{wie}: de host is niet lokaal")
    woorden = {w for w in re.split(r"[_\-]+", naam.lower()) if w}
    if not woorden & WEGWERP_WOORDEN:
        raise GeenWegwerpDatabase(f"{wie}: de naam is geen herkenbare wegwerpnaam")
    return f"{host}/{naam}"
